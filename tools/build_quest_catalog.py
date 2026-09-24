"""Build readable quest metadata from cModdle's exported current assets."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def localized(value):
    if not isinstance(value, dict):
        return ''
    return value.get('LocalizedString') or value.get('SourceString') or value.get('CultureInvariantString') or ''


def build(directory, build_name='Release-42.10+cl57819925'):
    rows, sources = {}, []
    for path in sorted(directory.rglob('*.json')):
        if 'quest' not in path.name.lower() and '_q_' not in path.name.lower():
            continue
        raw = path.read_bytes()
        try:
            objects = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(objects, list):
            continue
        for obj in objects:
            kind = str(obj.get('Type', ''))
            if not (kind.startswith('FortQuestItemDefinition') or kind == 'AthenaDailyQuestDefinition'):
                continue
            props = obj.get('Properties', {})
            name = localized(props.get('ItemName'))
            template = 'Quest:' + obj['Name'].lower()
            tags = [tag for part in props.get('DataList', []) for tag in part.get('Tags', []) if isinstance(tag, str)]
            categories = [tag for tag in tags if tag.startswith('QuestCategory.')]
            products = [v.get('TagName') for v in props.get('ProductCompatibilityQuery', {}).get('TagDictionary', [])]
            visibility = {}
            for component in objects:
                if component.get('Type') == 'FortQuestDefinitionComponent_DisplaySettings':
                    visibility = component.get('Properties', {}).get('VisibilitySettings', {})
            hidden = (not name or bool(props.get('bHidden', False))
                      or visibility.get('bIsVisibleToPlayers') is False
                      or visibility.get('bIncludedInCategories') is False
                      or any('Hidden' in tag.split('.') for tag in categories))
            # Rich-text icons have no useful spoken content. Keep their accompanying text.
            clean = lambda text: ' '.join(re.sub(r'<[^>]*>', '', text).split())
            rows[template.lower()] = dict(name=name, description=localized(props.get('ItemDescription')),
                asset=obj['Package'] + '.' + obj['Name'], categories=categories,
                products=products, hidden=hidden, visibility=visibility.get('QuestVisiblityData', {}),
                product_query=props.get('ProductCompatibilityQuery', {}),
                sort_priority=props.get('SortPriority', 0),
                completion_count=props.get('ObjectiveCompletionCount'),
                objectives=[dict(key=o.get('BackendName', '').lower(), required=o.get('Count'),
                    description=localized(o.get('Description')), hidden=bool(o.get('bHidden', False)),
                    stage=o.get('Stage')) for o in props.get('Objectives', [])])
            rows[template.lower()]['name'] = clean(name)
            rows[template.lower()]['description'] = clean(rows[template.lower()]['description'])
            sources.append(dict(asset=obj['Package'], sha256=hashlib.sha256(raw).hexdigest()))
    return dict(build=build_name, sources=sources, rows=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, default=Path('lib/data/packet_quests_4210.json'))
    args = parser.parse_args()
    result = build(args.directory)
    args.output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(len(result['rows']), 'readable quest definitions')
