"""Accessible four-tab pass browser launched from the locker."""
import threading

import wx
from lib.hub.controls import StyledButton, TabbedBook
from accessible_output2.outputs.auto import Auto

from lib.guis.view_host import EmbeddedView, ViewDialog
from lib.utilities import passes_view
from lib.utilities.epic_passes import EpicPassAPI, PassError, pages, rewards
from lib.utilities.pass_quests import related_templates


class PassesView(EmbeddedView):
    view_title = 'FA11y Locker Passes'

    def __init__(self, parent, auth, cosmetics=None, api=None):
        super().__init__(parent)
        self.api = api or EpicPassAPI(auth)
        self.speaker = Auto()
        self.snapshot = None
        self.busy = False
        self.closed = False
        self._loaded = False
        self.tabs = []
        self.metadata = passes_view.metadata_by_id(cosmetics)
        root = wx.BoxSizer(wx.VERTICAL)
        help_text = wx.StaticText(self, label=passes_view.HELP_TEXT)
        root.Add(help_text, 0, wx.ALL, 10)
        self.notebook = TabbedBook(self)
        for definition in self.api.definitions:
            panel = wx.Panel(self.notebook)
            layout = wx.BoxSizer(wx.VERTICAL)
            status = wx.TextCtrl(panel, style=wx.TE_READONLY | wx.TE_MULTILINE, size=(-1, 65))
            status.SetName('Pass ownership, level, and currency')
            layout.Add(status, 0, wx.EXPAND | wx.ALL, 5)
            layout.Add(wx.StaticText(panel, label='&Page:'), 0, wx.LEFT | wx.TOP, 5)
            choice = wx.Choice(panel)
            page_list = pages(definition)
            choice.SetItems(passes_view.page_choices(definition))
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
                button = StyledButton(panel, label=label)
                button.Bind(wx.EVT_BUTTON, lambda evt, t=tab, a=action: self.on_action(t,a))
                tab['buttons'][action] = button
                buttons.Add(button, 0, wx.ALL, 3)
            tab['set_notice']=wx.StaticText(panel,label=passes_view.SET_NOTICE)
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
        self.refresh_button = StyledButton(self, label='&Refresh passes')
        self.refresh_button.Bind(wx.EVT_BUTTON, self.refresh)
        footer.Add(self.refresh_button, 0, wx.ALL, 5)
        self.quests_button=StyledButton(self,label='View selected &pass quests')
        self.quests_button.Bind(wx.EVT_BUTTON,lambda evt:self.open_quests())
        footer.Add(self.quests_button,0,wx.ALL,5)
        self.message = wx.TextCtrl(self, value='Loading account status...',
                                   style=wx.TE_MULTILINE | wx.TE_READONLY,
                                   size=(-1,110), name='Pass operation result')
        footer.Add(self.message, 1, wx.ALL | wx.EXPAND, 5)
        close = StyledButton(self, label='&Close')
        close.Bind(wx.EVT_BUTTON, self.on_close_button)
        footer.Add(close, 0, wx.ALL, 5)
        root.Add(footer, 0, wx.EXPAND | wx.ALL, 5)
        self.SetSizer(root)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.render_all()

    def activate(self):
        self.closed = False
        if not self.busy:
            self.refresh_button.Enable()
        if not self._loaded:
            self._loaded = True
            wx.CallAfter(self.refresh)

    def deactivate(self):
        self.closed = True

    def initial_focus(self):
        return self.notebook

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
            self.busy = False
            if self.closed:
                return
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
        return passes_view.display_name(reward, self.metadata)

    def render_all(self):
        for tab in self.tabs:
            tab['status'].ChangeValue(passes_view.status_text(tab['definition'], self.snapshot))
            self.render_page(tab, preserve=True)

    def current(self, tab):
        index = tab['choice'].GetSelection()
        return tab['pages'][max(0,index)]

    def render_page(self, tab, preserve=False):
        selection = tab['list'].GetSelection() if preserve else 0
        category, page = self.current(tab)
        labels = passes_view.reward_labels(tab['definition'], category, page, self.snapshot, self.metadata)
        tab['list'].SetItems(labels)
        if labels:
            tab['list'].SetSelection(min(max(0,selection),len(labels)-1))
        self.render_details(tab)

    def render_details(self, tab):
        category,page = self.current(tab)
        index = tab['list'].GetSelection()
        reward = page['rewards'][index] if 0<=index<len(page['rewards']) else None
        definition = tab['definition']
        tab['details'].ChangeValue(passes_view.reward_details(definition, category, page, reward, self.snapshot, self.metadata))
        states = passes_view.button_states(definition, category, page, reward, self.snapshot, self.busy)
        tab['buttons']['reward'].Enable(states['reward'])
        tab['buttons']['page'].Enable(states['page'])
        tab['buttons']['set'].Show(states['set_visible'])
        tab['set_notice'].Show(states['set_notice'])
        tab['panel'].Layout()
        tab['buttons']['set'].Enable(states['set'])
        tab['buttons']['unlock'].Enable(states['unlock'])
        tab['buttons']['purchase'].Enable(states['purchase'])
        tab['buttons']['quests'].Enable(states['quests'])

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
        event.Skip()

    def on_action(self,tab,kind):
        if kind=='set' and self.current(tab)[0]['id']=='Set_SheerWill':
            self.say(passes_view.SHEER_WILL_TEXT)
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
        selected=passes_view.claim_selection(kind,category,page,page['rewards'][index] if kind=='reward' else None)
        ids=[r['id'] for r in selected if r['id'] not in state['claimed']]
        try:
            action=self.api.prepare(tab['definition']['key'],kind if kind in ('unlock','purchase') else 'claim',ids,self.snapshot)
        except PassError as exc:
            self.say(str(exc));return
        confirm=wx.MessageDialog(self,action.summary+'\n\nContinue?', 'FA11y Locker Passes: Confirm',
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
        scope=passes_view.quest_scope(definition,self.snapshot,self.metadata,reward)
        allowed,heading,scope=scope['templates'],scope['heading'],scope['label']
        QuestDialog(self,self.api.auth,quest_templates=allowed,heading=heading,initial_mode='All modes',scope_label=scope).run()

    def can_close(self):
        if self.busy:
            self.say('An account request is in progress. Close after it finishes.')
            return False
        return True

    def on_close_button(self,event):
        if self.can_close():
            self.request_close()


class PassesDialog(ViewDialog):
    """PassesView in a modal dialog; takes the same arguments as PassesView."""

    def __init__(self, parent, auth, cosmetics=None, api=None):
        super().__init__(parent, lambda host: PassesView(host, auth, cosmetics, api), size=(850, 720))
        self.SetMinSize((650, 550))
