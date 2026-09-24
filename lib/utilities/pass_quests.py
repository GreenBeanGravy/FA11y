"""Join explicit pass quest references to the existing account quest reader."""
from lib.utilities.epic_quests import parse_profile_response
from lib.utilities.quest_presentation import prepare_quests, details_text, list_label


def template_from_asset(asset, kind):
    if not asset:
        return ''
    return kind.lower()+':'+asset.split('.')[0].rsplit('/',1)[-1].lower()


def pass_quest_snapshot(profile, now):
    snapshot=parse_profile_response({'profileChanges':[{'changeType':'fullProfileUpdate','profile':profile}]},now=now)
    bundles={key:item.get('templateId','').lower() for key,item in profile.get('items',{}).items()
             if item.get('templateId','').lower().startswith('challengebundle:')}
    # Preserve the full reader snapshot so the normal quest browser can merge
    # newer packet observations, apply visibility, and filter completion state.
    snapshot['bundle_templates']=bundles
    return snapshot


def related_templates(reward, snapshot):
    target=template_from_asset(reward.get('quest',''),'Quest')
    bundle=template_from_asset(reward.get('quest_bundle',''),'ChallengeBundle')
    result={target} if target else set()
    if snapshot and bundle:
        bundle_ids={key for key,value in snapshot.get('bundle_templates',{}).items() if value==bundle}
        result.update(q['template'].lower() for q in snapshot['quests'] if q.get('bundle_id') in bundle_ids)
    return result


def linked_quests(reward, snapshot):
    if not snapshot:
        return []
    allowed=related_templates(reward,snapshot)
    # Pass-only quests are deliberately hidden from the general quest screen.
    # Exact game-authored links authorize displaying them in this context.
    rows,_,_=prepare_quests(snapshot['quests'],contextual_templates=allowed)
    target=template_from_asset(reward.get('quest',''),'Quest')
    return sorted([q for q in rows if q['template'].lower() in allowed],key=lambda q:q['template'].lower()!=target)


def pass_quest_status(reward,snapshot):
    rows=linked_quests(reward,snapshot)
    target=template_from_asset(reward.get('quest',''),'Quest')
    exact=[q for q in rows if q['template'].lower()==target]
    if len(exact)==1:
        q=exact[0]
        return ('Expired: ' if q.get('expired') else '')+list_label(q)
    if rows:
        active=sum(q['state'].lower()=='active' and not q.get('expired') for q in rows)
        completed=sum(q['state'].lower() in ('completed','claimed') for q in rows)
        return f'{active} active and {completed} completed linked quests'
    return 'Quest status not reported; it may be locked or not currently available'


def pass_quest_details(reward,snapshot):
    rows=linked_quests(reward,snapshot)
    if not rows:
        return pass_quest_status(reward,snapshot)+'. Missing quests are not treated as completed.'
    return '\n\n'.join(details_text(q) for q in rows)
