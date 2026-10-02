# Moving FA11y's window from wxPython to WPF

## Why

The FA11y window (the "hub") runs on wxPython inside the same Python
process as screen capture, OCR, audio and the keyboard hook. Python runs
one thread at a time, so the window waits whenever those threads are
busy, and wx needs workarounds for screen readers (ReadableText, Dynamic
Annotation, PageStack). The new window is a separate WPF program,
`FA11y.UI.exe`, that does nothing but draw and handle input. Python
becomes a background core that owns everything else.

WPF exposes UI Automation for every control, which is what NVDA, JAWS
and Narrator read, so focus, names, descriptions and announcements work
without workarounds.

## Shape

```
FA11y Launcher.exe
  └─ pythonw FA11y.py            the core: detection, audio, keybinds, Epic APIs,
     │                           in-game wx dialogs (for now)
     └─ FA11y.UI.exe             the window: sidebar, pages, tray icon
         stdin/stdout: JSON Lines
```

* The core starts `FA11y.UI.exe` with redirected stdin and stdout. The two
  talk in JSON Lines (one UTF-8 JSON object per line). The UI never prints
  anything else to stdout; it logs to `logs/ui.log`.
* When the core exits, the UI sees end of file on stdin and exits. When
  the UI exits unexpectedly, the core starts it again (at most 3 times a
  minute), then falls back to the wx window.
* If `FA11y.UI.exe` is missing or the config says
  `[Hub] Interface = classic`, the core uses the wx window as before. The
  wx hub stays in the repo until every page is ported and tested.

### Messages

```json
{"type": "request",  "id": 7, "method": "account.state", "params": {}}
{"type": "response", "id": 7, "ok": true, "result": {...}}
{"type": "response", "id": 7, "ok": false, "error": "message"}
{"type": "event",    "name": "home.changed", "data": {...}}
```

* Both sides can send requests and events. Request ids are per sender.
* The UI calls core methods (`home.status`, `settings.schema`,
  `fortnite.install`, ...). The core runs each request on a worker
  thread, so a slow request never blocks another one. Handlers that need
  wx (the Epic sign-in dialog, in-game dialogs) hop to the wx thread.
* The core sends events for things the UI should react to:
  `ui.summon`, `ui.show_page`, `ui.hide`, `keybinds.changed`,
  `fortnite.running`, `update.available`, `views.reset`, `ui.notify`,
  `ui.announce`, `ui.quit`, and `<page>.changed` for a page's data (`social.changed`,
  `locker.changed`, also sent after signing in or out).
* Long operations (Fortnite install) return an operation id at once and
  report progress as `operation.progress` and `operation.finished` events.

* Phase 3 operations (`fortnite.install`, `update`, `verify`, `move`,
  `uninstall`, `import_egl`, `egl_sync`) answer `{id, name}` and then send
  `operation.progress {id, percent, message}` (percent is null when unknown)
  and `operation.finished {id, ok, message, cancelled}`; `fortnite.cancel`
  stops the running one. First-run setup is shown by the window when it gets
  `setup.start` (or `setup: true` in `core.hello`) and ends with the request
  `setup.finish {save, answers, egl}`.

### Python side

* `lib/shell/bridge.py`: starts the UI process, reads and writes messages,
  routes requests to handlers, and lets core code send events. Thread safe.
* `lib/shell/remote_hub.py`: `RemoteHub`, which has the same public
  methods the rest of FA11y calls on the wx `HubFrame` (`show_page`,
  `summon`, `toggle`, `quit`, `reset_views`, `login_settled`, `page`,
  `current_page`, `has_page`, `notify`, `update_available_changed`,
  `start_onboarding`, `play_fortnite`, `services`, `IsShown`). Calls turn
  into events. `has_page` is true only for pages the UI has ported, so
  actions for unported pages keep opening their wx dialogs.
* `lib/shell/handlers/<page>.py`: the requests for each page. Handlers
  hold no UI code. Logic that lives inside wx views today moves into
  wx-free functions that both the old view and the handler call.
* Game watching and keybind syncing move from `HubFrame` into `RemoteHub`.

### UI side (`ui/`)

```
ui/
  FA11y.UI.sln
  src/FA11y.UI/            WPF app (net9.0-windows, RollForward=Major)
    App.xaml               theme dictionaries, startup
    Core/                  Bridge (JSON Lines client), CoreClient, models
    Theme/                 Colors.xaml, Controls.xaml (all control styles)
    Controls/              ReadableText, StatusCard, Card, IconButton, ...
    Shell/                 MainWindow, Sidebar, tray icon, close dialog
    Pages/                 one UserControl per page
  tests/FA11y.UI.Probe/    UI Automation probe: walks the window like NVDA
  tests/fake_core.py       scripted core for UI tests without FA11y
  bin/                     published FA11y.UI.exe (framework dependent)
```

