"""Compile current cModdle SeasonPass exports, preserving game page/offer order.

Usage: python tools/build_pass_catalog.py EXPORTS METADATA OUTPUT
METADATA is cModdle's JSON output directory. No account data is included.
"""
import argparse
import json
from pathlib import Path


def text(value):
    return (value.get('LocalizedString') or value.get('SourceString') or '') if isinstance(value, dict) else str(value or '')


def compile_catalog(exports, metadata, tracks=None):
    tracks={v['track']['ti'].split(':')[-1].lower():v['track'] for v in (tracks or {}).values() if isinstance(v,dict) and isinstance(v.get('track'),dict) and v['track'].get('ti')}
    entries = {}; packages = {}
    for path in sorted(exports.rglob('*.json')):
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        package = next((e['Package'] for e in data if e.get('Package')), None)
        if not package:
            package = data[0]['Outer']['ObjectPath'].rsplit('.', 1)[0]
        packages[package] = data
        for i, entry in enumerate(data):
            entries[f'{package}.{i}'] = entry

    def resolve(ref):
        if 'ObjectPath' in ref:
            return entries[ref['ObjectPath']]
        path = ref['AssetPathName'].split('.')[0]
        return next(e for e in packages[path] if e.get('Package') == path)

    def metadata_entry(path):
        short = metadata / (path.replace('/', '_') + '.json')
        if short.exists():
            return json.loads(short.read_text(encoding='utf-8-sig'))[0]
        leaf = path.rsplit('/', 1)[-1]
        candidates = list(metadata.glob('*_' + leaf + '.uasset.json'))
        for candidate in candidates:
            for e in json.loads(candidate.read_text(encoding='utf-8-sig')):
                if e.get('Package') == path:
                    return e
        return {}

    def item_metadata(ref):
        path = ref.get('AssetPathName', '').split('.')[0]
        e = metadata_entry(path); pr = e.get('Properties', {})
        basepath = pr.get('cosmetic_item', {}).get('ObjectPath', '').rsplit('.', 1)[0]
        base = metadata_entry(basepath).get('Properties', {}) if basepath else {}
        tags = [t for row in (base or pr).get('DataList', []) for t in row.get('Tags', [])]
        result=dict(item_id=path.rsplit('/', 1)[-1].lower(),
                    name=text(pr.get('ItemName')) or text(base.get('ItemName')),
                    description=text(pr.get('ItemDescription')) or text(base.get('ItemDescription')),
                    item_type=text(pr.get('ItemShortDescription')) or text(base.get('ItemShortDescription')),
                    cosmetic_set=next((t for t in tags if t.startswith('Cosmetics.Set.')), ''),
                    asset=path, variant=pr.get('VariantNameTag', {}).get('TagName', ''))
        if result['item_id'] in tracks:
            track=tracks[result['item_id']]
            result.update(name=track['tt'],description='By '+track.get('an','Unknown artist'),item_type='Jam Track')
        return result

    def offer_data(offer, free=False):
        price_ref = offer['OfferPriceRowHandle']
        price = resolve(price_ref['DataTable'])['Rows'][price_ref['RowName']]
        currency = price['CurrencyItemTemplate']
        info = item_metadata(offer['RewardItem']['ItemDefinition'])
        info.update(id=offer['OfferGuid'].replace('-', '').upper(), free=free,
                    cost=price['Cost'], currency=(currency['PrimaryAssetType']['Name']+':'+currency['PrimaryAssetName']).lower(),
                    quantity=offer['RewardItem'].get('Quantity', 1),
                    extra_rewards=[item_metadata(r['ItemDefinition']) for r in offer.get('ChainedRewardItemList', [])])
        return info

    result=[]
    specs={'BattlePass':('br','Battle Royale Pass'), 'FigmentPass':('og','OG Pass'),
           'SparksPass':('festival','Festival / Music Pass'), 'JunoPass':('lego','LEGO Pass')}
    for season in [e for e in entries.values() if e['Type']=='SeasonPassItemDefinition']:
        pr=season['Properties']; key,label=specs[pr['PRMPassId']]
        pd=resolve(pr['PassData'])['Properties']
        item=dict(key=key,name=label,season_name=text(pd['SeasonName']),
                  template='AthenaSeason:'+season['Name'].lower(),storefront=pd['SeasonStorefront'],
                  purchase_offer=pd['SeasonPassOfferId'],categories=[])
        for cat_ref in pr['Categories']:
            cat=resolve(cat_ref); cp=cat['Properties']
            category=dict(id=cat['Name'],name=text(cp['Title']),group=cp.get('GroupName',''),
                          unlock_offers=[],pages=[],dependent_category='')
            if cp.get('DependentCategory'):
                category['dependent_category']=resolve(cp['DependentCategory'])['Name']
            if cp.get('Requirements'):
                for req_ref in resolve(cp['Requirements'])['Properties']['Requirements']:
                    req=resolve(req_ref)
                    if req['Type']!='SeasonPassRequirement_Offer':
                        raise ValueError('Unsupported category requirement: '+req['Type'])
                    rp=req['Properties']
                    category['unlock_offers'].append(offer_data(rp['Offer'],rp.get('bIsFreePassOffer',False)))
            for page_ref in cp['Pages']:
                page=resolve(page_ref); rows=[]
                for reward_ref in page['Properties']['PageGrid']['RewardEntryList']:
                    reward=resolve(reward_ref); rp=reward['Properties']
                    if reward['Type']=='AthenaSeasonItemEntryQuest':
                        rows.append(dict(id=page['Name']+':'+reward['Name'],kind='quest',
                            name=text(rp.get('DisclaimerHeader')) or 'Quest reward',
                            description=text(rp.get('DisclaimerText')) or 'Earn this reward by completing its quests.',
                            quest=rp.get('SpecificQuestItem',{}).get('AssetPathName',''),item_type='Quest reward'))
                        rows[-1]['quest_bundle']=rp.get('ChallengeBundleSoftObjPtr',{}).get('AssetPathName','')
                        continue
                    assert reward['Type']=='AthenaSeasonItemEntryReward',reward['Type']
                    row=offer_data(rp['BattlePassOffer'],rp.get('bIsFreePassReward',False))
                    row.update(kind='reward',requirements={k:rp[k] for k in ['bRequireAllOtherPageRewards','bRequireAllOtherCategoryRewards','RewardsNeededForUnlock','TotalRewardsNeededForUnlock','TotalPassRewardsNeededForUnlock'] if k in rp})
                    rows.append(row)
                category['pages'].append(dict(id=page['Name'],rewards=rows))
            item['categories'].append(category)
        result.append(item)
    result.sort(key=lambda p:['br','og','festival','lego'].index(p['key']))
    assert len(result)==4
    return dict(schema=1,build='Release-42.20+cl58003952',generated='2026-09-24',passes=result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exports',type=Path);parser.add_argument('metadata',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--tracks',type=Path)
    args=parser.parse_args()
    result=compile_catalog(args.exports,args.metadata,json.loads(args.tracks.read_text()) if args.tracks else None)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    for p in result['passes']:
        print(p['name'],sum(len(c['pages']) for c in p['categories']),'pages',sum(len(g['rewards']) for c in p['categories'] for g in c['pages']),'entries')
