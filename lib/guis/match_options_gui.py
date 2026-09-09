"""Accessible, mode-specific controls for Fortnite's open match-options screen."""
import threading
import wx
from accessible_output2.outputs.auto import Auto
from lib.guis.gui_utilities import AccessibleDialog, force_focus_window
from lib.detection import match_options as backend
from lib.app import state

TITLE = 'FA11y Match Options'


class MatchOptionsDialog(AccessibleDialog):
    def __init__(self, current, parent=None, controller=backend):
        super().__init__(parent, title=TITLE, helpId='MatchOptions')
        self.SetWindowStyleFlag(self.GetWindowStyleFlag() | wx.STAY_ON_TOP)
        self.controller=controller
        self.current=current
        self.busy=False
        self.stale=False
        self.initial_focus=True
        self.speaker=Auto()
        self.setupDialog()
        self.render(current)
        self.Bind(wx.EVT_CLOSE,self.on_close)
        self.Bind(wx.EVT_CHAR_HOOK,self.on_key)
        self.Bind(wx.EVT_SHOW,self.on_show)

    def makeSettings(self, settingsSizer):
        self.status=wx.StaticText(self,label='Match options')
        settingsSizer.addItem(self.status,flag=wx.EXPAND|wx.ALL,border=5)
        hint=wx.StaticText(self,label='Changes apply immediately. Tab between controls. Refresh reads the game again. Close returns to the game options screen.')
        hint.Wrap(480)
        settingsSizer.addItem(hint,flag=wx.EXPAND|wx.ALL,border=5)
        self.build_label=wx.StaticText(self,label='&Build mode')
        settingsSizer.addItem(self.build_label,flag=wx.ALL,border=5)
        self.build=wx.Choice(self,choices=['Build','Zero Build'])
        self.build.SetName('Build mode')
        self.build.Bind(wx.EVT_CHOICE,lambda event:self.change('build',self.build.GetStringSelection(),self.build))
        settingsSizer.addItem(self.build,flag=wx.EXPAND|wx.ALL,border=5)
        self.ranked=wx.CheckBox(self,label='&Ranked')
        self.ranked.SetName('Ranked')
        self.ranked.Bind(wx.EVT_CHECKBOX,lambda event:self.change('ranked',self.ranked.GetValue(),self.ranked))
        settingsSizer.addItem(self.ranked,flag=wx.ALL,border=5)
        settingsSizer.addItem(wx.StaticText(self,label='&Team size'),flag=wx.ALL,border=5)
        self.team=wx.Choice(self)
        self.team.SetName('Team size')
        self.team.Bind(wx.EVT_CHOICE,lambda event:self.change('team',self.team.GetStringSelection(),self.team))
        settingsSizer.addItem(self.team,flag=wx.EXPAND|wx.ALL,border=5)
        self.fill=wx.CheckBox(self,label='Team &fill')
        self.fill.SetName('Team fill')
        self.fill.Bind(wx.EVT_CHECKBOX,lambda event:self.change('fill',self.fill.GetValue(),self.fill))
        settingsSizer.addItem(self.fill,flag=wx.ALL,border=5)
        self.fill_help=wx.StaticText(self,label='')
        settingsSizer.addItem(self.fill_help,flag=wx.EXPAND|wx.ALL,border=5)
        self.refresh=wx.Button(self,label='Re&fresh from Fortnite')
        self.refresh.Bind(wx.EVT_BUTTON,lambda event:self.run(self.controller.focus_and_read,self.refresh))
        settingsSizer.addItem(self.refresh,flag=wx.EXPAND|wx.ALL,border=5)
        close=wx.Button(self,wx.ID_CANCEL,label='&Close')
        close.Bind(wx.EVT_BUTTON,self.on_close)
        settingsSizer.addItem(close,flag=wx.EXPAND|wx.ALL,border=5)

    def render(self,current):
        self.current=current
        self.stale=False
        self.status.SetLabel(current.mode_name+'. '+current.summary())
        self.build_label.Show(current.build is not None)
        self.build.Show(current.build is not None)
        self.ranked.Show(current.ranked is not None)
        if current.build is not None:
            self.build.SetStringSelection(current.build)
        self.ranked.SetValue(current.ranked is True)
        self.team.Set(list(current.teams))
        self.team.SetStringSelection(current.team)
        self.fill.SetValue(current.fill is True)
        self.fill.SetLabel('Team &fill' if current.fill is not None else 'Team fill (locked by Fortnite)')
        self.fill_help.SetLabel('Team Fill is locked by Fortnite for the current settings.' if current.fill is None else 'Checked: fill empty team slots. Unchecked: do not fill.')
        for control in (self.build,self.ranked,self.team):
            control.Enable()
        self.fill.Enable(current.fill is not None)
        self.Layout()

    def change(self,field,value,control):
        if self.busy or self.stale:
            return
        expected=self.current
        self.run(lambda:self.controller.apply_option(expected,field,value),control)

    def run(self,operation,focus):
        if self.busy:
            return
        self.busy=True
        state.match_options_busy.set()
        self.SetWindowStyleFlag(self.GetWindowStyleFlag() & ~wx.STAY_ON_TOP)
        # Keep the modal event loop alive while Fortnite is foreground.
        def work():
            try:
                result,error=operation(),None
            except Exception as exc:
                result,error=None,str(exc)
            wx.CallAfter(self.finished,result,error,focus)
        threading.Thread(target=work,name='MatchOptionsApply',daemon=True).start()

    def finished(self,result,error,focus):
        self.busy=False
        if error:
            self.stale=True
            self.status.SetLabel(error)
            for control in (self.build,self.ranked,self.team,self.fill):
                control.Disable()
            message=error+' Use Refresh to read the current settings.'
            focus=self.refresh
        else:
            self.render(result)
            message=result.summary()
            if not focus.IsEnabled() or not focus.IsShown():
                focus=self.team
        self.SetWindowStyleFlag(self.GetWindowStyleFlag() | wx.STAY_ON_TOP)
        self.Show()
        force_focus_window(self,focus_widget=focus)
        state.match_options_busy.clear()
        self.speaker.speak(message)

    def on_show(self,event):
        if event.IsShown() and self.initial_focus:
            self.initial_focus=False
            wx.CallAfter(self.focus_first_option)
        event.Skip()

    def focus_first_option(self):
        (self.build if self.build.IsShown() else self.team).SetFocus()

    def on_key(self,event):
        if event.GetKeyCode()==wx.WXK_ESCAPE:
            self.on_close(event)
        else:
            event.Skip()

    def on_close(self,event):
        if self.busy:
            return
        if self.IsModal():
            self.EndModal(wx.ID_CANCEL)
        else:
            self.Destroy()
