"""Accessible four-tab pass browser launched from the locker."""
import threading

import wx
from accessible_output2.outputs.auto import Auto

from lib.utilities.epic_passes import (EpicPassAPI, PassError, CURRENCY_NAMES, costs_text, pages,
    rewards, reward_status, requirement_text)
from lib.utilities.pass_quests import related_templates, pass_quest_details


class PassesDialog(wx.Dialog):
    def __init__(self, parent, auth, cosmetics=None, api=None):
        super().__init__(parent, title='FA11y Locker Passes', size=(850, 720),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.api = api or EpicPassAPI(auth)
        self.speaker = Auto()
        self.snapshot = None
        self.busy = False
        self.closed = False
        self.tabs = []
        self.metadata = {c.get('id','').lower(): c for c in (cosmetics or [])}
        root = wx.BoxSizer(wx.VERTICAL)
        help_text = wx.StaticText(self, label='Arrow keys browse rewards. Page Up/Down changes pages. Ctrl+Tab changes passes.')
        root.Add(help_text, 0, wx.ALL, 10)
        self.notebook = wx.Notebook(self)
        for definition in self.api.definitions:
            panel = wx.Panel(self.notebook)
            layout = wx.BoxSizer(wx.VERTICAL)
            status = wx.TextCtrl(panel, style=wx.TE_READONLY | wx.TE_MULTILINE, size=(-1, 65))
            status.SetName('Pass ownership, level, and currency')
            layout.Add(status, 0, wx.EXPAND | wx.ALL, 5)
            layout.Add(wx.StaticText(panel, label='&Page:'), 0, wx.LEFT | wx.TOP, 5)
            choice = wx.Choice(panel)
            page_list = pages(definition)
            choice.SetItems([f'{i+1} of {len(page_list)}: '+('Bonus — ' if c.get('group')=='Bonus' else '')+c['name'] for i,(c,p) in enumerate(page_list)])
            choice.SetSelection(0)
            layout.Add(choice, 0, wx.EXPAND | wx.ALL, 5)
            layout.Add(wx.StaticText(panel, label='&Rewards:'), 0, wx.LEFT, 5)
            reward_list = wx.ListBox(panel, style=wx.LB_SINGLE)
            reward_list.SetName('Pass rewards')
            layout.Add(reward_list, 2, wx.EXPAND | wx.ALL, 5)
            layout.Add(wx.StaticText(panel, label='Reward &details:'), 0, wx.LEFT, 5)
            details = wx.TextCtrl(panel, style=wx.TE_READONLY | wx.TE_MULTILINE)
            details.SetName('Reward description, set, and requirements')
            layout.Add(details, 2, wx.EXPAND | wx.ALL, 5)
            buttons = wx.WrapSizer(wx.HORIZONTAL)
            tab = dict(definition=definition, panel=panel, status=status, choice=choice,
                       list=reward_list, details=details, pages=page_list, buttons={})
            for label, action in [('&Claim reward','reward'),('Claim full pa&ge','page'),
                                  ('Claim full &set','set'),('&Unlock set','unlock'),('Unlock premium &pass','purchase'),
                                  ('View reward &quests','quests')]:
                button = wx.Button(panel, label=label)
                button.Bind(wx.EVT_BUTTON, lambda evt, t=tab, a=action: self.on_action(t,a))
                tab['buttons'][action] = button
                buttons.Add(button, 0, wx.ALL, 3)
            tab['set_notice']=wx.StaticText(panel,label='Cannot claim full set, please claim full page')
            tab['set_notice'].Hide()
            layout.Add(buttons, 0, wx.EXPAND | wx.ALL, 3)
            layout.Add(tab['set_notice'],0,wx.ALL,5)
            panel.SetSizer(layout)
            self.tabs.append(tab)
            self.notebook.AddPage(panel, definition['name'])
            choice.Bind(wx.EVT_CHOICE, lambda evt,t=tab:self.render_page(t))
            reward_list.Bind(wx.EVT_LISTBOX, lambda evt,t=tab:self.render_details(t))
        root.Add(self.notebook, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        footer = wx.BoxSizer(wx.HORIZONTAL)
        self.refresh_button = wx.Button(self, label='&Refresh passes')
        self.refresh_button.Bind(wx.EVT_BUTTON, self.refresh)
        footer.Add(self.refresh_button, 0, wx.ALL, 5)
        self.quests_button=wx.Button(self,label='View selected &pass quests')
        self.quests_button.Bind(wx.EVT_BUTTON,lambda evt:self.open_quests())
        footer.Add(self.quests_button,0,wx.ALL,5)
        self.message = wx.TextCtrl(self, value='Loading account status...',
                                   style=wx.TE_MULTILINE | wx.TE_READONLY,
                                   size=(-1,110), name='Pass operation result')
        footer.Add(self.message, 1, wx.ALL | wx.EXPAND, 5)
        close = wx.Button(self, wx.ID_CANCEL, '&Close')
        close.Bind(wx.EVT_BUTTON, self.on_close)
        footer.Add(close, 0, wx.ALL, 5)
        root.Add(footer, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(root)
        self.SetMinSize((650,550))
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.CentreOnParent()
        self.render_all()
        wx.CallAfter(self.refresh)

    def say(self, message):
        self.message.ChangeValue(message)
        self.Layout()
        self.speaker.speak(message)

    def _worker(self, operation, callback):
        if self.busy or self.closed:
            return
        self.busy = True
        self.render_all()
        self.refresh_button.Disable()
        def work():
            try:
                result, error = operation(), None
            except PassError as exc:
                result, error = None, str(exc)
            except Exception:
                result, error = None, 'Pass data could not be loaded. Refresh to retry.'
            wx.CallAfter(done, result, error)
        def done(result, error):
            if self.closed:
                return
            self.busy = False
            self.refresh_button.Enable()
            callback(result,error)
            self.render_all()
        threading.Thread(target=work, daemon=True, name='epic-passes').start()

    def refresh(self, event=None):
        def done(result,error):
            self.snapshot = result if not error else None
            self.say(error or 'Passes refreshed.')
        self._worker(self.api.query, done)

    def display_name(self, reward):
        meta = self.metadata.get(reward.get('item_id',''),{})
        return reward.get('name') or meta.get('name') or 'Unnamed reward ('+reward.get('item_id','')+')'

    def render_all(self):
        for tab in self.tabs:
            definition = tab['definition']
            state = self.snapshot['passes'][definition['key']] if self.snapshot else None
            text = definition['season_name'] + '. '
            if not state or not state['active']:
                text += 'Account status unavailable. Refresh to check this pass.'
            else:
                text += ('Premium pass owned. ' if state['purchased'] else 'Premium pass not owned. ')
                text += f"Pass level: {state['level'] if state['level'] is not None else 'not reported'}. "
                currencies = {r['currency'] for c in definition['categories'] for r in rewards(c)+c['unlock_offers']}
                text += 'Available: '+', '.join(f"{self.snapshot['balances'].get(c,0):,} {CURRENCY_NAMES.get(c,c)}" for c in sorted(currencies))
            tab['status'].ChangeValue(text)
            self.render_page(tab, preserve=True)

    def current(self, tab):
        index = tab['choice'].GetSelection()
        return tab['pages'][max(0,index)]

    def render_page(self, tab, preserve=False):
        selection = tab['list'].GetSelection() if preserve else 0
        category, page = self.current(tab)
        labels = [self.display_name(r)+' — '+reward_status(tab['definition'],category,page,r,self.snapshot)
                  for r in page['rewards']]
        tab['list'].SetItems(labels)
        if labels:
            tab['list'].SetSelection(min(max(0,selection),len(labels)-1))
        self.render_details(tab)

    def render_details(self, tab):
        category,page = self.current(tab)
        index = tab['list'].GetSelection()
        reward = page['rewards'][index] if 0<=index<len(page['rewards']) else None
        definition = tab['definition']
        state = self.snapshot['passes'][definition['key']] if self.snapshot else None
        usable = bool(state and state['active'] and not self.busy)
        text = ''
        if reward:
            metadata = self.metadata.get(reward.get('item_id',''),{})
            cosmetic_set = metadata.get('set') or ''
            if isinstance(cosmetic_set,dict):
                cosmetic_set = cosmetic_set.get('value') or cosmetic_set.get('text') or ''
            text = self.display_name(reward)+'\n'+(reward.get('description') or metadata.get('description') or 'No description supplied.')
            text += '\nType: '+(reward.get('item_type') or 'Reward')
            text += '\nPass set: '+category['name']
            if category.get('group')=='Bonus':
                text += '\nBonus rewards'
            if category['unlock_offers']:
                unlock_cost = {}
                for offer in category['unlock_offers']:
                    if not state or offer['id'] not in state['claimed']:
                        unlock_cost[offer['currency']] = unlock_cost.get(offer['currency'],0)+offer['cost']
                text += '\nSet unlock: '+(costs_text(unlock_cost) if unlock_cost else 'Already unlocked')
            if category.get('dependent_category'):
                dependency=next((c['name'] for c in definition['categories'] if c['id']==category['dependent_category']), 'another set')
                text += '\nSet prerequisite: '+dependency+'; Epic checks the unlock requirements.'
            if cosmetic_set:
                text += '\nCosmetic set: '+cosmetic_set
            text += '\n'+reward_status(definition,category,page,reward,self.snapshot)
            if reward['kind']=='quest':
                text += '\n\n'+pass_quest_details(reward,self.snapshot.get('quests') if self.snapshot else None)
            if reward['kind']=='reward':
                text += '\n'+('Free track' if reward['free'] else 'Premium track')
                text += '\nCost: '+costs_text({reward['currency']:reward['cost']})
                text += '\n'+requirement_text(reward)
                if reward.get('extra_rewards'):
                    text += '\nAlso includes: '+', '.join(self.display_name(r) for r in reward['extra_rewards'])
        tab['details'].ChangeValue(text)
        tab['buttons']['reward'].Enable(usable and bool(reward) and reward['kind']=='reward' and reward['id'] not in state['claimed'])
        tab['buttons']['page'].Enable(usable and any(r['kind']=='reward' and r['id'] not in state['claimed'] for r in page['rewards']))
        page_only=definition['key']=='br' and category['id']=='Set_SheerWill'
        tab['buttons']['set'].Show(not page_only)
        tab['set_notice'].Show(page_only)
        tab['panel'].Layout()
        tab['buttons']['set'].Enable(not page_only and usable and definition['key']=='br' and any(r['id'] not in state['claimed'] for r in rewards(category)))
        tab['buttons']['unlock'].Enable(usable and any(r['id'] not in state['claimed'] for r in category['unlock_offers']))
        tab['buttons']['purchase'].Enable(usable and not state['purchased'])
        tab['buttons']['quests'].Enable(not self.busy and bool(reward) and reward['kind']=='quest' and bool(related_templates(reward,self.snapshot.get('quests') if self.snapshot else None)))

    def on_key(self,event):
        code = event.GetKeyCode()
        if code in (wx.WXK_PAGEUP,wx.WXK_PAGEDOWN):
            tab = self.tabs[self.notebook.GetSelection()]
            old = tab['choice'].GetSelection()
            new = min(max(old+(-1 if code==wx.WXK_PAGEUP else 1),0),len(tab['pages'])-1)
            if old != new:
                tab['choice'].SetSelection(new)
                self.render_page(tab)
                tab['list'].SetFocus()
                self.speaker.speak(tab['choice'].GetStringSelection())
            else:
                self.speaker.speak('First page.' if code==wx.WXK_PAGEUP else 'Last page.')
            return
        if code==wx.WXK_ESCAPE:
            self.on_close(event)
            return
        event.Skip()

    def on_action(self,tab,kind):
        if kind=='set' and self.current(tab)[0]['id']=='Set_SheerWill':
            self.say('Cannot claim full set, please claim full page. Claim page 15 before page 16.')
            return
        if kind=='quests':
            category,page=self.current(tab)
            index=tab['list'].GetSelection()
            if index>=0:self.open_quests(page['rewards'][index])
            return
        if self.busy or not self.snapshot:
            return
        category,page = self.current(tab)
        state = self.snapshot['passes'][tab['definition']['key']]
        if kind=='reward':
            index=tab['list'].GetSelection()
            if index<0:return
            selected=[page['rewards'][index]]
        elif kind=='page':selected=[r for r in page['rewards'] if r['kind']=='reward']
        elif kind=='set':selected=rewards(category)
        elif kind=='unlock':selected=category['unlock_offers']
        else:selected=[]
        ids=[r['id'] for r in selected if r['id'] not in state['claimed']]
        try:
            action=self.api.prepare(tab['definition']['key'],kind if kind in ('unlock','purchase') else 'claim',ids,self.snapshot)
        except PassError as exc:
            self.say(str(exc));return
        confirm=wx.MessageDialog(self,action.summary+'\n\nContinue?', 'FA11y Locker Passes — Confirm',
                                 wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
        try:
            if confirm.ShowModal()!=wx.ID_YES:return
        finally:
            confirm.Destroy()
        def done(result,error):
            if error:
                self.snapshot=None
                self.say(error)
            else:
                self.snapshot,message=result
                self.say(message)
        self._worker(lambda:self.api.execute(action),done)

    def open_quests(self,reward=None):
        from lib.guis.quest_gui import QuestDialog
        from lib.managers.quest_manager import quest_store
        quest_snapshot=self.snapshot.get('quests') if self.snapshot else None
        if quest_snapshot:
            quest_store.replace_api(quest_snapshot)
        definition=self.tabs[self.notebook.GetSelection()]['definition']
        scope=definition['name']+' quests'
        if reward:
            allowed=related_templates(reward,quest_snapshot)
            heading='Quests for '+self.display_name(reward)
        else:
            allowed=set()
            for category in definition['categories']:
                for page in category['pages']:
                    for entry in page['rewards']:
                        if entry['kind']=='quest':
                            allowed.update(related_templates(entry,quest_snapshot))
            heading=scope+' - quests linked to this pass and its rewards.'
        dialog=QuestDialog(self,self.api.auth,quest_templates=allowed,heading=heading,initial_mode='All modes',scope_label=scope)
        try:dialog.ShowModal()
        finally:dialog.Destroy()

    def on_close(self,event):
        if self.busy:
            self.say('An account request is in progress. Close after it finishes.')
            if isinstance(event,wx.CloseEvent) and event.CanVeto():event.Veto()
            return
        self.closed=True
        if self.IsModal():self.EndModal(wx.ID_CANCEL)
        else:self.Destroy()
