import copy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from lib.utilities.epic_passes import (EpicPassAPI, PassError, full_profile,
    load_pass_catalog, pages, rewards, reward_status, snapshot_from_profiles)


def reward(rid, **kwargs):
    return dict(id=rid, kind='reward', name=rid, item_id=rid, free=True, cost=1,
                currency='accountresource:points', requirements={}, **kwargs)


@pytest.fixture
def setup():
    first=reward('A'); final=reward('B')
    final['requirements']={'bRequireAllOtherPageRewards':True}
    locked=reward('C'); token=reward('TOKEN')
    token['currency']='accountresource:keys'
    definition=dict(key='br',name='Battle Pass',template='AthenaSeason:test',storefront='BRTest',purchase_offer='PASS',categories=[
        dict(id='set1',name='First',unlock_offers=[],pages=[dict(id='page1',rewards=[first,final])]),
        dict(id='set2',name='Second',unlock_offers=[token],pages=[dict(id='page2',rewards=[locked])])])
    athena=dict(profileId='athena',rvn=10,items={
        'season':dict(templateId='AthenaSeason:test',attributes=dict(purchased=True,level=20,purchased_offers=[])),
        'points':dict(templateId='AccountResource:points',quantity=5),
        'keys':dict(templateId='AccountResource:keys',quantity=1)})
    common=dict(profileId='common_core',rvn=20,items={})
    store=dict(expiration='2099-01-01T00:00:00Z',storefronts=[dict(name='BRTest',catalogEntries=[dict(
        offerId='PASS',offerType='StaticPrice',prices=[dict(currencyType='MtxCurrency',currencySubType='',finalPrice=800)])])])
    auth=SimpleNamespace(account_id='account-test',access_token='secret-test',MCP_URL='https://example.test/profile',refresh_access_token=Mock(return_value=True))
    session=Mock()
    api=EpicPassAPI(auth,session=session,definitions=[definition],clock=lambda:1000)
    snapshot=snapshot_from_profiles(athena,common,store,[definition],1000)
    snapshot['account_id']=auth.account_id
    return api,snapshot,definition,athena,common,store


def response(body,status=200):
    result=Mock(status_code=status);result.json.return_value=body;return result


def profile_body(profile):
    return {'profileChanges':[dict(changeType='fullProfileUpdate',profile=profile)]}


def test_catalog_has_all_current_pages_and_real_names():
    definitions=load_pass_catalog()
    assert {d['key']:len(pages(d)) for d in definitions}==dict(br=26,og=6,festival=4,lego=4)
    for definition in definitions:
        ids=[]
        for category in definition['categories']:
            for item in rewards(category)+category['unlock_offers']:
                assert item['name']
                assert len(item['id'])==32
                assert item['cost']>=0
                ids.append(item['id'])
        assert len(ids)==len(set(ids))


def test_requires_full_correct_profile():
    with pytest.raises(PassError):full_profile({'profileChanges':[]},'athena')
    with pytest.raises(PassError):full_profile(profile_body(dict(profileId='common_core',items={})), 'athena')


def test_locked_set_cannot_claim_but_can_unlock(setup):
    api,snap,definition,*_=setup
    with pytest.raises(PassError,match='Unlock this set'):api.prepare('br','claim',['C'],snap)
    action=api.prepare('br','unlock',['TOKEN'],snap)
    assert dict(action.costs)=={'accountresource:keys':1}
    assert action.names==('Second',)
    api.session.request.assert_not_called()


def test_full_page_orders_prerequisites_and_does_not_send_during_preview(setup):
    api,snap,*_=setup
    action=api.prepare('br','claim',['B','A'],snap)
    assert action.offer_ids==('A','B')
    assert dict(action.costs)=={'accountresource:points':2}
    api.session.request.assert_not_called()
    with pytest.raises(PassError,match='other rewards'):api.prepare('br','claim',['B'],snap)


@pytest.mark.parametrize('change,message',[
    ('stale','Refresh'),('account','account'),('currency','Not enough'),('ended','active'),('expiry','expired')])
def test_preconditions_block_sending(setup,change,message):
    api,snap,*_=setup
    if change=='stale':snap['updated_at']=0
    if change=='account':snap['account_id']='different'
    if change=='currency':snap['balances']={}
    if change=='ended':snap['passes']['br']['active']=False
    if change=='expiry':snap['expiration']='1970-01-01T00:00:00Z'
    with pytest.raises(PassError,match=message):api.prepare('br','claim',['A'],snap)
    api.session.request.assert_not_called()


def test_unknown_ids_and_premium_are_rejected(setup):
    api,snap,definition,*_=setup
    with pytest.raises(PassError):api.prepare('br','claim',['FAKE'],snap)
    with pytest.raises(PassError):api.prepare('br','claim',['A','A'],snap)
    definition['categories'][0]['pages'][0]['rewards'][0]['free']=False
    snap['passes']['br']['purchased']=False
    with pytest.raises(PassError,match='premium'):api.prepare('br','claim',['A'],snap)


def test_exact_live_price_used_for_purchase(setup):
    api,snap,*_=setup;snap['passes']['br']['purchased']=False
    action=api.prepare('br','purchase',[],snap)
    assert action.offer_ids==('PASS',)
    assert dict(action.costs)=={'MtxCurrency':800}
    snap['passes']['br']['offer']['prices'][0]['currencyType']='RealMoney'
    with pytest.raises(PassError,match='purchase type'):api.prepare('br','purchase',[],snap)


