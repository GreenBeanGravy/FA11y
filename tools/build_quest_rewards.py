"""Build lib/data/quest_rewards_*.json: the rewards Fortnite shows for each quest.

Primary source is the QuestDisplayData plugin (FortQuestDisplayDataAsset ->
RewardInfo), which is what the in-game quest screen reads: StandardRewards are
the visible rewards with XP already resolved, HiddenRewards are never shown,
and PremiumRewards are extra rewards gated behind a token (for example the
Battle Pass premium track). Quests without a display record fall back to the
FortQuestDefinitionComponent_Rewards on the quest definition itself.

Names come from the exported item definitions (ItemName / ItemShortDescription),
so the output matches the installed build. Usage, with cModdle "properties"
exports on disk:

    python tools/build_quest_rewards.py QUEST_DISPLAY_DATA_DIR ITEM_DIR [ITEM_DIR ...]
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
XP_RESOURCES = {'athenaseasonalxp'}
VBUCKS = {'mtxcomplimentary', 'mtxgiveaway', 'mtxpurchased', 'mtxpurchasebonus', 'currency_mtxswap'}
# Unlock tokens whose owner is known; other premium gates are described generically.
PREMIUM_GATES = {'battlepasss42_seasonpass_premiumtoken': 'Battle Pass'}
# Item types whose definitions carry no short description of what they are.
DEFAULT_CATEGORIES = {
    'JunoBuildingPropAccountItemDefinition': 'LEGO decor',
    'JunoBuildingSetAccountItemDefinition': 'LEGO build',
    'FortHomebaseBannerIconItemDefinition': 'Banner Icon',
    'AthenaItemWrapDefinition': 'Wrap',
    'AthenaSprayItemDefinition': 'Spray',
    'AthenaEmojiItemDefinition': 'Emoticon',
    'AthenaDanceItemDefinition': 'Emote',
    'AthenaLoadingScreenItemDefinition': 'Loading Screen',
    'AthenaBackpackItemDefinition': 'Back Bling',
    'AthenaPickaxeItemDefinition': 'Pickaxe',
    'AthenaCharacterItemDefinition': 'Outfit',
    'AthenaGliderItemDefinition': 'Glider',
    'AthenaSkyDiveContrailItemDefinition': 'Contrail',
    'AthenaMusicPackItemDefinition': 'Music',
}
# Visible reward types that are internal bookkeeping, not something a player receives.
SKIPPED_TYPES = {'token', 'challengebundle', 'none'}


def text(value):
    if not isinstance(value, dict):
        return ''
    raw = value.get('LocalizedString') or value.get('SourceString') or ''
    return ' '.join(re.sub(r'<[^>]*>', '', raw).split())


def load_objects(path):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


class ItemIndex:
    """Every exported object by lower-case name, following redirectors."""

    def __init__(self, directories):
        self.objects = {}
        self.files = {}  # package (file) name -> every object in it, components included
        for directory in directories:
            for path in Path(directory).rglob('*.json'):
                objects = [o for o in load_objects(path) if isinstance(o, dict) and o.get('Name')]
                if objects:
                    self.files.setdefault(path.stem.lower(), objects)
                for obj in objects:
                    self.objects.setdefault(obj['Name'].lower(), obj)

    def get(self, name, depth=0):
        obj = self.objects.get((name or '').lower())
        if obj and obj.get('Type') == 'ObjectRedirector' and depth < 4:
            target = (obj.get('DestinationObject') or {}).get('ObjectPath', '')
            return self.get(target.rsplit('/', 1)[-1].split('.')[0], depth + 1)
        return obj

    def row(self, table, row_name):
        obj = self.get(table)
        rows = (obj or {}).get('Rows') or {}
        for key, value in rows.items():
            if key.lower() == (row_name or '').lower():
                return value
        return None


def asset_name(reference):
    """'/Plugin/Path/Name.Name' or "Type'Name'" -> Name."""
    if not isinstance(reference, dict):
        return ''
    path = reference.get('AssetPathName') or reference.get('ObjectPath') or ''
    return path.rsplit('/', 1)[-1].split('.')[0]


class RewardResolver:
    def __init__(self, items, quest_names):
        self.items = items
        self.quest_names = quest_names
        self.unresolved = set()

    def item(self, kind, name, quantity):
        """One visible reward as a dict, or None when it is not player-facing."""
        kind_l, name_l = (kind or '').lower(), (name or '').lower()
        if kind_l in SKIPPED_TYPES or not name_l or name_l == 'none':
            return None
        if name_l in XP_RESOURCES:
            return dict(type='xp', quantity=quantity)
        if name_l in VBUCKS:
            return dict(type='resource', name='V-Bucks', quantity=quantity)
        if kind_l == 'quest':
            quest = self.quest_names.get('quest:' + name_l)
            return dict(type='quest', name=quest) if quest else dict(type='quest')
        obj = self.items.get(name)
        props = (obj or {}).get('Properties') or {}
        title = text(props.get('ItemName'))
        if not title:
            self.unresolved.add(f'{kind}:{name}')
            return None
        if obj['Type'] == 'FortVariantTokenType':
            cosmetic = self.items.get(asset_name(props.get('cosmetic_item')))
            cosmetic_props = (cosmetic or {}).get('Properties') or {}
            reward = dict(type='style', name=title, category=text(props.get('ItemShortDescription')) or 'Style')
            if text(cosmetic_props.get('ItemName')):
                reward.update(cosmetic=text(cosmetic_props['ItemName']),
                              cosmetic_category=text(cosmetic_props.get('ItemShortDescription'))
                              or DEFAULT_CATEGORIES.get(cosmetic['Type'], ''))
            return reward
        if kind_l in ('accountresource', 'currency') or obj['Type'] == 'FortPersistentResourceItemDefinition':
            return dict(type='resource', name=title, quantity=quantity)
        category = text(props.get('ItemShortDescription')) or DEFAULT_CATEGORIES.get(obj['Type'], '')
        reward = dict(type='item', name=title, category=category)
        if quantity and quantity != 1:
            reward['quantity'] = quantity
        return reward

    def display_rewards(self, info):
        rewards = []
        for entry in info.get('StandardRewards') or []:
            asset = entry.get('ItemPrimaryAssetId') or {}
            reward = self.item(((asset.get('PrimaryAssetType') or {}).get('Name')),
                               asset.get('PrimaryAssetName'), entry.get('Quantity', 1))
            if reward:
                rewards.append(reward)
        for premium in info.get('PremiumRewards') or []:
            inner = []
            for entry in premium.get('Rewards') or []:
                asset = entry.get('ItemPrimaryAssetId') or {}
                reward = self.item(((asset.get('PrimaryAssetType') or {}).get('Name')),
                                   asset.get('PrimaryAssetName'), entry.get('Quantity', 1))
                if reward:
                    inner.append(reward)
            if inner:
                gate = ((premium.get('RequiredTokenId') or {}).get('PrimaryAssetName') or '').lower()
                rewards.append(dict(type='premium', requires=PREMIUM_GATES.get(gate, ''), rewards=inner))
        return rewards

    def definition_rewards(self, objects):
        """Fallback for quests without a display record: the quest's own rewards component."""
        rewards = []
        for obj in objects:
            if obj.get('Type') != 'FortQuestDefinitionComponent_Rewards':
                continue
            for group in (obj.get('Properties') or {}).get('QuestRewardsArray') or []:
                for entry in group.get('ResourceDataTableRewards') or []:
                    handle = entry.get('TableRowEntry') or {}
                    row = self.items.row(asset_name(handle.get('DataTable')), handle.get('RowName'))
                    if entry.get('bHideFromUI') or not row or row.get('bIsVisibleToPlayer') is False:
                        continue
                    reward = self.item('AccountResource', asset_name(row.get('ResourceDefinition')), row.get('Quantity', 0))
                    if reward and reward.get('quantity') != 0:
                        rewards.append(reward)
                for entry in group.get('Rewards') or []:
                    if entry.get('bHideFromUI'):
                        continue
                    name = asset_name(entry.get('ItemDefinition'))
                    obj_type = (self.items.get(name) or {}).get('Type', '')
                    reward = self.item('Token' if obj_type == 'FortTokenType' else '', name, entry.get('ItemCount', 1))
                    if reward:
                        rewards.append(reward)
        return rewards


