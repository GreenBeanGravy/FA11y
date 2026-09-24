"""Read-only Epic account quest snapshots, usable without a match connection."""
from datetime import datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path
import threading
import time

import requests


class QuestQueryError(Exception):
    """Safe user-facing failure without tokens, response bodies, or account IDs."""


@lru_cache(maxsize=1)
def quest_catalog():
    try:
        data = json.loads((Path(__file__).resolve().parents[1] / 'data/packet_quests_4210.json').read_text(encoding='utf-8'))
        rows = data['rows']
        supplement = Path(__file__).resolve().parents[1] / 'data/quest_supplement_4220.json'
        if supplement.exists():
            rows.update(json.loads(supplement.read_text(encoding='utf-8'))['rows'])
        return rows
    except (OSError, ValueError, KeyError):
        return {}


def _number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


@lru_cache(maxsize=1)
def quest_suppression():
    try:
        return json.loads((Path(__file__).resolve().parents[1]/'data/quest_suppression_4220.json').read_text(encoding='utf-8'))['bundles']
    except (OSError,ValueError,KeyError):
        return {}


def normalize_quest(item_id, item, catalog, now):
    template = item.get('templateId', '')
    attributes = item.get('attributes', {})
    metadata = catalog.get(template.lower(), {})
    objectives = []
    remaining = {k[len('completion_'):].lower(): _number(v) for k, v in attributes.items() if k.lower().startswith('completion_')}
    for objective in metadata.get('objectives', []):
        key = objective['key'].lower()
        objectives.append(dict(key=key, achieved=remaining.pop(key, None), required=_number(objective.get('required')),
            description=objective.get('description', ''), hidden=objective.get('hidden', False)))
    objectives.extend(dict(key=k, achieved=v, required=None, description='', hidden=False) for k, v in remaining.items())
    expiry = attributes.get('expiry_time')
    expired = False
    if isinstance(expiry, str):
        try:
            parsed = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            expired = parsed.year > 1 and parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp() <= now
        except ValueError:
            pass
    state = attributes.get('quest_state', 'Unknown')
    if not isinstance(state, str):
        state = 'Unknown'
    return dict(id=item_id, template=template, name=metadata.get('name') or template.partition(':')[2],
        description=metadata.get('description', ''), state=state, expiry=expiry, expired=expired,
        objectives=objectives, completion_count=metadata.get('completion_count'),
        categories=metadata.get('categories', []), products=metadata.get('products', []),
        hidden=metadata.get('hidden', False), metadata_available=bool(metadata),
        bundle_id=attributes.get('challenge_bundle_id'), source='epic_account_api', updated_at=now)


def parse_profile_response(data, catalog=None, now=None):
    now = time.time() if now is None else now
    profiles = [change['profile'] for change in data.get('profileChanges', [])
                if change.get('changeType') == 'fullProfileUpdate' and isinstance(change.get('profile'), dict)]
    if len(profiles) != 1 or profiles[0].get('profileId') != 'athena':
        raise QuestQueryError('Epic did not return a complete Battle Royale quest profile. Refresh to retry.')
    profile = profiles[0]
    catalog = quest_catalog() if catalog is None else catalog
    quests = [normalize_quest(key, item, catalog, now) for key, item in profile.get('items', {}).items()
              if isinstance(item, dict) and str(item.get('templateId', '')).lower().startswith('quest:')]
    bundles={key:item.get('templateId','').lower() for key,item in profile.get('items',{}).items()
             if isinstance(item,dict) and item.get('templateId','').lower().startswith('challengebundle:')}
    suppression=quest_suppression()
    for quest in quests:
        bundle=bundles.get(quest.get('bundle_id'),'')
        quest['suppressed']=quest['template'].lower() in suppression.get(bundle,[])
    return dict(quests=quests, updated_at=now, revision=profile.get('rvn'), source='epic_account_api')


class EpicQuestAPI:
    def __init__(self, auth, session=None, clock=None):
        self.auth = auth
        self.session = session or requests.Session()
        self.clock = clock or time.time
        self.lock = threading.Lock()

    def query(self):
        with self.lock:
            if not self.auth or not self.auth.account_id or not self.auth.access_token:
                raise QuestQueryError('Sign in through FA11y\'s Epic Games login, then refresh quests.')
            for attempt in range(2):
                try:
                    response = self.session.post(
                        self.auth.MCP_URL + '/' + self.auth.account_id + '/client/QueryProfile',
                        params={'profileId': 'athena', 'rvn': -1}, json={},
                        headers={'Authorization': 'Bearer ' + self.auth.access_token}, timeout=20)
                except requests.RequestException:
                    raise QuestQueryError('Could not reach Epic Games. Refresh quests to retry.') from None
                if response.status_code == 401 and attempt == 0:
                    if self.auth.refresh_access_token():
                        continue
                    raise QuestQueryError('Epic Games login expired. Sign in again through FA11y.')
                if response.status_code == 429:
                    raise QuestQueryError('Epic Games limited quest requests. Try again later.')
                if response.status_code != 200:
                    raise QuestQueryError(f'Epic Games could not return quests (HTTP {response.status_code}).')
                try:
                    data = response.json()
                except ValueError:
                    raise QuestQueryError('Epic Games returned an unreadable quest response.') from None
                if not isinstance(data, dict) or data.get('errorCode'):
                    raise QuestQueryError('Epic Games rejected the quest query.')
                return parse_profile_response(data, now=self.clock())
            raise QuestQueryError('Epic Games login expired. Sign in again through FA11y.')


def quest_progress_text(quest):
    values = []
    for objective in quest['objectives']:
        if objective.get('hidden'):
            continue
        achieved, required = objective.get('achieved'), objective.get('required')
        if achieved is None:
            values.append('Progress not reported')
        elif required is None:
            values.append(f'{achieved:g}; target unavailable')
        else:
            values.append(f'{achieved:g} of {required:g}')
    return '; '.join(values) or 'No objective counter reported'