def test_claim_is_sent_once_then_confirmed_from_profile(setup):
    api,snap,definition,athena,common,store=setup
    action=api.prepare('br','claim',['A','B'],snap)
    after=copy.deepcopy(athena)
    after['items']['season']['attributes']['purchased_offers']=[{'offerId':'A'},{'offerId':'B'}]
    api.session.request.side_effect=[response(profile_body(athena)),response(profile_body(common)),response(store),
        response({}),response(profile_body(after)),response(profile_body(common)),response(store)]
    result,message=api.execute(action)
    mutation=api.session.request.call_args_list[3]
    assert mutation.args[1].endswith('/ExchangeGameCurrencyForSeasonPassOffer')
    assert mutation.kwargs['json']['offerItemIdList']==['A','B']
    assert mutation.kwargs['json']['seasonPassTemplateId']=='AthenaSeason:test'
    assert mutation.kwargs['params']=={'profileId':'athena','rvn':10}
    assert '2 of 2' in message
    assert result['passes']['br']['claimed']=={'A','B'}


def test_timeout_is_reconciled_without_resending(setup):
    api,snap,definition,athena,common,store=setup
    action=api.prepare('br','claim',['A'],snap)
    api.session.request.side_effect=[response(profile_body(athena)),response(profile_body(common)),response(store),
        requests.Timeout('secret should not escape'),response(profile_body(athena)),response(profile_body(common)),response(store)]
    result,message=api.execute(action)
    assert '0 of 1' in message and 'uncertain' in message
    assert 'secret' not in message
    assert sum(c.args[1].endswith('/ExchangeGameCurrencyForSeasonPassOffer') for c in api.session.request.call_args_list)==1


def test_refresh_failure_after_mutation_never_reports_success(setup):
    api,snap,definition,athena,common,store=setup
    action=api.prepare('br','claim',['A'],snap)
    api.session.request.side_effect=[response(profile_body(athena)),response(profile_body(common)),response(store),response({}),requests.Timeout()]
    with pytest.raises(PassError,match='could not be verified'):api.execute(action)


def test_partial_claim_is_reported_from_server_state(setup):
    api,snap,definition,athena,common,store=setup
    action=api.prepare('br','claim',['A','B'],snap)
    after=copy.deepcopy(athena)
    after['items']['season']['attributes']['purchased_offers']=[{'offerId':'A'}]
    api.session.request.side_effect=[response(profile_body(athena)),response(profile_body(common)),response(store),
        response({}),response(profile_body(after)),response(profile_body(common)),response(store)]
    result,message=api.execute(action)
    assert '1 of 2' in message
    assert result['passes']['br']['claimed']=={'A'}


def test_price_change_after_confirmation_stops_purchase(setup):
    api,snap,definition,athena,common,store=setup
    snap['passes']['br']['purchased']=False
    action=api.prepare('br','purchase',[],snap)
    athena['items']['season']['attributes']['purchased']=False
    store['storefronts'][0]['catalogEntries'][0]['prices'][0]['finalPrice']=900
    api.session.request.side_effect=[response(profile_body(athena)),response(profile_body(common)),response(store)]
    with pytest.raises(PassError,match='price changed'):api.execute(action)
    assert api.session.request.call_count==3


def test_changed_selection_does_not_mutate(setup):
    api,snap,definition,athena,common,store=setup
    action=api.prepare('br','claim',['A','B'],snap)
    athena['items']['season']['attributes']['purchased_offers']=[{'offerId':'A'}]
    api.session.request.side_effect=[response(profile_body(athena)),response(profile_body(common)),response(store)]
    with pytest.raises(PassError,match='changed'):api.execute(action)
    assert api.session.request.call_count==3


def test_queries_retry_login_but_mutations_never_retry(setup):
    api,*_=setup
    api.session.request.side_effect=[response({},401),response({})]
    assert api._request('GET','https://example.test')=={}
    api.auth.refresh_access_token.assert_called_once()
    api.session.request.reset_mock();api.session.request.side_effect=[response({},401)]
    with pytest.raises(PassError):api._request('POST','https://example.test',mutation=True,json={})
    assert api.session.request.call_count==1


def test_rejection_exposes_reason_redacts_secrets_and_lists_pending_requirements(setup):
    api,snap,definition,athena,common,store=setup
    action=api.prepare('br','claim',['A','B'],snap)
    rejection=dict(errorCode='errors.com.epicgames.requirements_not_met',
                   errorMessage='Need page rewards for account-test; secret-test',
                   debug='do not display this field')
    api.session.request.side_effect=[response(profile_body(athena)),response(profile_body(common)),response(store),
        response(rejection,400),response(profile_body(athena)),response(profile_body(common)),response(store)]
    _,message=api.execute(action)
    assert 'requirements_not_met' in message and 'Need page rewards' in message
    assert 'account-test' not in message and 'secret-test' not in message
    assert 'do not display' not in message
    assert 'Still unclaimed: A, B' in message
    assert 'Other rewards not yet claimed: A' in message
    assert '0 of 2' in message
    assert sum(c.args[1].endswith('/ExchangeGameCurrencyForSeasonPassOffer') for c in api.session.request.call_args_list)==1


def test_non_json_error_is_explained_without_echoing_body(setup):
    api,*_=setup
    result=response({},400);result.json.side_effect=ValueError('private body')
    api.session.request.return_value=result
    with pytest.raises(PassError,match='no detailed reason') as exc:
        api._request('POST','https://example.test',mutation=True)
    assert 'private body' not in str(exc.value)
