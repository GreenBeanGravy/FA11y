"""Current season-pass viewing and explicit, verified account operations.

Offer IDs/page order come from cooked game definitions, never cosmetic ownership.
Queries may retry authentication; mutations are sent once and reconciled by query.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time

import requests
from lib.utilities.pass_quests import pass_quest_snapshot, pass_quest_status

CATALOG_URL = 'https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/storefront/v2/catalog'
_ACCOUNT_OPERATIONS = threading.RLock()
CURRENCY_NAMES = {
    'accountresource:athenabattlestar': 'BR reward points',
    'accountresource:athenacategorystar': 'set-unlock tokens',
    'accountresource:figmentpass_currency': 'OG reward points',
    'accountresource:musicpassnote': 'Music reward points',
    'accountresource:junoseasonpasscurrency': 'LEGO reward points',
    'MtxCurrency': 'V-Bucks',
}


class PassError(Exception):
    """Account-safe message suitable for display; never includes raw responses."""


def load_pass_catalog():
    path = Path(__file__).resolve().parents[2] / 'data/season_passes_4220.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 1:
        raise PassError('Pass definitions need updating.')
    return data['passes']


def pages(pass_data):
    return [(category, page) for category in pass_data['categories'] for page in category['pages']]


def rewards(category):
    return [r for page in category['pages'] for r in page['rewards'] if r['kind'] == 'reward']


def costs_text(costs):
    return ', '.join(f'{amount:,} {CURRENCY_NAMES.get(currency, currency)}'
                     for currency, amount in costs.items() if amount) or 'No currency cost'


def full_profile(data, profile_id):
    matches = [c.get('profile') for c in data.get('profileChanges', [])
               if c.get('changeType') == 'fullProfileUpdate' and isinstance(c.get('profile'), dict)
               and c['profile'].get('profileId') == profile_id]
    if len(matches) != 1 or not isinstance(matches[0].get('items'), dict):
        raise PassError('Epic did not return a complete pass profile. Refresh to retry.')
    return matches[0]


def snapshot_from_profiles(athena, common, store, definitions, now=None):
    now = time.time() if now is None else now
    balances = Counter()
    for item in athena['items'].values():
        if item.get('templateId', '').lower().startswith('accountresource:'):
            quantity = item.get('quantity')
            if type(quantity) is int and quantity >= 0:
                balances[item['templateId'].lower()] += quantity
    pass_states = {}
    for definition in definitions:
        matches = [v for v in athena['items'].values()
                   if v.get('templateId', '').lower() == definition['template'].lower()]
        attrs = matches[0].get('attributes', {}) if len(matches) == 1 else {}
        storefront = next((f for f in store.get('storefronts', []) if f.get('name') == definition['storefront']), {})
        offers = [e for e in storefront.get('catalogEntries', []) if e.get('offerId') == definition['purchase_offer']]
        # Both exact live season and its currently offered pass must agree.
        active = len(matches) == 1 and len(offers) == 1
        pass_states[definition['key']] = dict(
            active=active, purchased=attrs.get('purchased') is True,
            level=attrs.get('level'), claimed={str(r.get('offerId', '')).upper() for r in attrs.get('purchased_offers', [])},
            offer=offers[0] if len(offers) == 1 else None,
        )
    return dict(passes=pass_states, balances=dict(balances), athena=athena, common=common,
                expiration=store.get('expiration'), updated_at=now,
                quests=pass_quest_snapshot(athena,now))


def find_context(definition, reward_id):
    for category, page in pages(definition):
        for reward in page['rewards']:
            if reward['id'] == reward_id:
                return category, page, reward
    raise PassError('That reward is no longer in this pass. Refresh the dialog.')


def requirement_text(reward):
    req = reward.get('requirements', {})
    messages = []
    if req.get('bRequireAllOtherPageRewards'):
        messages.append('Claim the other rewards on this page first.')
    if req.get('bRequireAllOtherCategoryRewards'):
        messages.append('Claim the other rewards in this set first.')
    for key, label in [('RewardsNeededForUnlock', 'page rewards'), ('TotalRewardsNeededForUnlock', 'set rewards'),
                       ('TotalPassRewardsNeededForUnlock', 'pass rewards')]:
        if req.get(key):
            messages.append(f"Requires {req[key]} {label}; Epic checks eligibility when claiming.")
    return ' '.join(messages)


def reward_status(definition, category, page, reward, snapshot):
    if reward['kind'] == 'quest':
        return pass_quest_status(reward,snapshot.get('quests') if snapshot else None)
    state = snapshot['passes'][definition['key']] if snapshot else None
    if not state or not state['active']:
        return 'Account status unavailable; refresh required'
    if reward['id'] in state['claimed']:
        return 'Claimed'
    if not reward['free'] and not state['purchased']:
        return 'Requires premium pass'
    if any(r['id'] not in state['claimed'] for r in category['unlock_offers']):
        return 'Set locked; unlock this set first'
    if snapshot['balances'].get(reward['currency'], 0) < reward['cost']:
        return 'Not enough reward points'
    return 'Unclaimed' + ('; prerequisites apply' if reward.get('requirements') else '')


@dataclass(frozen=True)
class PassAction:
    account_id: str
    pass_key: str
    kind: str
    offer_ids: tuple
    costs: tuple
    names: tuple
    created_at: float

    @property
    def summary(self):
        action = {'claim': 'Claim', 'unlock': 'Unlock', 'purchase': 'Purchase'}[self.kind]
        return f"{action}:\n" + '\n'.join(self.names) + '\n\nCost: ' + costs_text(dict(self.costs))


class EpicPassAPI:
    def __init__(self, auth, session=None, definitions=None, clock=None):
        self.auth = auth
        self.session = session or requests.Session()
        self.definitions = load_pass_catalog() if definitions is None else definitions
        self.clock = clock or time.time

    def _request(self, method, url, *, mutation=False, **kwargs):
        if not self.auth or not self.auth.account_id or not self.auth.access_token:
            raise PassError('Sign in through the locker, then refresh your passes.')
        for attempt in range(2):
            try:
                response = self.session.request(method, url,
                    headers={'Authorization': 'Bearer ' + self.auth.access_token, 'X-EpicGames-Language': 'en'},
                    timeout=25, **kwargs)
            except requests.RequestException:
                raise PassError('The result is uncertain. Refresh before trying again.' if mutation else
                                'Could not reach Epic Games. Refresh to retry.') from None
            if response.status_code == 401 and not mutation and attempt == 0:
                if self.auth.refresh_access_token():
                    continue
            if response.status_code != 200:
                message = {401: 'Your Epic login expired. Sign in again.',
                           429: 'Epic limited these requests. Try again later.'}.get(response.status_code)
                raise PassError(message or f'Epic rejected the request (HTTP {response.status_code}). Refresh to check requirements and balances.')
            try:
                result = response.json()
            except ValueError:
                raise PassError('Epic returned an unreadable response. Refresh before trying again.') from None
            if not isinstance(result, dict) or result.get('errorCode'):
                raise PassError('Epic did not accept the operation. Refresh to check the current pass requirements.')
            return result

    def _url(self, operation):
        if not self.auth or not self.auth.account_id:
            raise PassError('Sign in through the locker, then refresh your passes.')
        return self.auth.MCP_URL + '/' + self.auth.account_id + '/client/' + operation

    def query(self):
        with _ACCOUNT_OPERATIONS:
            account = self.auth.account_id if self.auth else None
            profiles = []
            for profile_id in ('athena', 'common_core'):
                data = self._request('POST', self._url('QueryProfile'),
                                     params={'profileId': profile_id, 'rvn': -1}, json={})
                profiles.append(full_profile(data, profile_id))
            catalog = self._request('GET', CATALOG_URL)
            if self.auth.account_id != account:
                raise PassError('Your account changed during refresh. Refresh again.')
            result = snapshot_from_profiles(*profiles, catalog, self.definitions, self.clock())
            result['account_id'] = account
            return result

    def definition(self, key):
        try:
            return next(d for d in self.definitions if d['key'] == key)
        except StopIteration:
            raise PassError('This pass definition is unavailable.') from None

    def prepare(self, key, kind, ids, snapshot):
        definition = self.definition(key)
        state = snapshot['passes'][key]
        if snapshot.get('account_id') != self.auth.account_id:
            raise PassError('Your account changed. Refresh before continuing.')
        if not state['active']:
            raise PassError('This pass is not confirmed active. Refresh; its definitions may need updating.')
        if self.clock() - snapshot['updated_at'] > 120:
            raise PassError('Refresh the pass before claiming or purchasing.')
        try:
            expiry = datetime.fromisoformat(snapshot['expiration'].replace('Z', '+00:00')).replace(tzinfo=timezone.utc).timestamp()
        except (ValueError, TypeError, AttributeError):
            raise PassError('Epic did not return a valid storefront expiration. Refresh before continuing.') from None
        if expiry <= self.clock():
            raise PassError('The storefront expired. Refresh before continuing.')
        costs = Counter(); names = []; selected = []
        if kind == 'purchase':
            if state['purchased']:
                raise PassError('You already own this pass.')
            offer = state['offer']; prices = offer.get('prices', [])
            if len(prices) != 1 or prices[0].get('currencyType') != 'MtxCurrency' or offer.get('offerType') != 'StaticPrice':
                raise PassError('This purchase type is not supported here. Use Fortnite to purchase it.')
            price = prices[0].get('finalPrice')
            if type(price) is not int or price < 0 or prices[0].get('currencySubType', ''):
                raise PassError('Epic did not return a supported pass price.')
            costs['MtxCurrency'] = price; selected = [offer['offerId']]; names = [definition['name']]
        elif kind in ('claim', 'unlock'):
            if not ids or len(set(ids)) != len(ids):
                raise PassError('No unique rewards were selected.')
            candidates = {r['id']: (c, r) for c in definition['categories']
                          for r in (c['unlock_offers'] if kind == 'unlock' else rewards(c))}
            for reward_id in ids:
                if reward_id not in candidates:
                    raise PassError('A selected offer does not belong to this pass.')
                category, reward = candidates[reward_id]
                if reward_id in state['claimed']:
                    continue
                if not reward['free'] and not state['purchased']:
                    raise PassError('This selection includes premium rewards. Unlock the pass first.')
                if kind == 'claim' and any(r['id'] not in state['claimed'] for r in category['unlock_offers']):
                    raise PassError('Unlock this set before claiming its rewards.')
                costs[reward['currency']] += reward['cost']
                names.append(category['name'] if kind == 'unlock' else reward['name'] or reward['item_id'])
                selected.append(reward_id)
            if not selected:
                raise PassError('These rewards are already claimed.')
            for currency, amount in costs.items():
                if snapshot['balances'].get(currency, 0) < amount:
                    raise PassError('Not enough currency. This selection costs ' + costs_text(costs) + '.')
            # Place page/set completion rewards after their prerequisite rewards.
            if kind == 'claim':
                selected.sort(key=lambda rid: (
                    bool(candidates[rid][1].get('requirements', {}).get('bRequireAllOtherCategoryRewards')),
                    bool(candidates[rid][1].get('requirements', {}).get('bRequireAllOtherPageRewards')),
                    candidates[rid][1].get('requirements', {}).get('TotalRewardsNeededForUnlock', 0)))
                combined = state['claimed'] | set(selected)
                for rid in selected:
                    category, page, reward = find_context(definition, rid)
                    req = reward.get('requirements', {})
                    if req.get('bRequireAllOtherCategoryRewards') and any(r['id'] not in combined for r in rewards(category)):
                        raise PassError('Claim the other rewards in this set first.')
                    if req.get('bRequireAllOtherPageRewards') and any(r['id'] not in combined for r in page['rewards'] if r['kind']=='reward'):
                        raise PassError('Claim the other rewards on this page first.')
        else:
            raise PassError('Unsupported pass action.')
        return PassAction(self.auth.account_id, key, kind, tuple(selected), tuple(sorted(costs.items())), tuple(names), self.clock())

    def execute(self, action):
        """Only called after the user accepts the concrete action/price in the UI."""
        with _ACCOUNT_OPERATIONS:
            if not self.auth or action.account_id != self.auth.account_id or self.clock()-action.created_at > 120:
                raise PassError('This selection expired or your account changed. Refresh and select it again.')
            before = self.query()
            fresh = self.prepare(action.pass_key, action.kind, action.offer_ids, before)
            if action.account_id != self.auth.account_id:
                raise PassError('Your account changed. Refresh before continuing.')
            if fresh.offer_ids != action.offer_ids or fresh.costs != action.costs:
                raise PassError('The selected rewards or price changed. Review the updated selection before continuing.')
            definition = self.definition(action.pass_key)
            if action.kind == 'purchase':
                operation = 'PurchaseCatalogEntry'; profile_id = 'common_core'
                body = dict(offerId=action.offer_ids[0], purchaseQuantity=1, currency='MtxCurrency',
                            currencySubType='', expectedTotalPrice=dict(action.costs)['MtxCurrency'], gameContext='')
            else:
                operation = 'ExchangeGameCurrencyForSeasonPassOffer'; profile_id = 'athena'
                body = dict(offerItemIdList=list(action.offer_ids), seasonPassTemplateId=definition['template'],
                            additionalData={})
            failure = None
            try:
                self._request('POST', self._url(operation), mutation=True,
                              params={'profileId':profile_id, 'rvn':before['common' if profile_id=='common_core' else 'athena']['rvn']}, json=body)
            except PassError as exc:
                failure = str(exc)
            try:
                after = self.query()
            except PassError:
                raise PassError('The operation was sent, but its result could not be verified. Refresh before trying again.') from None
            state = after['passes'][action.pass_key]
            if action.kind == 'purchase':
                complete = state['purchased']; message = 'Pass unlocked.' if complete else 'Pass purchase was not confirmed.'
            else:
                count = len(set(action.offer_ids) & state['claimed']); complete = count == len(action.offer_ids)
                message = f'{count} of {len(action.offer_ids)} selected offers confirmed ' + ('unlocked.' if action.kind=='unlock' else 'claimed.')
            if not complete:
                message += ' ' + (failure or 'Epic has not confirmed the rest. Check the displayed requirements before trying again.')
            return after, message