def catalog_rows():
    rows = json.loads((ROOT / 'lib/data/packet_quests_4210.json').read_text(encoding='utf-8'))['rows']
    supplement = ROOT / 'lib/data/quest_supplement_4220.json'
    if supplement.exists():
        rows.update(json.loads(supplement.read_text(encoding='utf-8'))['rows'])
    return rows


def display_names(display_dir):
    """Quest names from display records, covering unlocked quests the catalog lacks."""
    names = {}
    for path in Path(display_dir).rglob('*.json'):
        for obj in load_objects(path):
            if isinstance(obj, dict) and obj.get('Type') == 'FortQuestDisplayDataAsset':
                props = obj.get('Properties') or {}
                for entry in props.get('ExtensionData') or []:
                    if text(entry.get('DisplayName')):
                        names[str(props.get('TemplateId', '')).lower()] = text(entry['DisplayName'])
    return names


def build(display_dir, item_dirs, build_name):
    catalog = catalog_rows()
    quest_names = display_names(display_dir)
    quest_names.update({key: row['name'] for key, row in catalog.items() if row.get('name')})
    items = ItemIndex([*item_dirs, display_dir])
    resolver = RewardResolver(items, quest_names)
    rows, display_keys = {}, set()
    for path in sorted(Path(display_dir).rglob('*.json')):
        for obj in load_objects(path):
            if not isinstance(obj, dict) or obj.get('Type') != 'FortQuestDisplayDataAsset':
                continue
            props = obj.get('Properties') or {}
            key = str(props.get('TemplateId', '')).lower()
            if key not in catalog:
                continue
            display_keys.add(key)
            info = next((e['RewardInfo'] for e in props.get('ExtensionData') or [] if 'RewardInfo' in e), None)
            rewards = resolver.display_rewards(info) if info else []
            if rewards:
                rows[key] = rewards
    fallback = 0
    for key, row in catalog.items():
        if key in display_keys:
            continue
        objects = items.files.get(row.get('asset', '').rsplit('.', 1)[-1].lower())
        if not objects:
            continue
        rewards = resolver.definition_rewards(objects)
        if rewards:
            rows[key] = rewards
            fallback += 1
    return dict(build=build_name,
                source='QuestDisplayData RewardInfo (standard and premium rewards; hidden rewards excluded), '
                       'quest definition reward components as fallback, names from item definitions',
                rows=dict(sorted(rows.items()))), resolver.unresolved, fallback


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('display_dir', type=Path)
    parser.add_argument('item_dirs', type=Path, nargs='+')
    parser.add_argument('--build', default='Release-42.20-CL-58011042')
    parser.add_argument('--output', type=Path, default=ROOT / 'lib/data/quest_rewards_4220.json')
    args = parser.parse_args()
    data, unresolved, fallback = build(args.display_dir, args.item_dirs, args.build)
    args.output.write_text(json.dumps(data, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    print(len(data['rows']), 'quests with rewards;', fallback, 'from quest definitions')
    if unresolved:
        print('Unresolved reward names:', ', '.join(sorted(unresolved)))
