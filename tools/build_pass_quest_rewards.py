"""Extract quest reward names from exported quest and variant-token properties."""
import argparse
import json
from pathlib import Path

def build(root):
    items={}
    for p in root.glob('*CosmeticVariantTokens*VTID*.json'):
        for e in json.loads(p.read_text(encoding='utf-8')):
            text=e.get('Properties',{}).get('ItemName',{})
            name=text.get('LocalizedString') or text.get('SourceString')
            if name:items[e['Name']]=name
    rows={}
    for p in root.glob('*BattlePassS42_PassQuestPrereqs*QuestItems*.json'):
        data=json.loads(p.read_text(encoding='utf-8'))
        quest=next((e for e in data if e['Type'].startswith('FortQuestItemDefinition')),None)
        if not quest:continue
        names=[]
        def walk(value):
            if isinstance(value,dict):
                ref=value.get('AssetPathName','')
                name=items.get(ref.rsplit('.',1)[-1])
                if name and name not in names:names.append(name)
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
        for entry in data:
            if 'Rewards' in entry.get('Type',''):walk(entry.get('Properties',{}))
        if names:rows['quest:'+quest['Name'].lower()]={'name':', '.join(names),'asset':quest.get('Package','')}
    return {'source':'Release 42.20 explicit quest reward references and variant ItemName','rows':rows}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('exports',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();data=build(args.exports)
    args.output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(len(data['rows']),'named reward trackers')
