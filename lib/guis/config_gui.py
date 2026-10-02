"""
Configuration view for FA11y
Provides interface for user configuration of settings, values, and keybinds.

ConfigView is a panel that the hub shows as the Settings and Keybinds pages
(each with its own subset of tabs) and that ViewDialog shows as a popup
when the hub isn't running.
"""
import logging
import time
import configparser
from typing import Callable, Dict, Optional, List, Any, Tuple, TYPE_CHECKING

import wx
import wx.lib.scrolledpanel as scrolled
from lib.hub.accessibility import annotate
from lib.hub.controls import StyledButton, TabbedBook
from lib.guis.config_layout import (
    CONTROL_WIDTH, KEY_WIDTH, group_for, finish_sections, reset_sections, section_for, setting_label,
)
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import DisplayableError
from lib.guis.view_host import EmbeddedView, ViewDialog, show_view
from lib.utilities.utilities import DEFAULT_CONFIG, read_config, get_maps_with_game_objects
from lib.utilities.input import (
    get_pressed_key_combination, validate_key_combination, get_pressed_main_keys, is_key_pressed
)
from lib.config_schema import (
    ALL_TABS, CANT_USE_KEY, TRACKED_ELSEWHERE, KeybindTable, VolumeTester, bind_message, default_section_for_key,
    default_value_string, extract_value_and_description, get_value_range, key_name, map_items, number_spec,
    target_section, tab_items, volume_percent,
)

if TYPE_CHECKING:
    from lib.utilities.utilities import Config

logger = logging.getLogger(__name__)
speaker = Auto()


# Tab routing, labels, groups, defaults and keybind rules live in lib/config_schema.py,
# which the new window reads too.
_key_name = key_name


