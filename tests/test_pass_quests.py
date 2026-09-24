from lib.utilities.epic_quests import parse_profile_response,normalize_quest
from lib.utilities.pass_quests import linked_quests, related_templates, pass_quest_details
from lib.utilities.quest_presentation import prepare_quests,list_label
from lib.managers.quest_manager import QuestStore


def test_birthday_suppression_is_bound_to_actual_bundle():
    tid='Quest:quest_s42_fncsbirthday_suppressed01'
    profile=dict(profileId='athena',items={
        'bundle':dict(templateId='ChallengeBundle:questbundle_s42_birthday_01'),
        'quest':dict(templateId=tid,attributes=dict(quest_state='Active',challenge_bundle_id='bundle'))})
    response={'profileChanges':[dict(changeType='fullProfileUpdate',profile=profile)]}
    snap=parse_profile_response(response)
    assert snap['quests'][0]['suppressed']
    assert prepare_quests(snap['quests'])[0]==[]
    profile['items']['quest']['attributes']['quest_state']='Claimed'
    assert len(prepare_quests(parse_profile_response(response)['quests'])[0])==1
    profile['items']['bundle']['templateId']='ChallengeBundle:unrelated'
    assert not parse_profile_response(response)['quests'][0]['suppressed']


def quest(tid,state='Active',count=2,bundle='bundle1'):
    catalog={tid:dict(name='Do the objective',description='Test quest',objectives=[dict(key='obj0',required=3)],categories=[])}
    q=normalize_quest(tid,dict(templateId=tid,attributes=dict(quest_state=state,completion_obj0=count,challenge_bundle_id=bundle)),catalog,100)
    return q


def test_reward_links_exact_quest_and_bundle_without_other_quests(monkeypatch):
    from lib.utilities import pass_quests
    monkeypatch.setattr(pass_quests,'prepare_quests',lambda qs,**kw:([dict(q,mode='Battle Royale',modes=['Battle Royale'],category='Test') for q in qs],0,0))
    reward=dict(quest='/Game/Specific.Specific',quest_bundle='/Game/Bundle.Bundle')
    snapshot=dict(quests=[quest('quest:specific'),quest('quest:sibling'),quest('quest:other',bundle='bundle2')],bundle_templates={'bundle1':'challengebundle:bundle'})
    assert related_templates(reward,snapshot)=={'quest:specific','quest:sibling'}
    assert len(linked_quests(reward,snapshot))==2
    assert '2 of 3' in pass_quest_details(reward,snapshot)
    assert 'Missing quests are not treated as completed' in pass_quest_details(reward,None)


def test_hidden_pass_quest_is_visible_only_in_specific_reward_context():
    q=quest('quest:test');q['hidden']=True
    assert prepare_quests([q])[0]==[]
    assert len(prepare_quests([q],contextual_templates={'quest:test'})[0])==1
    q['suppressed']=True
    assert prepare_quests([q],contextual_templates={'quest:test'})[0]==[]


def test_sparse_or_stale_packet_does_not_erase_account_progress():
    store=QuestStore();store.replace_api(dict(quests=[quest('quest:test')],updated_at=100))
    store.feed_packet(dict(kind='quest_progress',received_at=101,quest=dict(template='quest:test',state=1,objectives=[])),1)
    assert store.snapshot()[1]['quests'][0]['objectives'][0]['achieved']==2
    store.replace_api(dict(quests=[quest('quest:test','Claimed',3)],updated_at=102))
    store.feed_packet(dict(kind='quest_progress',received_at=101,quest=dict(template='quest:test',state=1,objectives=[dict(id=1,achieved=2,required=3,visible=True)])),1)
    assert store.snapshot()[1]['quests'][0]['state']=='Claimed'


def test_completed_without_counter_does_not_sound_incomplete():
    q=quest('quest:test','Claimed',None)
    q.update(mode='Battle Royale',category='Test')
    assert 'Completion confirmed by Epic' in list_label(q)
    assert 'Progress not reported' not in list_label(q)
