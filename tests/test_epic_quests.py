from types import SimpleNamespace

import pytest

from lib.utilities.epic_quests import EpicQuestAPI, QuestQueryError, parse_profile_response, quest_progress_text
from lib.managers.quest_manager import QuestStore

CAT = {'quest:test': dict(name='Search containers', description='Search ten containers',
                         objectives=[dict(key='test_obj0', required=10)], categories=['Weekly'])}


def response(state='Active', count=5):
    attributes = dict(quest_state=state, completion_test_obj0=count)
    return dict(profileChanges=[dict(changeType='fullProfileUpdate', profile=dict(profileId='athena', rvn=7,
        items={'quest-instance': dict(templateId='Quest:test', attributes=attributes),
               'cosmetic': dict(templateId='AthenaCharacter:test', attributes={})}))])


def test_profile_is_quest_only_and_preserves_actual_state():
    result = parse_profile_response(response(), CAT, now=100)
    assert len(result['quests']) == 1
    quest = result['quests'][0]
    assert quest['name'] == 'Search containers'
    assert quest_progress_text(quest) == '5 of 10'
    assert quest['state'] == 'Active'
    # Reaching a count does not invent a server completion state.
    assert parse_profile_response(response(count=10), CAT)['quests'][0]['state'] == 'Active'


def test_missing_counter_and_unknown_target_are_not_fabricated():
    data = response()
    del data['profileChanges'][0]['profile']['items']['quest-instance']['attributes']['completion_test_obj0']
    quest = parse_profile_response(data, CAT)['quests'][0]
    assert quest['objectives'][0]['achieved'] is None
    assert 'not reported' in quest_progress_text(quest)
    quest = parse_profile_response(response(), {})['quests'][0]
    assert not quest['metadata_available']
    assert quest_progress_text(quest) == '5; target unavailable'


@pytest.mark.parametrize('data', [{}, {'profileChanges': []},
    {'profileChanges': [{'changeType': 'itemAttrChanged'}]},
    {'profileChanges': [{'changeType': 'fullProfileUpdate', 'profile': {'profileId': 'campaign'}}]}])
def test_incomplete_or_wrong_profile_is_rejected(data):
    with pytest.raises(QuestQueryError):
        parse_profile_response(data, CAT)


def test_query_uses_only_read_operation_and_refreshes_once():
    sent, refreshed = [], []
    auth = SimpleNamespace(account_id='test-account', access_token='test-token', MCP_URL='https://example.invalid/profile')
    auth.refresh_access_token = lambda: refreshed.append(True) or True
    replies = iter([SimpleNamespace(status_code=401), SimpleNamespace(status_code=200, json=response)])
    session = SimpleNamespace(post=lambda url, **kw: sent.append((url, kw)) or next(replies))
    result = EpicQuestAPI(auth, session).query()
    assert len(result['quests']) == 1 and len(refreshed) == 1
    assert len(sent) == 2
    for url, kwargs in sent:
        assert url.endswith('/test-account/client/QueryProfile')
        assert kwargs['params'] == dict(profileId='athena', rvn=-1)
        assert kwargs['json'] == {}


@pytest.mark.parametrize('code', [403, 429, 500])
def test_api_errors_do_not_expose_response_body(code):
    auth = SimpleNamespace(account_id='test-account', access_token='test-token', MCP_URL='https://example.invalid/profile')
    session = SimpleNamespace(post=lambda *a, **k: SimpleNamespace(status_code=code, text='private-data'))
    with pytest.raises(QuestQueryError) as error:
        EpicQuestAPI(auth, session).query()
    assert 'private-data' not in str(error.value)
    assert 'test-account' not in str(error.value)


def test_packet_overlay_and_match_reset_do_not_overwrite_account_identity():
    store = QuestStore()
    store.replace_api(parse_profile_response(response(), CAT, now=100))
    event = dict(kind='quest_progress', received_at=101, quest=dict(template='Quest:test', state=1,
        objectives=[dict(id=42, achieved=6, required=10, visible=True)]))
    store.feed_packet(event, 1)
    quest = store.snapshot()[1]['quests'][0]
    assert quest['id'] == 'quest-instance' and quest['name'] == 'Search containers'
    assert quest_progress_text(quest) == '6 of 10' and quest['source'] == 'match_packets'
    # A lagging account refresh cannot roll back current-match replication.
    store.replace_api(parse_profile_response(response(), CAT, now=102))
    assert quest_progress_text(store.snapshot()[1]['quests'][0]) == '6 of 10'
    store.reset_packet(2)
    assert quest_progress_text(store.snapshot()[1]['quests'][0]) == '5 of 10'


def test_ambiguous_duplicate_template_is_not_assigned_to_wrong_instance():
    data = response()
    items = data['profileChanges'][0]['profile']['items']
    items['second-instance'] = items['quest-instance'].copy()
    store = QuestStore()
    store.replace_api(parse_profile_response(data, CAT))
    store.feed_packet(dict(kind='quest_progress', received_at=101, quest=dict(template='Quest:test', state=2,
                      objectives=[dict(id=42, achieved=10, required=10, visible=True)])), 1)
    assert all(q['state'] == 'Active' for q in store.snapshot()[1]['quests'])


def test_packet_single_objective_keeps_account_description():
    from copy import deepcopy
    catalog = deepcopy(CAT)
    catalog['quest:test']['objectives'][0]['description'] = 'Search ten containers'
    store = QuestStore()
    store.replace_api(parse_profile_response(response(), catalog, now=100))
    store.feed_packet(dict(kind='quest_progress', received_at=101,
        quest=dict(template='Quest:test', state=1, objectives=[
            dict(id=42, achieved=6, required=10, visible=True, active=True, stage=0,
                 display_stage=1, display_max=3)])), 1)
    objective = store.snapshot()[1]['quests'][0]['objectives'][0]
    assert objective['description'] == 'Search ten containers'
    assert objective['achieved'] == 6 and objective['display_stage'] == 1


def test_objective_backend_names_match_case_insensitively():
    from copy import deepcopy
    catalog = deepcopy(CAT)
    catalog['quest:test']['objectives'][0]['key'] = 'TEST_OBJ0'
    quest = parse_profile_response(response(), catalog)['quests'][0]
    assert len(quest['objectives']) == 1
    assert quest_progress_text(quest) == '5 of 10'
