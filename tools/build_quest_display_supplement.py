"""Add live quests missing from the quest catalog, using QuestDisplayData.

The base catalog (packet_quests_4210.json) and its 42.20 supplement come from
quest definition assets, which miss quests Epic released later. The
QuestDisplayData plugin carries player-facing names, objectives and category
tags for every quest the client can show, so this tool fills the gap.

Only quests the game marks enabled are added: bIsVisibleToPlayers and
bIncludedInCategories must not be false (Sprite Mastery tiers, granters and
reward trackers are hidden this way), and the name must be real text. A quest
is added only when it is active on the reference account, or when it is a
daily quest from the same random daily pool as an active daily (same plugin,
exact QuestCategory tag, both typed AthenaDailyQuest) so tomorrow's draw is
covered too. Older seasons that reuse the same tags are left out.

    python tools/build_quest_display_supplement.py QDD_DIR QC_DIR ACTIVE_TEMPLATES.json

ACTIVE_TEMPLATES.json is a JSON list of quest template ids (Quest:...) that are
active on an account. New rows and categories are merged into
lib/data/quest_supplement_4220.json; existing rows are never overwritten.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPLEMENT = ROOT / 'lib/data/quest_supplement_4220.json'
DAILY = 'EFortQuestType::AthenaDailyQuest'
PLACEHOLDER = re.compile(r'^(quest name|name|tbd|placeholder)$|LOCTEXT|\{[^}]*\}', re.I)


def text(value):
    if not isinstance(value, dict):
        return ''
    raw = value.get('LocalizedString') or value.get('SourceString') or ''
    return ' '.join(re.sub(r'<[^>]*>', '', raw).split())


def objects(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def display_records(directory):
    """Template id -> (record, merged extension data, file path)."""
    records = {}
    for path in sorted(Path(directory).rglob('QuestDisplayData_*.json')):
        for obj in objects(path):
            if isinstance(obj, dict) and obj.get('Type') == 'FortQuestDisplayDataAsset':
                props = obj.get('Properties') or {}
                ext = {}
                for entry in props.get('ExtensionData') or []:
                    ext.update(entry)
                records[str(props.get('TemplateId', '')).lower()] = (obj, ext, path)
    return records


def enabled(ext):
    return ext.get('bIsVisibleToPlayers') is not False and ext.get('bIncludedInCategories') is not False


def quest_tags(obj):
    return [t for t in (obj.get('Properties') or {}).get('OwnedGameplayTags') or []
            if isinstance(t, str) and t.startswith('QuestCategory.')]


def row(obj, ext):
    props = obj.get('Properties') or {}
    query = props.get('ProductCompatabilityQuery') or {}
    name = text(ext.get('DisplayName'))
    return dict(
        name=name, description=text(ext.get('Description')) or name,
        asset=obj.get('Package', '') + '.' + obj.get('Name', ''),
        categories=quest_tags(obj),
        products=[t.get('TagName') for t in query.get('TagDictionary') or []],
        hidden=False, visibility=ext.get('QuestVisiblityData') or {},
        product_query=query, sort_priority=ext.get('SortPriority', 0),
        completion_count=ext.get('ObjectiveCompletionCount'),
        objectives=[dict(key=str(o.get('ObjectiveId', '')).lower(), required=o.get('Count'),
                         description=text(o.get('Description')), hidden=False, stage=-1)
                    for o in props.get('Objectives') or []],
        source='QuestDisplayData')


def categories(directory):
    """QuestCategoryData assets, in the same shape as quest_groups_4210.json."""
    result = []
    for path in sorted(Path(directory).rglob('*.json')):
        for obj in objects(path):
            if isinstance(obj, dict) and obj.get('Type') == 'QuestCategoryData':
                props = obj.get('Properties') or {}
                result.append(dict(asset=obj['Package'], name=text(props.get('DisplayName')),
                    tags=props.get('IncludeTags', []), exclude=props.get('ExcludeTags', []),
                    headers=[dict(name=text(h.get('HeaderName')), tag=(h.get('HeaderTag') or {}).get('TagName'),
                                  description=text(h.get('HeaderDescription')))
                             for h in props.get('AdditionalHeaders', [])]))
    return result


def _matches(tag, prefix):
    return tag == prefix or tag.startswith(prefix + '.')


def build(display_dir, category_dir, active_templates, catalog, supplement):
    records = display_records(display_dir)
    known = set(catalog) | set(supplement.get('rows', {}))
    active = {t.lower() for t in active_templates}

    def eligible(key):
        obj, ext, _ = records[key]
        name = text(ext.get('DisplayName'))
        return enabled(ext) and name and not PLACEHOLDER.search(name) and quest_tags(obj)

    def daily_pool(key):
        # Random daily draws: same plugin folder and exact category tag, both typed as daily quests.
        obj, ext, path = records[key]
        if ext.get('QuestType') != DAILY:
            return set()
        return {(path.parent.name, tag) for tag in quest_tags(obj)}

    pools = set().union(*(daily_pool(key) for key in active if key in records and eligible(key)))
    added, sources = {}, []
    for key, (obj, ext, path) in sorted(records.items()):
        if key in known or not eligible(key):
            continue
        if key in active or pools.intersection(daily_pool(key)):
            added[key] = row(obj, ext)
            sources.append(dict(asset=obj.get('Package', ''), sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    # Current-build categories for every tag the new rows use, replacing older copies of the same asset.
    new_tags = {tag for r in added.values() for tag in r['categories']}
    current = [c for c in categories(category_dir)
               if c['name'] and any(_matches(t, p) for t in new_tags for p in c['tags'])]
    return added, current, sources


def merge(supplement, added, current, sources, build_name):
    supplement.setdefault('rows', {}).update(added)
    replaced = {c['asset'] for c in current}
    supplement['categories'] = [c for c in supplement.get('categories', []) if c['asset'] not in replaced] + current
    supplement.setdefault('sources', []).extend(sources)
    supplement['display_supplement'] = dict(build=build_name, rows=len(added),
        rule='enabled in QuestDisplayData and active on the reference account, or in the same daily pool as an active daily')
    return supplement


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('display_dir', type=Path)
    parser.add_argument('category_dir', type=Path)
    parser.add_argument('active_templates', type=Path)
    parser.add_argument('--build', default='Release-42.20-CL-58011042')
    parser.add_argument('--output', type=Path, default=SUPPLEMENT)
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'lib/data/packet_quests_4210.json').read_text(encoding='utf-8'))['rows']
    supplement = json.loads(SUPPLEMENT.read_text(encoding='utf-8'))
    active = json.loads(args.active_templates.read_text(encoding='utf-8'))
    added, current, sources = build(args.display_dir, args.category_dir, active, catalog, supplement)
    merge(supplement, added, current, sources, args.build)
    args.output.write_text(json.dumps(supplement, indent=2, ensure_ascii=False), encoding='utf-8')
    print(len(added), 'quests added;', len(current), 'current categories written')
