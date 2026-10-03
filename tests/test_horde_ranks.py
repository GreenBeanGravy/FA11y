import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from lib.utilities.horde_ranks import rank_snapshot, rank_text, rank_catalog, HordeRankAPI
from lib.utilities.epic_quests import QuestQueryError

FIXTURE=json.loads((Path(__file__).parent/'fixtures/horde_rank_api_4230.json').read_text())

def test_current_account_rank_progress_and_next_unlock_from_live_api_fixture():
    snapshot=rank_snapshot(FIXTURE,100)
    assert snapshot['rank']==3
    assert snapshot['achieved']==473 and snapshot['remaining']==127
    assert snapshot['next_rank']['rank']==4
    text=rank_text(snapshot)
    assert 'Hunter Rank 3' in text and '473 of 600' in text and '127 more needed.' in text
    assert 'Ammo on match start' in text
    assert len(rank_catalog())==20 and rank_catalog()[-1]['required']==8850

def test_missing_progress_is_not_reported_as_zero():
    response=copy.deepcopy(FIXTURE)
    for item in response['profileChanges'][0]['profile']['items'].values():
        if item['templateId'].lower()=='quest:quest_s42_ltm_mash_q04': item['attributes']={}
    snapshot=rank_snapshot(response)
    assert snapshot['achieved'] is None and snapshot['remaining'] is None
    assert 'Your progress was not reported.' in rank_text(snapshot)

def test_partial_response_and_conflicting_entitlements_fail_explicitly():
    with pytest.raises(QuestQueryError): rank_snapshot({'profileChanges':[]})
    response=copy.deepcopy(FIXTURE)
    for item in response['profileChanges'][0]['profile']['items'].values():
        if item['templateId'].lower()=='token:athena_s42_mashexpertise_token': item['quantity']=20
    with pytest.raises(QuestQueryError): rank_snapshot(response)

def test_highest_rank_has_no_next_rank_and_catalog_remains_readable_without_login():
    response={'profileChanges':[dict(changeType='fullProfileUpdate',profile=dict(profileId='athena',items={
        'x':dict(templateId='Token:athena_s42_mashexpertise_token',quantity=20)}))]}
    assert 'Maximum Horde rank reached.' in rank_text(rank_snapshot(response))
    assert 'Hunter Rank 20' in rank_text(error='Sign in to load your rank.')

def test_api_is_read_only_full_athena_query_with_existing_refresh_handling():
    auth=SimpleNamespace(account_id='test-account',access_token='test-token',MCP_URL='https://example.invalid/profile')
    response=Mock(status_code=200);response.json.return_value=FIXTURE
    session=Mock();session.post.return_value=response
    assert HordeRankAPI(auth,session,lambda:100).query()['rank']==3
    args,kwargs=session.post.call_args
    assert args[0].endswith('/client/QueryProfile')
    assert kwargs['json']=={} and kwargs['params']=={'profileId':'athena','rvn':-1}