class ConfigView(EmbeddedView):
    """Configuration panel with instant opening via deferred widget creation.

    ``tabs`` picks which tabs to show (None means all). With a single tab no
    notebook is created and that tab's panel fills the view.
    """

    def __init__(self, parent, config: 'Config', update_callback: Callable,
                 tabs: Optional[List[str]] = None, default_config_str=None):
        if tabs is None:
            self.tab_names = list(ALL_TABS)
            self.view_title = "FA11y Configuration"
        else:
            self.tab_names = [t for t in tabs if t in ALL_TABS]
            self.view_title = self.tab_names[0] if len(self.tab_names) == 1 else "Settings"
        super().__init__(parent)

        self.config = config
        self.update_callback = update_callback
        self.default_config_str = default_config_str if default_config_str else DEFAULT_CONFIG
        # While General is shown, its keys leave their natural tabs.
        self._general_active = "General" in self.tab_names

        # Quick initialization
        self.maps_with_objects = get_maps_with_game_objects() if "GameObjects" in self.tab_names else {}
        self.keytable = KeybindTable({})
        self.volume_tester = VolumeTester()
        self.tab_widgets = {}
        self.tab_variables = {}
        self.capturing_key = False
        self.capture_widget = None
        self.capture_action = None
        self.original_capture_value = ""
        self.tab_control_widgets = {}
        self.notebook: Optional[TabbedBook] = None
        self._populated = False
        # (tab name, setting key) of every widget changed since the last save.
        self._dirty_keys: set = set()

        # Polling timer picks up mouse buttons (EVT_CHAR_HOOK can't see them).
        self._capture_timer: Optional[wx.Timer] = None
        # Keys already held when capture starts (e.g. the Enter that
        # activated the button) - ignored until physically released so the
        # activator is never sampled as the user's binding.
        self._capture_ignore_keys: set = set()

        self._build_structure()

    @property
    def _dirty(self) -> bool:
        return bool(self._dirty_keys)

    # ------------------------------------------------------------------
    # EmbeddedView protocol
    # ------------------------------------------------------------------

    def activate(self) -> None:
        self._ensure_populated()

    def prefetch(self) -> None:
        """Build the widgets while the hub is idle, before the page is first shown."""
        self._ensure_populated()

    def deactivate(self) -> None:
        """The page was hidden or the window is closing: stop capture, save changes."""
        if self.capturing_key:
            self._cancel_capture()
        self._cleanup_test_audio()
        self.save_changes()

    def handle_escape(self) -> bool:
        """Escape cancels a key capture; otherwise the host hides or closes the view."""
        if self.capturing_key:
            self._cancel_capture()
            speaker.speak("Cancelled")
            return True
        return False

    def initial_focus(self) -> Optional[wx.Window]:
        self._ensure_populated()
        first_tab = self.tab_names[0] if self.tab_names else None
        widgets = self.tab_control_widgets.get(first_tab) or []
        if widgets:
            return widgets[0]
        if self.notebook is not None:
            return self.notebook
        return None

    # ------------------------------------------------------------------

    def _build_structure(self):
        """Create view structure with minimal content"""
        sizer = wx.BoxSizer(wx.VERTICAL)
        if len(self.tab_names) > 1:
            self.notebook = TabbedBook(self)
            sizer.Add(self.notebook, 1, wx.EXPAND)
            self.notebook.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, self.onPageChanged)
        self.SetSizer(sizer)

        # Create empty tabs
        self.create_tabs()
        if self.notebook is None and self.tab_names:
            sizer.Add(self.tabs[self.tab_names[0]], 1, wx.EXPAND)

        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

        # Defer heavy operations
        wx.CallAfter(self._ensure_populated)

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self._stop_capture_polling()
            self._cleanup_test_audio()
        event.Skip()

    def _cleanup_test_audio(self):
        self.volume_tester.cleanup()

    def _ensure_populated(self):
        """Populate the active tab now (once); queue the rest for background build."""
        if self._populated or not self:
            return
        self._populated = True
        try:
            self.analyze_config()

            self._tab_built = {tab_name: False for tab_name in self.tabs}
            self._prebuild_queue: List[str] = []

            active_tab = self.get_current_tab_name()
            if active_tab is None and self.tab_names:
                active_tab = self.tab_names[0]

            self._build_tab(active_tab)
            self.Layout()

            self._prebuild_queue = [
                t for t in self.tabs if t != active_tab and not self._tab_built.get(t, False)
            ]
            if self._prebuild_queue:
                wx.CallLater(50, self._prebuild_next)
        except Exception as e:
            logger.exception(f"Error populating widgets: {e}")
            speaker.speak(f"Error loading configuration: {e}")

    def _prebuild_next(self) -> None:
        """Build the next queued tab, then reschedule."""
        if not self:
            return
        if not getattr(self, '_prebuild_queue', None):
            return

        tab_name = self._prebuild_queue.pop(0)
        if not self._tab_built.get(tab_name, False):
            try:
                self._build_tab(tab_name)
            except Exception as e:
                logger.error(f"Error pre-building tab {tab_name!r}: {e}")

        if self._prebuild_queue:
            wx.CallLater(50, self._prebuild_next)

    def _build_tab(self, tab_name: str) -> None:
        """Construct widgets for a single tab. Idempotent; cheap to call again."""
        if tab_name not in self.tabs:
            return
        if self._tab_built.get(tab_name):
            return

        panel = self.tabs[tab_name]
        panel.Freeze()
        try:
            self.create_widgets(target_tab=tab_name)
            finish_sections(panel, tab_name)
            self.build_tab_control_lists(target_tab=tab_name)
        finally:
            panel.Thaw()
        panel.Layout()
        self._tab_built[tab_name] = True

    def build_tab_control_lists(self, target_tab: Optional[str] = None):
        """Rebuild focusable-widget lists. ``target_tab=None`` does all tabs."""
        if target_tab is not None:
            if target_tab not in self.tabs:
                return
            self.tab_control_widgets[target_tab] = []
            self._collect_focusable_widgets(
                self.tabs[target_tab], self.tab_control_widgets[target_tab]
            )
            return
        for tab_name, panel in self.tabs.items():
            self.tab_control_widgets[tab_name] = []
            self._collect_focusable_widgets(panel, self.tab_control_widgets[tab_name])

    def _collect_focusable_widgets(self, parent, widget_list):
        """Recursively collect focusable widgets in tab order. Skip hidden subtrees."""
        for child in parent.GetChildren():
            try:
                if not child.IsShown():
                    continue
            except Exception:
                pass
            if isinstance(child, (wx.Button, wx.TextCtrl, wx.CheckBox, wx.SpinCtrl, wx.SpinCtrlDouble,
                                  wx.Choice, wx.ComboBox, wx.ListCtrl)):
                widget_list.append(child)
            elif hasattr(child, 'GetChildren'):
                self._collect_focusable_widgets(child, widget_list)

    def get_current_tab_name(self):
        """Get the name of the currently selected tab"""
        if self.notebook is None:
            return self.tab_names[0] if self.tab_names else None
        selection = self.notebook.GetSelection()
        if selection != wx.NOT_FOUND:
            return self.notebook.GetPageText(selection)
        return None

    def is_last_widget_in_tab(self, widget):
        """Check if the widget is the last focusable widget in its tab"""
        current_tab = self.get_current_tab_name()
        if not current_tab or current_tab not in self.tab_control_widgets:
            return False

        widgets = self.tab_control_widgets[current_tab]
        return widgets and widget == widgets[-1]

    def handle_tab_navigation(self, event):
        """Handle custom tab navigation logic"""
        # With a single tab there's no notebook to jump back to; normal
        # Tab order carries focus on to the next control in the host.
        if self.notebook is not None and not event.ShiftDown():
            focused_widget = self.FindFocus()
            if focused_widget and self.is_last_widget_in_tab(focused_widget):
                self.notebook.SetFocus()
                return True

        return False

    def onPageChanged(self, event):
        """Build the tab on its first visit. The tab control itself tells screen readers its name."""
        page_index = event.GetSelection()
        if page_index >= 0 and page_index < self.notebook.GetPageCount():
            tab_text = self.notebook.GetPageText(page_index)
            # Build this tab on first visit so opening the view stays
            # snappy when the user only ever touches one or two tabs.
            if hasattr(self, '_tab_built') and not self._tab_built.get(tab_text, False):
                self._build_tab(tab_text)
        event.Skip()

    def findWidgetKey(self, widget):
        """Find the setting key for a widget by looking at its parent's label"""
        try:
            parent = widget.GetParent()
            if parent:
                for child in parent.GetChildren():
                    if isinstance(child, wx.StaticText):
                        return child.GetLabel()
        except:
            pass
        return "Unknown setting"
    
    def create_tabs(self):
        """Create empty tab structure"""
        self.tabs = {}

        # Per-map GameObjects sections aren't separate tabs anymore - they
        # render inside the GameObjects tab via a Map dropdown.
        # A lone tab has no notebook; its panel sits directly in the view.
        for tab_name in self.tab_names:
            panel = scrolled.ScrolledPanel(self.notebook if self.notebook is not None else self)
            panel.SetupScrolling(scroll_x=False, scroll_y=True)
            
            if self.notebook is not None:
                self.notebook.AddPage(panel, tab_name)
            self.tabs[tab_name] = panel
            self.tab_widgets[tab_name] = []
            self.tab_variables[tab_name] = {}
            
            # Add loading indicator
            sizer = wx.BoxSizer(wx.VERTICAL)
            loading_text = wx.StaticText(panel, label="Loading settings...")
            sizer.Add(loading_text, flag=wx.ALL, border=10)
            panel.SetSizer(sizer)
    
    def analyze_config(self):
        """Read the keybinds, for conflict checks."""
        self.keytable = KeybindTable.from_parser(self.config.config)

    def create_widgets(self, target_tab: Optional[str] = None):
        """Create widgets. ``target_tab`` filters to one tab (None means all of them)."""
        # GameObjects gets a special map-dropdown layout; route there.
        if target_tab == "GameObjects":
            self._build_gameobjects_tab_layout()
            return
        if target_tab == "General":
            self._build_general_tab_layout()
            return

        if target_tab is None:
            self._build_gameobjects_tab_layout()
            self._build_general_tab_layout()
            panels_to_reset = [(n, p) for n, p in self.tabs.items() if n not in ("GameObjects", "General")]
        else:
            if target_tab not in self.tabs:
                return
            panels_to_reset = [(target_tab, self.tabs[target_tab])]
        for tab_name, panel in panels_to_reset:
            panel.DestroyChildren()
            panel.sizer = wx.BoxSizer(wx.VERTICAL)
            panel.SetSizer(panel.sizer)
            reset_sections(panel)

        for tab_name, panel in panels_to_reset:
            for item in tab_items(self.config.config, tab_name, self._general_active, self.maps_with_objects):
                self._create_item(item)
            panel.SetupScrolling(scroll_x=False, scroll_y=True)

    def _create_item(self, item, parent_override=None) -> None:
        """Create the control for one setting."""
        args = (item.tracking, item.key, item.value_string)
        if item.kind == "check":
            self.create_checkbox(*args, parent_override=parent_override)
        elif item.kind == "volume":
            self.create_volume_entry(*args, parent_override=parent_override)
        elif item.kind == "keybind":
            self.create_keybind_entry(*args, parent_override=parent_override)
        elif item.kind == "choice":
            self.create_choice_entry(*args, item.choices, label_text=item.label, parent_override=parent_override)
        else:
            self.create_value_entry(*args, parent_override=parent_override)

    # ------------------------------------------------------------------
    # General tab - a few settings pulled out of other sections.
    # ------------------------------------------------------------------

    def _build_general_tab_layout(self) -> None:
        """Lay out the General tab: startup/update toggles, then what closing the window does."""
        panel = self.tabs.get("General")
        if panel is None:
            return

        panel.DestroyChildren()
        panel.sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(panel.sizer)
        reset_sections(panel)

        self.tab_widgets["General"] = []
        self.tab_variables["General"] = {}

        for item in tab_items(self.config.config, "General"):
            self._create_item(item)

        panel.SetupScrolling(scroll_x=False, scroll_y=True)

    # ------------------------------------------------------------------
    # GameObjects tab - universal settings + map dropdown + per-map
    # sub-panels (replaces the old per-map notebook tabs).
    # ------------------------------------------------------------------

    def _build_gameobjects_tab_layout(self) -> None:
        """Lay out the GameObjects tab: universal section, map picker, per-map host."""
        panel = self.tabs.get("GameObjects")
        if panel is None:
            return

        panel.DestroyChildren()
        panel.sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(panel.sizer)
        reset_sections(panel)

        # Reset trackers - Advanced-routed keys keep their existing entries.
        self.tab_widgets["GameObjects"] = []
        self.tab_variables["GameObjects"] = {}

        # 1. Universal [GameObjects] settings (skip ADVANCED_KEYS - those go on Advanced).
        for item in tab_items(self.config.config, "GameObjects"):
            self._create_item(item)

        # 2. Map dropdown row.
        available_maps = sorted(self.maps_with_objects.keys()) if self.maps_with_objects else []
        if 'main' in available_maps:
            available_maps.remove('main')
            available_maps.insert(0, 'main')

        if available_maps:
            section = section_for(panel, "Each map", show_descriptions=False)
            map_label = wx.StaticText(section.parent, label="Map")
            self._gameobjects_map_keys = available_maps
            self._gameobjects_map_choice = wx.Choice(
                section.parent, choices=[m.replace('_', ' ').title() for m in available_maps],
                size=(section.parent.FromDIP(CONTROL_WIDTH * 2), -1),
            )
            self._gameobjects_map_choice.SetSelection(0)
            annotate(self._gameobjects_map_choice, name="Map",
                     description="Pick which map's per-object tracking settings to view and edit.")
            self._gameobjects_map_choice.Bind(wx.EVT_CHOICE, self._on_gameobjects_map_changed)
            section.add_row(map_label, self._gameobjects_map_choice)

        # 3. Sub-panel host. Each map's settings live in its own panel,
        # built lazily on first show, then hidden / shown as the
        # dropdown changes. Keeps state across switches.
        self._gameobjects_subpanel_host = wx.Panel(panel)
        host_sizer = wx.BoxSizer(wx.VERTICAL)
        self._gameobjects_subpanel_host.SetSizer(host_sizer)
        panel.sizer.Add(self._gameobjects_subpanel_host, proportion=1, flag=wx.EXPAND)

        self._gameobjects_subpanels = {}  # map_name -> wx.Panel

        if available_maps:
            self._show_gameobjects_map(available_maps[0])

        try:
            panel.SetupScrolling(scroll_x=False, scroll_y=True)
        except Exception:
            pass

    def _on_gameobjects_map_changed(self, event):
        idx = self._gameobjects_map_choice.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        try:
            map_name = self._gameobjects_map_keys[idx]
        except (IndexError, AttributeError):
            return
        self._show_gameobjects_map(map_name)

    def _show_gameobjects_map(self, map_name: str) -> None:
        """Hide every map sub-panel, build / show the requested one."""
        host = getattr(self, "_gameobjects_subpanel_host", None)
        if host is None:
            return

        # Hide all currently visible.
        for sub in self._gameobjects_subpanels.values():
            sub.Hide()

        # Build on first request.
        if map_name not in self._gameobjects_subpanels:
            sub = wx.Panel(host)
            sub_sizer = wx.BoxSizer(wx.VERTICAL)
            sub.SetSizer(sub_sizer)
            self._build_per_map_widgets(sub, map_name)
            finish_sections(sub, f"{map_name.title()}GameObjects")
            self._gameobjects_subpanels[map_name] = sub
            host.GetSizer().Add(sub, proportion=1, flag=wx.EXPAND)

        self._gameobjects_subpanels[map_name].Show()
        host.Layout()
        host.GetParent().Layout()
        # Refresh tab-order list so Tab navigation skips the hidden maps.
        self.build_tab_control_lists(target_tab="GameObjects")

    def _build_per_map_widgets(self, parent_panel, map_name: str) -> None:
        """Build per-object widgets for ``map_name`` onto ``parent_panel``.

        Widgets are tracked under the ``<MapName>GameObjects`` key in
        ``tab_variables`` so the existing save logic still routes each
        value back to its real config section.
        """
        section_name = f"{map_name.title()}GameObjects"
        if not self.config.config.has_section(section_name):
            return

        # Reset trackers for this section (we may rebuild on reset).
        self.tab_widgets[section_name] = []
        self.tab_variables[section_name] = {}

        for item in map_items(self.config.config, map_name):
            self._create_item(item, parent_override=parent_panel)

    def _resolve_widget_parent(self, tab_name: str, parent_override=None):
        """Pick the wx parent for a widget. ``parent_override`` lets the
        GameObjects map sub-panels host widgets that are still tracked
        under a per-map ``tab_name`` key in ``tab_variables``."""
        if parent_override is not None:
            return parent_override
        return self.tabs.get(TRACKED_ELSEWHERE.get(tab_name, tab_name))

    def _ensure_tracking(self, tab_name: str) -> None:
        """Make sure ``tab_widgets`` / ``tab_variables`` have entries for a
        non-notebook tracking key (e.g. ``MainGameObjects``)."""
        if tab_name not in self.tab_widgets:
            self.tab_widgets[tab_name] = []
        if tab_name not in self.tab_variables:
            self.tab_variables[tab_name] = {}

    def _section(self, tab_name: str, key: str, parent_override=None):
        """The group box ``key`` goes in, or None if its tab isn't shown."""
        container = self._resolve_widget_parent(tab_name, parent_override)
        if container is None:
            return None
        per_map = tab_name.endswith("GameObjects") and tab_name != "GameObjects"
        return section_for(container, group_for(tab_name, key),
                           show_descriptions=tab_name != "Keybinds" and not per_map)

    def create_checkbox(self, tab_name: str, key: str, value_string: str, parent_override=None):
        """Create a checkbox for a boolean setting."""
        section = self._section(tab_name, key, parent_override)
        if section is None:
            return

        value, description = self.extract_value_and_description(value_string)
        checkbox = wx.CheckBox(section.parent, label=setting_label(key, tab_name))
        checkbox.SetValue(value.lower() == 'true')
        checkbox.description = description  # saved with the value
        annotate(checkbox, description=description)

        checkbox.Bind(wx.EVT_CHAR_HOOK, self.onControlCharHook)
        self._track_changes(checkbox, tab_name, key)

        self._ensure_tracking(tab_name)
        self.tab_widgets[tab_name].append(checkbox)
        self.tab_variables[tab_name][key] = checkbox
        section.add_check(checkbox, description)

    def _number_control(self, parent, key: str, value: str):
        """A SpinCtrl for whole numbers or a SpinCtrlDouble for decimals, or
        None when ``value`` isn't a number."""
        spec = number_spec(key, value)
        if spec is None:
            return None
        size = (parent.FromDIP(CONTROL_WIDTH), -1)
        if spec["decimals"]:
            control = wx.SpinCtrlDouble(parent, size=size, min=spec["min"], max=spec["max"],
                                        initial=spec["value"], inc=spec["step"])
            control.SetDigits(spec["decimals"])
            return control
        return wx.SpinCtrl(parent, size=size, min=spec["min"], max=spec["max"], initial=spec["value"])

    def create_value_entry(self, tab_name: str, key: str, value_string: str, parent_override=None):
        """Create a number box (or a text field for non-numbers) for a value setting."""
        section = self._section(tab_name, key, parent_override)
        if section is None:
            return

        value, description = self.extract_value_and_description(value_string)
        label = wx.StaticText(section.parent, label=setting_label(key, tab_name))
        entry = self._number_control(section.parent, key, value)
        if entry is None:
            entry = wx.TextCtrl(section.parent, value=value, style=wx.TE_PROCESS_ENTER,
                                size=(section.parent.FromDIP(CONTROL_WIDTH * 2), -1))
            entry.Bind(wx.EVT_CHAR_HOOK, self.onTextCharHook)
        entry.description = description  # saved with the value
        annotate(entry, name=label.GetLabel(), description=description)
        self._track_changes(entry, tab_name, key)

        self._ensure_tracking(tab_name)
        self.tab_widgets[tab_name].extend([label, entry])
        self.tab_variables[tab_name][key] = entry
        section.add_row(label, entry, description)

    def create_volume_entry(self, tab_name: str, key: str, value_string: str, parent_override=None):
        """Create a volume entry field with test button."""
        section = self._section(tab_name, key, parent_override)
        if section is None:
            return

        value, description = self.extract_value_and_description(value_string)
        label = wx.StaticText(section.parent, label=setting_label(key, tab_name))
        scaled_value = volume_percent(value)

        entry = wx.SpinCtrl(section.parent, size=(section.parent.FromDIP(CONTROL_WIDTH), -1),
                            min=0, max=100, initial=scaled_value)
        entry.description = description  # saved with the value
        annotate(entry, name=label.GetLabel(), description=description)

        test_button = StyledButton(section.parent, label="Test")
        annotate(test_button, name=f"Test {setting_label(key, tab_name)}")

        self._track_changes(entry, tab_name, key)
        test_button.Bind(wx.EVT_BUTTON, lambda evt: self.test_volume(key, str(entry.GetValue() / 100.0)))

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(entry, 0, wx.ALIGN_CENTER_VERTICAL)
        row.Add(test_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, section.parent.FromDIP(8))

        self._ensure_tracking(tab_name)
        self.tab_widgets[tab_name].extend([label, entry, test_button])
        self.tab_variables[tab_name][key] = entry
        section.add_row(label, row, description)

    def create_choice_entry(self, tab_name: str, key: str, value_string: str,
                            choices, label_text: Optional[str] = None, parent_override=None):
        """Create a drop-down for a setting with a fixed set of values.

        ``choices`` is a sequence of (config value, label shown to the user).
        """
        section = self._section(tab_name, key, parent_override)
        if section is None:
            return

        value, description = self.extract_value_and_description(value_string)
        text = label_text or setting_label(key, tab_name)
        label = wx.StaticText(section.parent, label=text)

        choice = wx.Choice(section.parent, choices=[shown for _value, shown in choices],
                           size=(section.parent.FromDIP(CONTROL_WIDTH * 2), -1))
        choice.SetName(text)
        choice.choice_values = [stored for stored, _text in choices]
        selected = 0
        if value.lower() in choice.choice_values:
            selected = choice.choice_values.index(value.lower())
        choice.SetSelection(selected)
        choice.description = description  # saved with the value
        annotate(choice, name=text, description=description)

        self._track_changes(choice, tab_name, key)

        self._ensure_tracking(tab_name)
        self.tab_widgets[tab_name].extend([label, choice])
        self.tab_variables[tab_name][key] = choice
        section.add_row(label, choice, description)

    def _track_changes(self, widget, tab_name: str, key: str) -> None:
        """Mark the setting as changed whenever the user edits ``widget``."""
        def changed(event):
            self._dirty_keys.add((tab_name, key))
            event.Skip()

        if isinstance(widget, wx.CheckBox):
            widget.Bind(wx.EVT_CHECKBOX, changed)
        elif isinstance(widget, wx.SpinCtrl):
            widget.Bind(wx.EVT_SPINCTRL, changed)
            widget.Bind(wx.EVT_TEXT, changed)
        elif isinstance(widget, wx.SpinCtrlDouble):
            widget.Bind(wx.EVT_SPINCTRLDOUBLE, changed)
            widget.Bind(wx.EVT_TEXT, changed)
        elif isinstance(widget, wx.Choice):
            widget.Bind(wx.EVT_CHOICE, changed)
        elif isinstance(widget, wx.TextCtrl):
            widget.Bind(wx.EVT_TEXT, changed)

    def create_keybind_entry(self, tab_name: str, key: str, value_string: str, parent_override=None):
        """Create a keybind row: the action's name, then a button showing its key.

        The button only draws the key ("Left Ctrl"), but its label, which is
        what screen readers read, is the whole "Fire: Left Ctrl".
        """
        section = self._section(tab_name, key, parent_override)
        if section is None:
            return

        value, description = self.extract_value_and_description(value_string)
        label = wx.StaticText(section.parent, label=key)

        # The raw stored combination lives on the button; the label only
        # shows a readable name and is never parsed back.
        keybind_button = StyledButton(section.parent, label=key,
                                      size=(section.parent.FromDIP(KEY_WIDTH), -1))
        keybind_button.description = description  # saved with the value
        annotate(keybind_button, description=description)
        self._set_keybind_value(key, keybind_button, value)

        keybind_button.Bind(wx.EVT_CHAR_HOOK, self.onControlCharHook)
        keybind_button.Bind(wx.EVT_BUTTON, lambda evt: self.capture_keybind(key, keybind_button))

        self._ensure_tracking(tab_name)
        self.tab_widgets[tab_name].extend([label, keybind_button])
        self.tab_variables[tab_name][key] = keybind_button
        section.add_row(label, keybind_button, description)

    def onControlCharHook(self, event):
        """Handle char events for controls to disable arrow navigation"""
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB:
            if self.handle_tab_navigation(event):
                return
            event.Skip()
            return
        
        if key_code in [wx.WXK_UP, wx.WXK_DOWN, wx.WXK_LEFT, wx.WXK_RIGHT]:
            return
        
        event.Skip()
    
    def onTextCharHook(self, event):
        """Handle char events for text controls"""
        key_code = event.GetKeyCode()
        
        if key_code == wx.WXK_TAB:
            if self.handle_tab_navigation(event):
                return
            event.Skip()
            return
        
        if key_code in [wx.WXK_UP, wx.WXK_DOWN]:
            return
        
        event.Skip()
    
    def get_value_range(self, key: str) -> tuple:
        """Get reasonable min/max values for numeric settings"""
        return get_value_range(key)

    def test_volume(self, volume_key: str, volume_value: str):
        """Test a volume setting by playing an appropriate sound"""
        try:
            volume = float(volume_value)
        except ValueError:
            return
        master = 1.0
        if 'MasterVolume' in self.tab_variables.get("Audio", {}):
            try:
                master = float(self.tab_variables["Audio"]['MasterVolume'].GetValue()) / 100.0
            except Exception:
                master = 1.0
        self.volume_tester.play(volume_key, volume, master)

    def _set_keybind_value(self, action_name: str, button: wx.Button, value: str) -> None:
        """Store a key combination on its button and show a readable label.

        ``button.key_value`` is the raw value that gets saved; the label is
        for display only and is never parsed back.
        """
        value = (value or "").strip()
        button.key_value = value
        shown = _key_name(value) if value else "Unbound"
        button.display_text = shown
        button.SetLabel(f"{action_name}: {shown}")

    def _find_keybind_button(self, action_name: str) -> Optional[wx.Button]:
        return self.tab_variables.get("Keybinds", {}).get(action_name)

    def capture_keybind(self, action_name: str, button_widget: wx.Button):
        """Start capturing a new keybind"""
        button_widget.display_text = "Press any key..."
        button_widget.SetLabel(f"{action_name}: Press any key...")

        self.capturing_key = True
        self.capture_widget = button_widget
        self.capture_action = action_name
        self.original_capture_value = getattr(button_widget, 'key_value', "")

        # Snapshot whatever is held right now (e.g. the Enter that activated
        # this button). Those keys are excluded from capture until released,
        # so the activator can't become the binding - but the user's first
        # real keypress is captured immediately, even if it lands before an
        # all-keys-up polling tick.
        self._capture_ignore_keys = get_pressed_main_keys()
        self._start_capture_polling()

    def _start_capture_polling(self):
        """Start a wx.Timer that polls global key state during keybind capture."""
        if self._capture_timer is None:
            self._capture_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._on_capture_timer, self._capture_timer)
        if not self._capture_timer.IsRunning():
            self._capture_timer.Start(30)

    def _stop_capture_polling(self):
        """Stop the capture polling timer if it's running."""
        if self._capture_timer is not None and self._capture_timer.IsRunning():
            self._capture_timer.Stop()

    def _on_capture_timer(self, _event):
        """Timer tick - try to capture a keybind from current global key state."""
        if not self.capturing_key:
            self._stop_capture_polling()
            return
        self.handle_key_capture()

    def _end_capture(self):
        self.capturing_key = False
        self.capture_widget = None
        self.capture_action = None
        self._stop_capture_polling()

    def _cancel_capture(self):
        """Restore the captured button's label and exit capture mode."""
        if self.capture_widget is not None and self.capture_action is not None:
            self._set_keybind_value(
                self.capture_action, self.capture_widget, self.original_capture_value
            )
        self._end_capture()

    def _clear_key(self, action_name: str, button: wx.Button) -> bool:
        """Unbind ``action_name``. Returns True if it had a key."""
        changed = self.keytable.clear(action_name)
        self._set_keybind_value(action_name, button, "")
        if changed:
            self._dirty_keys.add(("Keybinds", action_name))
        return bool(changed)

    def _bind_key(self, action_name: str, button: wx.Button, new_key: str) -> str:
        """Bind ``new_key`` to ``action_name``, swapping with any action that already uses it.

        The other action gets this action's previous key (or becomes unbound
        if there wasn't one). Returns a sentence describing the swap, or ""
        when the key was free.
        """
        note, changed = self.keytable.bind(action_name, new_key)
        for action, value in changed.items():
            other = button if action == action_name else self._find_keybind_button(action)
            if other is not None:
                self._set_keybind_value(action, other, value)
            self._dirty_keys.add(("Keybinds", action))
        self._set_keybind_value(action_name, button, new_key)
        return note

    def handle_key_capture(self):
        """Handle key capture using input utilities"""
        if not self.capturing_key:
            return

        # Ignored keys stay excluded only while continuously held; once
        # released, a re-press is a genuine capture attempt.
        if self._capture_ignore_keys:
            self._capture_ignore_keys = {
                k for k in self._capture_ignore_keys if is_key_pressed(k)
            }

        new_key = get_pressed_key_combination(exclude_keys=self._capture_ignore_keys)

        if new_key:
            action = self.capture_action
            button = self.capture_widget
            if validate_key_combination(new_key):
                note = self._bind_key(action, button, new_key)
                message = bind_message(action, new_key, note)
            else:
                self._set_keybind_value(action, button, self.original_capture_value)
                message = CANT_USE_KEY

            self._end_capture()
            speaker.speak(message)

    def onKeyEvent(self, event):
        """Handle key events for shortcuts and capture"""
        key_code = event.GetKeyCode()
        focused = self.FindFocus()

        if self.capturing_key:
            if key_code == wx.WXK_ESCAPE:
                self.handle_escape()
                return
            else:
                self.handle_key_capture()
                return

        # Ctrl+F → setting search. Handled before single-letter shortcuts so
        # the F doesn't fall through to anything else.
        if event.ControlDown() and key_code in (ord('F'), ord('f')):
            self._open_search_dialog()
            return

        if key_code == wx.WXK_TAB:
            if self.handle_tab_navigation(event):
                return

        # The single-letter shortcuts below should NOT fire when a modifier
        # is held - Ctrl+R / Ctrl+T would otherwise hijack browser-style
        # combos and trigger reset/test unexpectedly.
        modifier_held = (event.ControlDown() or event.AltDown() or event.MetaDown())

        if not modifier_held and key_code in (ord('R'), ord('r')):
            if focused:
                self.reset_focused_setting(focused)
                return
        elif key_code == wx.WXK_DELETE:
            if focused and self.is_keybind_button(focused):
                self.unbind_keybind(focused)
                return
        elif not modifier_held and key_code in (ord('T'), ord('t')):
            if focused and self.is_volume_entry(focused):
                self.test_focused_volume(focused)
                return

        event.Skip()

    # ------------------------------------------------------------------
    # Ctrl+F search
    # ------------------------------------------------------------------

    def _open_search_dialog(self) -> None:
        """Show the search popup; navigate to the chosen setting on accept."""
        try:
            self._ensure_all_settings_built()
            entries = self._build_search_index()
        except Exception as e:
            logger.error(f"Error building search index: {e}")
            speaker.speak("Search unavailable.")
            return

        if not entries:
            speaker.speak("No settings to search.")
            return

        speaker.speak("Search settings.")
        dlg = _SettingSearchDialog(self, entries)
        try:
            if dlg.ShowModal() == wx.ID_OK and dlg.result is not None:
                tab_internal, key = dlg.result
                self._navigate_to_setting(tab_internal, key)
        finally:
            dlg.Destroy()

    def _ensure_all_settings_built(self) -> None:
        """Build every notebook tab and every per-map GameObjects sub-panel
        so ``self.tab_variables`` covers the full setting space."""
        if not hasattr(self, "_tab_built"):
            return

        # 1. Force-build any deferred notebook tabs.
        for tab_name in list(self.tabs.keys()):
            if not self._tab_built.get(tab_name, False):
                try:
                    self._build_tab(tab_name)
                except Exception as e:
                    logger.error(f"Error pre-building tab {tab_name!r}: {e}")

        # 2. Force-build per-map GameObjects sub-panels (they're lazy-built
        #    by the Map dropdown, so non-default maps may have no widgets yet).
        host = getattr(self, "_gameobjects_subpanel_host", None)
        map_keys = getattr(self, "_gameobjects_map_keys", None)
        subpanels = getattr(self, "_gameobjects_subpanels", None)
        if host is None or not map_keys or subpanels is None:
            return
        for map_name in map_keys:
            if map_name in subpanels:
                continue
            try:
                sub = wx.Panel(host)
                sub.SetSizer(wx.BoxSizer(wx.VERTICAL))
                self._build_per_map_widgets(sub, map_name)
                finish_sections(sub, f"{map_name.title()}GameObjects")
                sub.Hide()
                subpanels[map_name] = sub
                host.GetSizer().Add(sub, proportion=1, flag=wx.EXPAND)
            except Exception as e:
                logger.error(f"Error pre-building per-map widgets for {map_name!r}: {e}")

    def _build_search_index(self):
        """Return ``[(tab_display, tab_internal, key, description), ...]`` for
        every setting widget tracked in ``tab_variables``."""
        entries: List[Tuple[str, str, str, str]] = []
        for tab_internal, widgets in self.tab_variables.items():
            if not widgets:
                continue
            # Per-map sections like "MainGameObjects" render inside the
            # GameObjects tab via the Map dropdown - show that in the label.
            if (tab_internal.endswith("GameObjects")
                    and tab_internal != "GameObjects"):
                map_token = tab_internal[:-len("GameObjects")]
                # Convert "Main" / "Reload_Oasis" → human text.
                map_display = map_token.replace('_', ' ').strip()
                tab_display = f"GameObjects ({map_display})"
            else:
                tab_display = TRACKED_ELSEWHERE.get(tab_internal, tab_internal)
            for key, widget in widgets.items():
                description = ""
                try:
                    description = getattr(widget, "description", "") or ""
                except Exception:
                    description = ""
                entries.append((tab_display, tab_internal, key, description))
        # Stable order: by tab, then key.
        entries.sort(key=lambda e: (e[0].lower(), e[2].lower()))
        return entries

    def _navigate_to_setting(self, tab_internal: str, key: str) -> None:
        """Switch notebook (and per-map dropdown if needed), then focus widget."""
        is_per_map = (tab_internal.endswith("GameObjects")
                      and tab_internal != "GameObjects")
        target_tab = "GameObjects" if is_per_map else TRACKED_ELSEWHERE.get(tab_internal, tab_internal)

        # Switch notebook page (a lone tab has no notebook).
        page_count = self.notebook.GetPageCount() if self.notebook is not None else 0
        for idx in range(page_count):
            if self.notebook.GetPageText(idx) == target_tab:
                if self.notebook.GetSelection() != idx:
                    self.notebook.SetSelection(idx)
                # Lazy-built tabs also need explicit build before focusing.
                if hasattr(self, "_tab_built") and not self._tab_built.get(target_tab, False):
                    try:
                        self._build_tab(target_tab)
                    except Exception:
                        pass
                break

        # If per-map, point the dropdown at the right map and reveal its panel.
        if is_per_map:
            map_token = tab_internal[:-len("GameObjects")]
            map_name = map_token.lower()
            choice = getattr(self, "_gameobjects_map_choice", None)
            map_keys = getattr(self, "_gameobjects_map_keys", None)
            if choice is not None and map_keys:
                try:
                    map_idx = map_keys.index(map_name)
                    choice.SetSelection(map_idx)
                    self._show_gameobjects_map(map_name)
                except (ValueError, AttributeError) as e:
                    logger.error(f"Could not switch to map {map_name!r}: {e}")

        widget = self.tab_variables.get(tab_internal, {}).get(key)
        if widget is not None:
            wx.CallAfter(widget.SetFocus)
            speaker.speak(f"{setting_label(key, tab_internal)} on {target_tab} tab")
        else:
            speaker.speak(f"Could not focus {key}")
    
    def is_keybind_button(self, widget):
        """Check if widget is a keybind button"""
        for tab_name in self.tab_variables:
            if tab_name == "Keybinds":
                for key, button in self.tab_variables[tab_name].items():
                    if button == widget and isinstance(widget, wx.Button):
                        return True
        return False
    
    def is_volume_entry(self, widget):
        """Check if widget is a volume entry"""
        for tab_name in self.tab_variables:
            for key, entry in self.tab_variables[tab_name].items():
                if entry == widget and (key.endswith('Volume') or key == 'MasterVolume'):
                    return True
        return False
    
    def test_focused_volume(self, widget):
        """Test volume for focused widget"""
        for tab_name in self.tab_variables:
            for key, entry in self.tab_variables[tab_name].items():
                if entry == widget:
                    if isinstance(entry, wx.SpinCtrl):
                        volume_value = str(entry.GetValue() / 100.0)
                    else:
                        volume_value = entry.GetValue()
                    self.test_volume(key, volume_value)
                    return
    
    def unbind_keybind(self, widget):
        """Unbind a keybind by setting it to empty"""
        for tab_name in self.tab_variables:
            if tab_name == "Keybinds":
                for action_name, button in self.tab_variables[tab_name].items():
                    if button == widget:
                        self._clear_key(action_name, button)
                        speaker.speak(f"{action_name} unbound")
                        return

    def reset_focused_setting(self, widget):
        """Reset focused setting to default value"""
        for tab_name in self.tab_variables:
            for key, stored_widget in self.tab_variables[tab_name].items():
                if stored_widget == widget:
                    default_full_value = default_value_string(tab_name, key)

                    if not default_full_value:
                        return
                    
                    default_value_part, _ = self.extract_value_and_description(default_full_value)
                    self._dirty_keys.add((tab_name, key))
                    name = setting_label(key, tab_name)
                    
                    if isinstance(widget, wx.CheckBox):
                        bool_value = default_value_part.lower() == 'true'
                        widget.SetValue(bool_value)
                        speaker.speak(f"{name} reset to default: {'checked' if bool_value else 'unchecked'}")
                    elif isinstance(widget, wx.SpinCtrl):
                        if key.endswith('Volume') or key == 'MasterVolume':
                            try:
                                volume_value = float(default_value_part)
                                scaled_value = int(volume_value * 100)
                                widget.SetValue(scaled_value)
                                speaker.speak(f"{name} reset to default: {scaled_value}%")
                            except (ValueError, TypeError):
                                widget.SetValue(100)
                                speaker.speak(f"{name} reset to default: 100%")
                        else:
                            try:
                                numeric_value = int(float(default_value_part))
                                widget.SetValue(numeric_value)
                                speaker.speak(f"{name} reset to default: {numeric_value}")
                            except (ValueError, TypeError):
                                widget.SetValue(0)
                                speaker.speak(f"{name} reset to default: 0")
                    elif isinstance(widget, wx.SpinCtrlDouble):
                        try:
                            widget.SetValue(float(default_value_part))
                        except (ValueError, TypeError):
                            return
                        speaker.speak(f"{name} reset to default: {default_value_part}")
                    elif isinstance(widget, wx.TextCtrl):
                        widget.SetValue(default_value_part)
                        speaker.speak(f"{name} reset to default: {default_value_part}")
                    elif isinstance(widget, wx.Choice):
                        values = getattr(widget, 'choice_values', [])
                        if default_value_part.lower() in values:
                            widget.SetSelection(values.index(default_value_part.lower()))
                            speaker.speak(f"{name} reset to default: {widget.GetStringSelection()}")
                    elif isinstance(widget, wx.Button) and tab_name == "Keybinds":
                        if default_value_part.strip():
                            note = self._bind_key(key, widget, default_value_part.strip())
                            speaker.speak(note or f"{key} reset to default: {_key_name(default_value_part.strip())}")
                        else:
                            self._clear_key(key, widget)
                            speaker.speak(f"{name} reset to default: unbound")

                    return
    
    def extract_value_and_description(self, value_string: str) -> tuple:
        """Extract value and description from a config string"""
        return extract_value_and_description(value_string)

    def _default_section_for_key(self, key: str) -> Optional[str]:
        """Return the default-config section that owns ``key``."""
        return default_section_for_key(key)

    def _widget_value(self, tab_name: str, setting_key: str, widget) -> str:
        """The value to store for ``widget`` (without its description)."""
        if isinstance(widget, wx.CheckBox):
            return 'true' if widget.GetValue() else 'false'
        if isinstance(widget, wx.SpinCtrl):
            if setting_key.endswith('Volume') or setting_key == 'MasterVolume':
                return str(widget.GetValue() / 100.0)
            return str(widget.GetValue())
        if isinstance(widget, wx.SpinCtrlDouble):
            return f"{widget.GetValue():.{widget.GetDigits()}f}"
        if isinstance(widget, wx.Choice):
            values = getattr(widget, 'choice_values', None)
            selection = widget.GetSelection()
            if values and 0 <= selection < len(values):
                return values[selection]
            return widget.GetStringSelection()
        if isinstance(widget, wx.Button) and tab_name == "Keybinds":
            value = getattr(widget, 'key_value', "")
            if value.strip() and not validate_key_combination(value):
                return ""
            return value
        return widget.GetValue()

    def _target_section(self, config_parser_instance, tab_name: str, setting_key: str) -> Optional[str]:
        """The config section a widget on ``tab_name`` is saved to."""
        return target_section(config_parser_instance, tab_name, setting_key)

    def _apply_changes_to(self, config_parser_instance) -> None:
        """Write this view's changed widgets onto ``config_parser_instance``."""
        for tab_name, setting_key in sorted(self._dirty_keys):
            widget = self.tab_variables.get(tab_name, {}).get(setting_key)
            if widget is None:
                continue
            description = getattr(widget, 'description', '')
            value_to_save = self._widget_value(tab_name, setting_key, widget)
            value_string_to_save = f"{value_to_save} \"{description}\"" if description else str(value_to_save)

            target_section = self._target_section(config_parser_instance, tab_name, setting_key)
            if target_section is None:
                logger.warning(
                    f"save_changes: no section found for key {setting_key!r}, skipping"
                )
                continue
            if not config_parser_instance.has_section(target_section):
                config_parser_instance.add_section(target_section)
            config_parser_instance.set(target_section, setting_key, value_string_to_save)

    def save_changes(self) -> bool:
        """Save what changed since the last save. Returns True if anything was saved.

        The config is re-read fresh and only this view's changed widgets are
        applied to it, so the Settings and Keybinds views never overwrite
        each other's changes.
        """
        if not self._dirty_keys:
            return False
        try:
            config_parser_instance = read_config(use_cache=False)
            self._apply_changes_to(config_parser_instance)
            self.update_callback(config_parser_instance)
            self.config.config = config_parser_instance
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            speaker.speak("Error saving configuration.")
            try:
                if self.IsShownOnScreen():
                    DisplayableError(
                        f"Error saving configuration: {str(e)}",
                        "Configuration Error"
                    ).displayError(self)
            except Exception:
                pass
            return False

        self._dirty_keys.clear()
        speaker.speak("Configuration saved and applied.")
        return True


