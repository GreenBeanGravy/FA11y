"""Name every Sprite Mastery tier and show it in its own quest category.

Fortnite hides Sprite Mastery quests from the quest log and ships them without
names. Each tier's single objective, however, tracks one exact extractable
sprite tag, e.g. Sprites.Extractable.8Bit.Holofoil, so the quest can be named
from the sprite definitions (ExtractableSpriteDefinition ItemName):

    base -> 8-Bit Sprite, _01 Cheatmaster -> Cheat Master, _02 Gold, _03 Hacker -> Loot Hacker,
    _04 Candy -> Gummy, _05 Holofoil, _06 Reaper -> Bounty Hunter

The variant words below are the prefixes the game itself uses in its sprite
names (e.g. ESD_DoubleJumpSprite_Variant_Candy = "Gummy Jackrabbit Sprite",
ESD_*_Variant_Reaper = "Bounty Hunter ... Sprite"). Sprites with no name in the
installed build are skipped rather than invented.

    python tools/build_sprite_mastery_quests.py QUEST_DEFINITION_DIR SPRITE_DEFINITION_DIR
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPPLEMENT = ROOT / 'lib/data/quest_supplement_4220.json'
VARIANTS = {'base': '', 'cheatmaster': 'Cheat Master', 'gold': 'Gold', 'hacker': 'Loot Hacker',
            'candy': 'Gummy', 'holofoil': 'Holofoil', 'reaper': 'Bounty Hunter'}
# Prefixes seen in sprite ItemNames, stripped to recover the sprite's own name from any variant.
NAME_PREFIXES = ('Cheat Master ', 'Cheatmaster ', 'Gold ', 'Loot Hacker ', 'Gummy ', 'Holofoil ', 'Bounty Hunter ')
# Extractable tag keys whose sprite definition folder is spelled differently.
TAG_ALIASES = {'8bit': '8bitblaster', 'cosmicthunderdoublejump': 'doublejump'}
CATEGORY_TAG = 'QuestCategory.FA11y.SpriteMastery'
CATEGORY_ASSET = '/FA11y/SpriteMastery'
PRODUCT_QUERY = {'TagDictionary': [{'TagName': 'Product.BR'}], 'QueryTokenStream': [0, 1, 1, 1, 0],
                 'AutoDescription': ' ANY( Product.BR )'}


def load(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def text(value):
    return ' '.join(((value or {}).get('LocalizedString') or (value or {}).get('SourceString') or '').split())


def sprite_names(sprite_dir):
    """Lower-case definition key ('8bitblastersprite') -> sprite name without variant or 'Sprite'."""
    names = {}
    for path in sorted(Path(sprite_dir).rglob('ESD_*.json')):
        for obj in load(path):
            name = text((obj.get('Properties') or {}).get('ItemName'))
            if not name:
                continue
            key = re.sub(r'_Variant_.*$', '', obj['Name'])[4:].lower()
            base = name
            for prefix in NAME_PREFIXES:
                if base.startswith(prefix):
                    base = base[len(prefix):]
            base = re.sub(r'\s+Sprite$', '', base)
            # A base definition's own name wins over one recovered from a variant.
            if key not in names or '_Variant_' not in obj['Name']:
                names[key] = base
    return names


def sprite_for(tag_key, names, fallback):
    key = TAG_ALIASES.get(tag_key.lower(), tag_key.lower())
    for candidate in (key, key + 'sprite'):
        if candidate in names:
            return names[candidate]
    return fallback


def build(definition_dir, sprite_dir, catalog):
    names = sprite_names(sprite_dir)
    # Families already named in an older catalog (e.g. Squibbly) keep that name when the build lacks one.
    old = {}
    for key, row in catalog.items():
        match = re.match(r'quest:quest_s42_spritemastery_([a-z0-9]+)$', key)
        name = (row.get('name') or '').removeprefix('Sprite Mastery - ')
        if match and name and not re.search(r'\[|placeholder', name, re.I):
            old[match.group(1)] = name
    rows, headers, skipped = {}, {}, set()
    for path in sorted(Path(definition_dir).rglob('Quest_S42_SpriteMastery_*.json')):
        objects = load(path)
        quest = next((o for o in objects if 'Objectives' in (o.get('Properties') or {})), None)
        if not quest:
            continue
        raw = json.dumps(quest)
        tags = sorted(set(re.findall(r'Sprites\.Extractable\.(\w+)\.(\w+)', raw)))
        family = re.match(r'quest_s42_spritemastery_([a-z0-9]+?)(?:_\d\d)?$', quest['Name'].lower())
        if len(tags) != 1 or not family or tags[0][1].lower() not in VARIANTS:
            skipped.add(quest['Name'])
            continue
        tag_key, variant = tags[0]
        sprite = sprite_for(tag_key, names, old.get(family.group(1)))
        if not sprite:
            skipped.add(quest['Name'])
            continue
        full = ' '.join(filter(None, (VARIANTS[variant.lower()], sprite)))
        article = 'an' if re.match(r'[aeiou]|8|11|18', full, re.I) else 'a'
        header_tag = f'{CATEGORY_TAG}.{family.group(1)}'
        headers[header_tag] = sprite
        objectives = [dict(key=o.get('BackendName', '').lower(), required=o.get('Count'),
                           description=f'Extract {article} {full} Sprite', hidden=False, stage=-1)
                      for o in quest['Properties']['Objectives']]
        rows['quest:' + quest['Name'].lower()] = dict(
            name='Sprite Mastery - ' + full, description=f'Extract {article} {full} Sprite to master it.',
            asset=quest.get('Package', '') + '.' + quest['Name'], categories=[header_tag],
            products=['Product.BR'], hidden=False, visibility={}, product_query=PRODUCT_QUERY,
            sort_priority=list(VARIANTS).index(variant.lower()), completion_count=None,
            objectives=objectives, source='SpriteMastery')
    category = dict(asset=CATEGORY_ASSET, name='Sprite Mastery', tags=[CATEGORY_TAG], exclude=[],
                    headers=[dict(name=name, tag=tag, description='')
                             for tag, name in sorted(headers.items(), key=lambda item: item[1].casefold())])
    return rows, category, sorted(skipped)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('definition_dir', type=Path)
    parser.add_argument('sprite_dir', type=Path)
    args = parser.parse_args()
    catalog = json.loads((ROOT / 'lib/data/packet_quests_4210.json').read_text(encoding='utf-8'))['rows']
    supplement = json.loads(SUPPLEMENT.read_text(encoding='utf-8'))
    rows, category, skipped = build(args.definition_dir, args.sprite_dir, catalog)
    # These rows deliberately replace the older hidden, sometimes placeholder-named catalog rows.
    supplement['rows'].update(rows)
    supplement['categories'] = [c for c in supplement['categories'] if c['asset'] != CATEGORY_ASSET] + [category]
    SUPPLEMENT.write_text(json.dumps(supplement, indent=2, ensure_ascii=False), encoding='utf-8')
    print(len(rows), 'Sprite Mastery quests named;', len(category['headers']), 'sprites')
    if skipped:
        print('Skipped (no sprite name in this build):', ', '.join(skipped))
