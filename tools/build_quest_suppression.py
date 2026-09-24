"""Extract explicit bundle suppression lists from cooked cModdle JSON exports."""
import argparse,json
from pathlib import Path


def build(directory):
    bundles={}
    for path in directory.rglob('*.json'):
        if 'bundle' not in path.name.lower():continue
        try:data=json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError,OSError):continue
        if not isinstance(data,list):continue
        for entry in data:
            if entry.get('Type')!='FortChallengeBundleItemDefinition':continue
            refs=entry.get('Properties',{}).get('SuppressedQuestDefs',[])
            if refs:
                bundles['challengebundle:'+entry['Name'].lower()]=sorted({
                    'quest:'+r['AssetPathName'].split('.')[0].rsplit('/',1)[-1].lower() for r in refs if r.get('AssetPathName')})
    return dict(source='Cooked FortChallengeBundleItemDefinition.SuppressedQuestDefs',bundles=bundles)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('exports',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args();data=build(args.exports)
    args.output.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(len(data['bundles']),'bundle suppression lists')