class _SettingSearchDialog(wx.Dialog):
    """Ctrl+F search popup for the config GUI.

    Shows a TextCtrl + ListBox. Typing live-filters the entries by
    substring match against ``key + description``. Up/Down from the
    text field move the list selection so the user never has to leave
    the search box. Enter accepts; Esc cancels. ``self.result`` is set
    to ``(tab_internal, key)`` on accept, ``None`` on cancel.
    """

    def __init__(self, parent: wx.Window, entries):
        super().__init__(parent, title="Search settings",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self._entries = entries
        self._filtered = list(entries)
        self.result = None

        sizer = wx.BoxSizer(wx.VERTICAL)

        prompt = wx.StaticText(
            self,
            label="Type to filter. Up/Down moves selection. Enter jumps to setting.",
        )
        sizer.Add(prompt, flag=wx.ALL, border=8)

        self._search = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        sizer.Add(self._search, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

        self._list = wx.ListBox(self, style=wx.LB_SINGLE)
        sizer.Add(self._list, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

        self._status = wx.StaticText(self, label="")
        sizer.Add(self._status, flag=wx.LEFT | wx.RIGHT | wx.BOTTOM, border=8)

        self.SetSizer(sizer)
        self.SetSize((560, 440))
        self.SetMinSize((400, 320))
        self.CentreOnParent()

        self._search.Bind(wx.EVT_TEXT, self._on_text)
        self._search.Bind(wx.EVT_TEXT_ENTER, self._on_accept)
        self._search.Bind(wx.EVT_CHAR_HOOK, self._on_search_char_hook)
        self._list.Bind(wx.EVT_LISTBOX_DCLICK, self._on_accept)
        self._list.Bind(wx.EVT_CHAR_HOOK, self._on_list_char_hook)

        self._populate_list("")
        # Search field gets focus by default - start typing immediately.
        wx.CallAfter(self._search.SetFocus)

    def _populate_list(self, query: str) -> None:
        q = query.lower().strip()
        if not q:
            self._filtered = list(self._entries)
        else:
            terms = q.split()
            scored = []
            for entry in self._entries:
                _, tab_internal, key, description = entry
                key_l = setting_label(key, tab_internal).lower()
                hay = f"{key_l} {key.lower()} {description.lower()}"
                if not all(t in hay for t in terms):
                    continue
                if key_l == q:
                    score = -1000
                elif key_l.startswith(q):
                    score = -500
                elif q in key_l:
                    score = -100
                else:
                    score = 0
                scored.append((score, key_l, entry))
            scored.sort(key=lambda x: (x[0], x[1]))
            self._filtered = [e for _, _, e in scored]

        self._list.Clear()
        for tab_display, tab_internal, key, _description in self._filtered:
            self._list.Append(f"{setting_label(key, tab_internal)}, {tab_display}")
        if self._filtered:
            self._list.SetSelection(0)
        count = len(self._filtered)
        self._status.SetLabel(f"{count} match{'es' if count != 1 else ''}")

    def _on_text(self, _event):
        self._populate_list(self._search.GetValue())

    def _move_selection(self, delta: int) -> None:
        count = self._list.GetCount()
        if count == 0:
            return
        sel = self._list.GetSelection()
        if sel == wx.NOT_FOUND:
            sel = 0
        new = max(0, min(count - 1, sel + delta))
        if new != sel:
            self._list.SetSelection(new)

    def _on_search_char_hook(self, event):
        key_code = event.GetKeyCode()
        if key_code == wx.WXK_DOWN:
            self._move_selection(1)
            return
        if key_code == wx.WXK_UP:
            self._move_selection(-1)
            return
        if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_accept(event)
            return
        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()

    def _on_list_char_hook(self, event):
        key_code = event.GetKeyCode()
        if key_code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_accept(event)
            return
        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()

    def _on_accept(self, _event):
        sel = self._list.GetSelection()
        if sel == wx.NOT_FOUND or sel >= len(self._filtered):
            return
        _tab_display, tab_internal, key, _description = self._filtered[sel]
        self.result = (tab_internal, key)
        self.EndModal(wx.ID_OK)


class ConfigGUI(ViewDialog):
    """ConfigView in a modal dialog; takes the same arguments as ConfigView."""

    def __init__(self, parent, config, update_callback: Callable,
                 default_config_str=None, tabs: Optional[List[str]] = None):
        super().__init__(
            parent,
            lambda host: ConfigView(host, config, update_callback, tabs=tabs,
                                    default_config_str=default_config_str),
            size=(700, 600),
        )
        self.SetMinSize((400, 350))


def launch_config_gui(config_obj: 'Config',
                     update_callback: Callable[[configparser.ConfigParser], None],
                     default_config_str: Optional[str] = None) -> None:
    """Show the configuration: the hub's Settings page, or a dialog without the hub."""
    try:
        app = wx.GetApp()
        if app is None:
            app = wx.App(False)

        show_view(
            'settings',
            lambda host: ConfigView(host, config_obj, update_callback,
                                    default_config_str=default_config_str),
            size=(700, 600),
        )

    except Exception as e:
        logger.exception(f"Error launching configuration GUI: {e}")
        error = DisplayableError(
            f"Error launching configuration GUI: {str(e)}",
            "Application Error"
        )
        error.displayError()