* Colors, fonts and spacing come from `lib/hub/theme.py` and
  `lib/hub/controls.py` so the window looks the same: dark surfaces, the
  blue accent, 8 px radius, Segoe UI 10 pt, Tabler icons from
  `assets/icons`.
* Accessibility rules carried over from the wx work, which followed
  NVDA's own settings dialog:
  * Arrowing through the sidebar changes the page. Focus stays in the
    sidebar and nothing is spoken except the item.
  * Enter or Tab moves into the page. F6 switches between the sidebar and
    the page. Ctrl+Tab and Ctrl+Shift+Tab cycle pages (or tabs inside a
    page). Escape leaves a sub-view, then returns to the sidebar, then
    hides the window when Fortnite is running.
  * Read-only information is a focusable text element whose name is the
    full text, so Tab reads it. Status cards read their title, value and
    detail.
  * Every control has a name. Descriptions use HelpText.
  * Messages that aren't tied to focus (signed out, keybind swapped,
    "N loaded") use UI Automation notification events, which NVDA speaks.
    The core's own speech (accessible_output2) stays for in-game speech.
  * "Loading…" shows as focusable text while a page loads. If focus was
    in the page, it moves to that text.
* The window is never shown minimized: the core starts the UI with
  `STARTF_USESHOWWINDOW` and `SW_SHOWNORMAL`, calls
  `AllowSetForegroundWindow` for it, and the UI activates itself on first
  show (with the zero-distance mouse move fallback the wx hub uses).

## Pages and order of work

| Phase | Work | Python source it replaces |
|---|---|---|
| 1 | Bridge, RemoteHub, fallback, WPF shell, theme, controls, tray icon, close dialog, Home, Epic account, About, probe tool, fake core | `lib/hub/frame.py`, `sidebar.py`, `controls.py`, `widgets.py`, `pages/home.py`, `pages/account.py`, `pages/about.py` |
| 2 | Settings and Keybinds editor (schema built in Python, generic editor in WPF, search, reset, volume test, key capture) | `lib/guis/config_gui.py`, `config_layout.py`, `lib/hub/pages/settings.py` |
| 3 | Fortnite page (install, update, verify, move, uninstall, launch options, mouse passthrough), first-run setup | `lib/hub/pages/fortnite.py`, `lib/hub/onboarding.py`, `lib/guis/welcome_wizard.py` |
| 4 | Discover, Quests and passes | `lib/guis/discovery_gui.py`, `quest_gui.py`, `passes_gui.py` |
| 5 | Social, Locker | `lib/guis/social_gui.py`, `locker_gui.py` |
| 6 | Packaging: publish to `ui/bin`, Windows Desktop Runtime component in `installer/manifest.json`, sync excludes for `ui/src` and `ui/tests`, CI build check, clean install test in the VM | `installer/`, `.github/workflows/` |
| Later | In-game dialogs (POI selector, visited objects, custom POI, match options, Epic sign-in) and removing wx | `lib/guis/*` |

Unported pages appear in the new sidebar with a button that opens the
existing wx window, so nothing is lost between phases.

## Checks for every phase

* `python -m pytest` passes (the one old timing test excepted).
* `dotnet build` has no warnings in new code.
* The probe passes: every sidebar item changes the page without moving
  focus, every control in tab order has a name and the right role, cards
  read their full text, nothing is unnamed.
* Startup: the window is visible and focused within 1 s of the core
  starting it. Page switches under 50 ms. Memory reported.
* Screenshots of every page compared against the wx window for colors,
  spacing and focus rings.
* Speech checked with NVDA's speech viewer for the sidebar, Home and one
  form page.
* End to end through `FA11y Launcher.exe` in FA11y-Test: no console
  windows, the window comes to the front, closing and the tray work.

## Runtime version

The machine that builds this has the .NET 9 SDK. The app targets
`net9.0-windows` with `RollForward=Major`, so it also runs on the .NET 10
Windows Desktop Runtime. .NET 8 and 9 support ends in November 2026, so
the installer component installs the .NET 10 Windows Desktop Runtime, and
the target moves to `net10.0-windows` once a .NET 10 SDK is installed.
