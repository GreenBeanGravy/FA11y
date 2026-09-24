"""Native keyboard and screen-reader quest browser backed by Epic and packets."""
from datetime import datetime
import threading

import wx

from lib.managers.quest_manager import quest_store
from lib.utilities.epic_quests import EpicQuestAPI, QuestQueryError
from lib.utilities.quest_presentation import (prepare_quests, filter_quests, natural_key,
                                            list_labels, details_text, matches_mode)


class QuestDialog(wx.Dialog):
    def __init__(self, parent, auth, api=None, store=None, autoload=True,
                 quest_templates=None, heading=None, initial_mode=None):
        super().__init__(parent, title='FA11y Locker Pass Quests' if heading else 'Fortnite Quests', size=(920, 680),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.api = api or EpicQuestAPI(auth)
        self.store = store or quest_store
        self._closed = False
        self._loading = False
        self._revision = -1
        self._error = None
        self._initial_mode = initial_mode is None
        self.quest_templates = set(quest_templates) if quest_templates is not None else None
        self.rows = []
        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(wx.StaticText(self, label=heading or 'Browse your account quests before or during a match.'), 0, wx.ALL, 10)
        groups = wx.BoxSizer(wx.HORIZONTAL)
        groups.Add(wx.StaticText(self, label='&Mode:'), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.mode = wx.Choice(self, choices=['All modes'], name='Game mode')
        self.mode.SetSelection(0)
        groups.Add(self.mode, 1, wx.RIGHT, 10)
        groups.Add(wx.StaticText(self, label='Cate&gory:'), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.category = wx.Choice(self, choices=['All categories'], name='Quest category')
        self.category.SetSelection(0)
        groups.Add(self.category, 2)
        layout.Add(groups, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        controls = wx.BoxSizer(wx.HORIZONTAL)
        controls.Add(wx.StaticText(self, label='&Search:'), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.search = wx.TextCtrl(self, name='Search quests')
        controls.Add(self.search, 1, wx.RIGHT, 10)
        controls.Add(wx.StaticText(self, label='&Status:'), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.filter = wx.Choice(self, choices=['Active', 'Completed', 'All'], name='Quest status')
        self.filter.SetSelection(2 if self.quest_templates is not None else 0)
        controls.Add(self.filter, 0)
        layout.Add(controls, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        self.expired = wx.CheckBox(self, label='Include &expired quests')
        layout.Add(self.expired, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        layout.Add(wx.StaticText(self, label='&Quests:'), 0, wx.LEFT | wx.RIGHT, 10)
        self.list = wx.ListBox(self, name='Quests')
        layout.Add(self.list, 2, wx.EXPAND | wx.ALL, 10)
        layout.Add(wx.StaticText(self, label='&Details:'), 0, wx.LEFT | wx.RIGHT, 10)
        self.details = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY,
                                   name='Quest details')
        layout.Add(self.details, 1, wx.EXPAND | wx.ALL, 10)
        self.status = wx.StaticText(self, label='Quests have not been loaded.')
        layout.Add(self.status, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.refresh_button = wx.Button(self, label='&Refresh')
        close = wx.Button(self, wx.ID_CANCEL, label='&Close')
        buttons.Add(self.refresh_button, 0, wx.RIGHT, 10)
        buttons.Add(close, 0)
        layout.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
        self.SetSizer(layout)
        self.SetMinSize((620, 480))
        self.search.Bind(wx.EVT_TEXT, self._render)
        self.filter.Bind(wx.EVT_CHOICE, self._render)
        self.mode.Bind(wx.EVT_CHOICE, self._mode_changed)
        self.category.Bind(wx.EVT_CHOICE, self._render)
        self.expired.Bind(wx.EVT_CHECKBOX, self._render)
        self.list.Bind(wx.EVT_LISTBOX, self._selection)
        self.refresh_button.Bind(wx.EVT_BUTTON, self.refresh)
        close.Bind(wx.EVT_BUTTON, lambda event: self.Close())
        self.Bind(wx.EVT_CLOSE, self._close)
        self.Bind(wx.EVT_CHAR_HOOK, self._key)
        self.account_timer = wx.Timer(self)
        self.packet_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.refresh, self.account_timer)
        self.Bind(wx.EVT_TIMER, self._packet_tick, self.packet_timer)
        if autoload:
            self.account_timer.Start(60_000)
            self.packet_timer.Start(500)
            self.refresh()
        self._render()
        self.search.SetFocus()

    def _key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
        else:
            event.Skip()

    def refresh(self, event=None):
        if self._closed or self._loading:
            return
        self._loading = True
        self.refresh_button.Disable()
        self.status.SetLabel('Loading quests from Epic Games.')
        def worker():
            try:
                snapshot, error = self.api.query(), None
            except QuestQueryError as exc:
                snapshot, error = None, str(exc)
            except Exception:
                snapshot, error = None, 'Unable to load quests. Refresh to retry.'
            wx.CallAfter(self._loaded, snapshot, error)
        threading.Thread(target=worker, name='EpicQuestQuery', daemon=True).start()

    def _loaded(self, snapshot, error):
        if self._closed:
            return
        self._loading = False
        self.refresh_button.Enable()
        if error:
            self.account_timer.Stop()
            self._error = error + ' Previously loaded quests remain available.'
            self.status.SetLabel(self._error)
            return
        self._error = None
        self.store.replace_api(snapshot)
        self.account_timer.Start(60_000)
        self._render()

    def _packet_tick(self, event):
        revision, _ = self.store.snapshot()
        if revision != self._revision:
            self._render()

    def _mode_changed(self, event):
        self._initial_mode = False
        self.category.SetSelection(0)
        self._render()

    @staticmethod
    def _choices(control, values):
        selected = control.GetStringSelection()
        if list(control.GetStrings()) != values:
            control.Set(values)
            control.SetStringSelection(selected if selected in values else values[0])

    def _render(self, event=None):
        if self._closed:
            return
        old_index = self.list.GetSelection()
        selected = self.rows[old_index]['id'] if 0 <= old_index < len(self.rows) else None
        self._revision, snapshot = self.store.snapshot()
        rows, hidden, unresolved = prepare_quests(snapshot['quests'],contextual_templates=self.quest_templates)
        if self.quest_templates is not None:
            rows=[q for q in rows if q['template'].lower() in self.quest_templates]
        self._choices(self.mode, ['All modes'] + sorted({m for q in rows for m in q['modes']}, key=natural_key))
        if rows and self._initial_mode:
            self.mode.SetStringSelection('Battle Royale')
            self._initial_mode = False
        mode = self.mode.GetStringSelection()
        categories = {q['category'] for q in rows if matches_mode(q, mode)}
        self._choices(self.category, ['All categories'] + sorted(categories, key=natural_key))
        self.rows = filter_quests(rows, mode=mode, category=self.category.GetStringSelection(),
                                  status=self.filter.GetStringSelection(), query=self.search.GetValue(),
                                  expired=self.expired.GetValue())
        labels = list_labels(self.rows, include_mode=mode == 'All modes')
        old_ids = getattr(self, '_list_ids', [])
        new_ids = [q['id'] for q in self.rows]
        if old_ids != new_ids:
            self.list.Set(labels)
        else:
            # Updating one counter must not reset the list's scroll position.
            for i, label in enumerate(labels):
                if self.list.GetString(i) != label:
                    self.list.SetString(i, label)
        self._list_ids = new_ids
        if self.rows:
            index = next((i for i, q in enumerate(self.rows) if q['id'] == selected), 0)
            if self.list.GetSelection() != index:
                self.list.SetSelection(index)
        self._selection()
        when = snapshot.get('updated_at')
        stamp = datetime.fromtimestamp(when).strftime('%I:%M:%S %p') if when else 'not yet loaded'
        self.status.SetLabel(self._error or
            f'{len(self.rows)} quests shown. {hidden} inactive, hidden, or suppressed quests excluded; '
            f'{unresolved} quests awaiting readable names. Account snapshot: {stamp}.')

    def _selection(self, event=None):
        index = self.list.GetSelection()
        if not 0 <= index < len(self.rows):
            self.details.ChangeValue('No quests match these filters.')
            return
        value = details_text(self.rows[index])
        selected_id = self.rows[index]['id']
        if self.details.GetValue() != value:
            position = self.details.GetInsertionPoint() if getattr(self, '_details_id', None) == selected_id else 0
            self.details.ChangeValue(value)
            self.details.SetInsertionPoint(min(position, len(value)))
        self._details_id = selected_id

    def _close(self, event):
        self._closed = True
        self.account_timer.Stop()
        self.packet_timer.Stop()
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Destroy()


def show_quest_gui(auth):
    dialog = QuestDialog(None, auth)
    try:
        dialog.ShowModal()
    finally:
        dialog.Destroy()
