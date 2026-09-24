from unittest.mock import Mock

import pytest
import wx

from lib.utilities.epic_passes import load_pass_catalog
import lib.guis.passes_gui as gui


@pytest.fixture
def dialog(monkeypatch):
    app=wx.App.Get() or wx.App(False)
    monkeypatch.setattr(gui,'Auto',lambda:Mock())
    # Exercise real native controls without account requests or visible windows.
    monkeypatch.setattr(gui.PassesDialog,'refresh',lambda *args:None)
    api=Mock(definitions=load_pass_catalog())
    dlg=gui.PassesDialog(None,None,api=api)
    yield dlg
    dlg.closed=True
    dlg.Destroy()
    app.ProcessPendingEvents()


def key(code):
    return Mock(GetKeyCode=lambda:code)


def test_page_keys_follow_game_pages_and_stop_at_boundaries(dialog):
    assert dialog.notebook.GetPageCount()==4
    tab=dialog.tabs[0]
    dialog.on_key(key(wx.WXK_PAGEDOWN))
    assert tab['choice'].GetSelection()==1
    assert tab['list'].GetSelection()==0
    dialog.on_key(key(wx.WXK_PAGEUP))
    dialog.on_key(key(wx.WXK_PAGEUP))
    assert tab['choice'].GetSelection()==0
    dialog.notebook.SetSelection(1)
    for _ in range(8):dialog.on_key(key(wx.WXK_PAGEDOWN))
    assert dialog.tabs[1]['choice'].GetSelection()==5
    assert tab['choice'].GetSelection()==0


def test_arrow_keys_pass_through_and_quest_reward_cannot_claim(dialog):
    event=key(wx.WXK_DOWN)
    dialog.on_key(event)
    event.Skip.assert_called_once()
    tab=dialog.tabs[0]
    assert tab['list'].GetCount()>0
    assert not tab['buttons']['purchase'].IsEnabled()
    assert not tab['buttons']['reward'].IsEnabled()
    assert 'Sonic' in tab['choice'].GetStringSelection()
    assert tab['details'].GetValue()


def test_only_br_has_native_set_claim_button(dialog):
    dialog.snapshot=dict(passes={d['key']:dict(active=True,purchased=True,level=100,claimed=set()) for d in dialog.api.definitions},balances={})
    dialog.render_all()
    assert dialog.tabs[0]['buttons']['set'].IsEnabled()
    assert all(not t['buttons']['set'].IsEnabled() for t in dialog.tabs[1:])


def test_bonus_pages_are_explicit_and_reward_quests_have_button(dialog):
    tab=dialog.tabs[0]
    assert sum('Bonus' in s for s in tab['choice'].GetStrings())==10
    for i,(category,page) in enumerate(tab['pages']):
        indices=[j for j,r in enumerate(page['rewards']) if r['kind']=='quest']
        if indices:
            tab['choice'].SetSelection(i);dialog.render_page(tab)
            tab['list'].SetSelection(indices[0]);dialog.render_details(tab)
            assert tab['buttons']['quests'].IsEnabled()
            assert not tab['buttons']['reward'].IsEnabled()
            assert 'Missing quests are not treated as completed' in tab['details'].GetValue()
            return
    assert False,'Expected a quest reward entry'


def test_scoped_quest_dialog_keeps_active_and_completed_item_quests(dialog):
    from lib.guis.quest_gui import QuestDialog
    from lib.managers.quest_manager import QuestStore
    from lib.utilities.epic_quests import normalize_quest
    tid='quest:pass_gui_test'
    catalog={tid:dict(name='Complete the item task',hidden=True,objectives=[dict(key='obj0',required=3)])}
    q=normalize_quest('instance',dict(templateId=tid,attributes=dict(quest_state='Claimed',completion_obj0=3)),catalog,100)
    store=QuestStore();store.replace_api(dict(quests=[q],updated_at=100))
    child=QuestDialog(dialog,None,store=store,autoload=False,quest_templates={tid},heading='Selected reward',initial_mode='All modes',scope_label='Battle Royale Pass quests')
    try:
        assert child.filter.GetStringSelection()=='All'
        assert child.category.GetStringSelection()=='Battle Royale Pass quests'
        assert len(child.rows)==1
        assert '3 of 3' in child.details.GetValue()
        assert 'Completed (reward claimed)' in child.details.GetValue()
    finally:
        child._closed=True;child.Destroy()


def test_pass_button_scopes_to_selected_tab_including_empty_pass(dialog, monkeypatch):
    import lib.guis.quest_gui as quests
    from lib.utilities.pass_quests import related_templates
    constructor=Mock()
    monkeypatch.setattr(quests,'QuestDialog',constructor)
    for index,tab in enumerate(dialog.tabs):
        dialog.notebook.SetSelection(index)
        dialog.open_quests()
        kwargs=constructor.call_args.kwargs
        expected=set()
        for category,page in tab['pages']:
            for reward in page['rewards']:
                if reward['kind']=='quest':
                    expected.update(related_templates(reward,None))
        assert kwargs['quest_templates']==expected
        assert kwargs['quest_templates'] is not None
        assert kwargs['scope_label']==tab['definition']['name']+' quests'
