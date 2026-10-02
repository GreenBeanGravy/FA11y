"""Horde rank entitlements and objective progress from the Epic account API."""
import json
import time
from functools import lru_cache
from pathlib import Path
from lib.utilities.epic_quests import EpicQuestAPI, QuestQueryError

@lru_cache(maxsize=1)
def rank_catalog():
    return json.loads((Path(__file__).resolve().parents[1]/'data/horde_ranks_4230.json').read_text(encoding='utf-8'))['rows']

def _counter(value):
    return value if type(value) is int and 0 <= value <= 1000000000 else None

def rank_snapshot(response, now=None):
    profiles=[c.get('profile') for c in response.get('profileChanges',[])
              if c.get('changeType')=='fullProfileUpdate' and isinstance(c.get('profile'),dict)]
    if len(profiles)!=1 or profiles[0].get('profileId')!='athena':
        raise QuestQueryError('Epic did not return a complete Horde rank profile. Refresh to retry.')
    profile=profiles[0]
    items={v.get('templateId','').lower():v for v in profile.get('items',{}).values()}
    catalog=rank_catalog()
    unlocked=[r['rank'] for r in catalog if (_counter(items.get(r['token'],{}).get('quantity')) or 0)>0]
    aggregate=items.get('token:athena_s42_mashexpertise_token')
    rank=_counter(aggregate.get('quantity')) if aggregate else max(unlocked,default=0)
    if rank is None or rank>len(catalog) or unlocked and max(unlocked)!=rank:
        raise QuestQueryError('Epic returned inconsistent Horde rank data. Refresh to retry.')
    current=catalog[rank-1] if rank else None
    next_rank=catalog[rank] if rank<len(catalog) else None
    achieved=None
    if next_rank and next_rank['required'] is not None:
        attributes=items.get(next_rank['quest'],{}).get('attributes',{})
        achieved=_counter(attributes.get('completion_'+next_rank['objective'].lower()))
    remaining=(max(0,next_rank['required']-achieved)
               if next_rank and next_rank['required'] is not None and achieved is not None else None)
    return dict(rank=rank,current=current,next_rank=next_rank,achieved=achieved,remaining=remaining,
                updated_at=time.time() if now is None else now,source='epic_account_api')

def rank_text(snapshot=None, error=None):
    lines=[]
    if error:
        lines.append(error)
    elif snapshot:
        current=snapshot['current']; next_rank=snapshot['next_rank']
        lines.append('Current Horde rank: '+(current['name'] if current else 'No rank unlocked yet.'))
        if current:
            lines.extend(['Current benefits:',current['benefits']])
            if current.get('exact_description'):lines.extend(['Exact values:',current['exact_description']])
        if next_rank:
            lines.append('Next: '+next_rank['name'])
            if next_rank['required'] is None:
                lines.append('Requirement: '+next_rank['requirement'])
            elif snapshot['achieved'] is None:
                lines.append(f"Target: {next_rank['required']:,} total Horde eliminations. Your progress was not reported.")
            else:
                lines.append(f"Progress: {snapshot['achieved']:,} of {next_rank['required']:,} Horde eliminations.")
                lines.append(f"{snapshot['remaining']:,} more needed." if snapshot['remaining'] else
                             'Target reached; the next rank has not yet been reported as unlocked.')
            lines.extend(['Next rank benefits:',next_rank['benefits']])
            if next_rank.get('exact_description'):lines.extend(['Exact values:',next_rank['exact_description']])
        else:
            lines.append('Maximum Horde rank reached.')
        lines.append('Source: Epic account API. Refresh Account Information after a match to update.')
    else:
        lines.append('Your Horde rank has not been loaded.')
    lines.extend(['','All Horde ranks (benefits at each rank):'])
    for row in rank_catalog():
        requirement=(f"{row['required']:,} total Horde eliminations" if row['required'] is not None
                     else row['requirement'])
        lines.extend(['',row['name']+' — '+requirement,row['benefits']])
        if row.get('exact_description'):lines.extend(['Exact values:',row['exact_description']])
    return '\n'.join(lines)

class HordeRankAPI:
    def __init__(self, auth, session=None, clock=None):
        self.api=EpicQuestAPI(auth,session,clock)

    def query(self):
        return rank_snapshot(self.api.query_full_profile(),self.api.clock())
