using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Automation;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using FA11y.UI.Controls;
using FA11y.UI.Core;
using FA11y.UI.Pages;

namespace FA11y.UI.Shell;

/// <summary>
/// The window: brand header, the sidebar of pages, and the page area. Arrowing through the sidebar
/// changes the page and leaves focus on the sidebar. Enter, Right arrow or Tab goes into the page,
/// F6 switches between the sidebar and the page, Ctrl+Tab cycles pages, and Escape leaves a
/// sub-view, then returns to the sidebar, then hides the window when Fortnite is running.
/// </summary>
public partial class MainWindow : Window
{
    private sealed record PageSpec(string Key, string Label, string Icon, string Group);

    private static readonly PageSpec[] Specs =
    {
        new("home", "Home", "home", ""),
        new("fortnite", "Fortnite", "device-gamepad-2", "Play"),
        new("discover", "Discover", "compass", "Play"),
        new("account", "Epic account", "user", "Account"),
        new("locker", "Locker", "shirt", "Account"),
        new("social", "Social", "users", "Account"),
        new("quests", "Quests and passes", "list-check", "Account"),
        new("settings", "Settings", "settings", "FA11y"),
        new("keybinds", "Keybinds", "keyboard", "FA11y"),
        new("about", "About and updates", "info-circle", "FA11y"),
    };

    private readonly Dictionary<string, IHubPage> _pages = new();
    private readonly Dictionary<string, NavListItem> _items = new();
    private TrayIcon? _tray;
    private string? _current;
    private bool _selecting;
    private bool _summonedOverGame;
    private bool _quitting;
    private bool _userMinimized;
    private bool _closing;
    private bool? _reportedVisible;
    private bool? _reportedActive;
    private bool _starting;
    private DispatcherTimer? _startupTimeout;

    public MainWindow()
    {
        InitializeComponent();
        WindowTools.UseDarkTitleBar(this);

        string? previous = null;
        foreach (var spec in Specs)
        {
            var icon = TryFindResource($"Icon.{spec.Icon}") as Geometry;
            var item = new NavListItem(spec.Key, spec.Label, icon, spec.Group, spec.Group.Length > 0 && spec.Group != previous);
            previous = spec.Group;
            _items[spec.Key] = item;
            Sidebar.Items.Add(item);
        }
        Setup.Finished += ExitSetup;
        Sidebar.SelectionChanged += OnSidebarSelectionChanged;
        Sidebar.Activate += FocusContent;

        PreviewKeyDown += OnPreviewKeyDown;
        KeyDown += OnKeyDown;
        IsVisibleChanged += (_, _) => ReportVisibility();
        Activated += (_, _) => ReportVisibility();
        Deactivated += (_, _) => ReportVisibility();
        StateChanged += (_, _) =>
        {
            ReportVisibility();
            // Only the user's own minimize (title bar button, taskbar, Alt+Space, Windows+Down) goes to the
            // tray. Windows+D and Windows+M minimize every window without SC_MINIMIZE; FA11y stays put then.
            if (WindowState == WindowState.Minimized && _userMinimized)
                _ = MinimizeToTrayAsync();
            _userMinimized = false;
        };
        SourceInitialized += (_, _) =>
            System.Windows.Interop.HwndSource.FromHwnd(new System.Windows.Interop.WindowInteropHelper(this).Handle)
                ?.AddHook(WatchMinimize);

        SubscribeToCore();
        ShowPage("home", fromUser: false);
        if (App.Bridge.Connected)
            BeginStartup();
        else
            Startup.Visibility = Visibility.Collapsed;
    }

    // Startup screen ----------------------------------------------------------

    /// <summary>The sidebar and pages stay out of reach until the core says startup is done.</summary>
    private void BeginStartup()
    {
        _starting = true;
        MainArea.Visibility = Visibility.Hidden;
        Startup.Visibility = Visibility.Visible;
        Startup.Opacity = 1;
        _startupTimeout?.Stop();
        _startupTimeout = new DispatcherTimer { Interval = TimeSpan.FromSeconds(60) };
        _startupTimeout.Tick += (_, _) =>
        {
            Log.Error("startup.done did not arrive within 60 seconds; showing the window anyway");
            EndStartup(focus: true);
        };
        _startupTimeout.Start();
    }

    // Keybind capture ----------------------------------------------------------------------------------

    private Action<MouseButton>? _captureMouse;
    private (WindowState State, WindowStyle Style, ResizeMode Resize)? _beforeCapture;

    public bool KeyCaptureShown => _captureMouse != null;

    /// <summary>
    /// Go full screen and fade to the "press a key" screen while a keybind waits for its key. The keybind
    /// button keeps keyboard focus under the overlay; mouse buttons pressed anywhere go to onMouse.
    /// </summary>
    public void ShowKeyCapture(string action, Action<MouseButton> onMouse)
    {
        _captureMouse = onMouse;
        KeyCaptureTitle.Text = $"Press a key to bind to {action}";
        if (_beforeCapture == null)
        {
            _beforeCapture = (WindowState, WindowStyle, ResizeMode);
            // Style None before maximizing, or the maximized window stops at the taskbar.
            if (WindowState == WindowState.Maximized)
                WindowState = WindowState.Normal;
            WindowStyle = WindowStyle.None;
            ResizeMode = ResizeMode.NoResize;
            WindowState = WindowState.Maximized;
        }
        if (KeyCaptureOverlay.Visibility != Visibility.Visible)
            KeyCaptureOverlay.Opacity = 0;
        KeyCaptureOverlay.Visibility = Visibility.Visible;
        // Opacity only: a hidden MainArea would take keyboard focus away from the keybind button.
        Fade(MainArea, 0, null);
        Fade(KeyCaptureOverlay, 1, null);
    }

    /// <summary>Back from the "press a key" screen: restore the window and fade the pages back in.</summary>
    public void HideKeyCapture()
    {
        if (_captureMouse == null)
            return;
        _captureMouse = null;
        if (_beforeCapture is { } before)
        {
            _beforeCapture = null;
            WindowState = WindowState.Normal;
            WindowStyle = before.Style;
            ResizeMode = before.Resize;
            WindowState = before.State;
        }
        Fade(MainArea, 1, null);
        Fade(KeyCaptureOverlay, 0, () => KeyCaptureOverlay.Visibility = Visibility.Collapsed);
    }

    private void Fade(UIElement element, double to, Action? done)
    {
        void Finish()
        {
            element.BeginAnimation(OpacityProperty, null);
            element.Opacity = to;
            done?.Invoke();
        }
        if (!IsVisible || !SystemParameters.ClientAreaAnimation)
        {
            Finish();
            return;
        }
        var animation = new System.Windows.Media.Animation.DoubleAnimation(to, TimeSpan.FromMilliseconds(200));
        // Only the last fade of an element finishes it; a newer one replaces this.
        animation.Completed += (_, _) =>
        {
            if (Math.Abs(element.Opacity - to) < 0.001)
                Finish();
        };
        element.BeginAnimation(OpacityProperty, animation);
    }

    private void OnKeyCaptureMouseDown(object sender, MouseButtonEventArgs e)
    {
        e.Handled = true;
        _captureMouse?.Invoke(e.ChangedButton);
    }

    /// <summary>Fade the startup screen out and the sidebar and pages in. No animation if the window is hidden or animations are off.</summary>
    private void EndStartup(bool focus)
    {
        _startupTimeout?.Stop();
        if (!_starting)
            return;
        _starting = false;
        focus |= Startup.IsKeyboardFocusWithin;
        MainArea.Visibility = Visibility.Visible;
        void Finish()
        {
            Startup.Visibility = Visibility.Collapsed;
            MainArea.BeginAnimation(OpacityProperty, null);
            MainArea.Opacity = 1;
        }
        if (!IsVisible || !SystemParameters.ClientAreaAnimation)
        {
            Finish();
        }
        else
        {
            MainArea.Opacity = 0;
            MainArea.BeginAnimation(OpacityProperty, new System.Windows.Media.Animation.DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(250)));
            var fade = new System.Windows.Media.Animation.DoubleAnimation(1, 0, TimeSpan.FromMilliseconds(300));
            fade.Completed += (_, _) => Finish();
            Startup.BeginAnimation(OpacityProperty, fade);
        }
        if (focus && !Setup.IsActive)
        {
            ShowPage("home", fromUser: false);
            Dispatcher.BeginInvoke(DispatcherPriority.Input, FocusSidebar);
        }
    }

    private void OnStartupProgress(JsonElement data)
    {
        if (!_starting)
            return;
        var percent = data.TryGetProperty("percent", out var p) && p.ValueKind == JsonValueKind.Number ? (int)p.GetDouble() : 0;
        Startup.Set(percent, data.Str("message"));
    }

    // Startup ---------------------------------------------------------------

    /// <summary>
    /// Everything that can wait until after the first paint: the tray icon, the other pages, and
    /// telling the core the window is up (which makes it send core.hello).
    /// </summary>
    public void FinishStartup()
    {
        try
        {
            _tray = new TrayIcon(
                open: () => Summon(false, false),
                play: () => App.Bridge.Notify("app.play_fortnite"),
                settings: () => App.Bridge.Notify("app.show_page", new { key = "settings", summon = true }),
                quit: RequestQuit);
        }
        catch (Exception e)
        {
            Log.Error("Creating the tray icon failed", e);
        }
        App.Bridge.Ready();
        App.Bridge.SendEvent("ui.ready");
        _reportedVisible = _reportedActive = null;
        ReportVisibility();

        // Build the remaining pages while idle, so the first visit to each is instant.
        foreach (var spec in Specs)
        {
            var key = spec.Key;
            Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, () => GetPage(key));
        }
    }

    private void SubscribeToCore()
    {
        var bridge = App.Bridge;
        bridge.On("core.hello", hello =>
        {
            AppState.ApplyHello(hello);
            if (hello.Bool("starting") && !hello.Bool("setup"))
            {
                if (!_starting)
                    BeginStartup();
                if (hello.TryGetProperty("startup", out var startup))
                    OnStartupProgress(startup);
            }
            else
                EndStartup(focus: false);
            var page = hello.Str("page");
            if (page.Length > 0 && _items.ContainsKey(page) && page != _current)
                ShowPage(page, fromUser: false);
            if (hello.Bool("setup"))
                StartSetup(false);
        });
        bridge.On("startup.progress", OnStartupProgress);
        bridge.On("startup.done", _ => EndStartup(focus: true));
        bridge.On("setup.start", data => StartSetup(data.Bool("summon")));
        bridge.On("ui.summon", data => Summon(data.Bool("focus_content"), data.Bool("over_game")));
        bridge.On("ui.show_page", data =>
        {
            var key = data.Str("key");
            if (!_items.ContainsKey(key))
                return;
            ShowPage(key, fromUser: false);
            if (data.Bool("summon"))
                Summon(true, data.Bool("over_game"));
            else if (data.Bool("focus_sidebar"))
                FocusSidebar();
        });
        bridge.On("ui.hide", _ => HideWindow(fromUser: false, refocusGame: false));
        bridge.On("ui.focus_sidebar", _ => FocusSidebar());
        bridge.On("ui.quit", _ => Quit());
        bridge.On("ui.notify", data => _tray?.Notify(data.Str("title"), data.Str("message")));
        bridge.On("keybinds.changed", data => AppState.SetKeybinds(data.Bool("enabled"), data.Str("open_keybind")));
        bridge.On("fortnite.running", data =>
        {
            AppState.SetFortniteRunning(data.Bool("running"));
            RefreshIfShown("home");
        });
        bridge.On("update.available", data =>
        {
            AppState.SetUpdate(data.NullableStr("version"));
            RefreshIfShown("home");
            RefreshIfShown("about");
        });
        bridge.On("home.changed", _ => RefreshIfShown("home"));
        bridge.On("account.changed", _ => RefreshIfShown("account"));
        bridge.On("about.changed", _ => RefreshIfShown("about"));
        bridge.On("fortnite.changed", _ => RefreshIfShown("fortnite"));
        bridge.On("operation.progress", data => FortnitePage?.OnOperationProgress(data));
        bridge.On("operation.finished", data => FortnitePage?.OnOperationFinished(data));
        bridge.On("fortnite.mouse_detected", data => FortnitePage?.OnMouseDetected(data));
        bridge.On("fortnite.launch_failed", data => FortnitePage?.OnLaunchFailed(data));
        bridge.On("fortnite.setup_choice", data => FortnitePage?.OnSetupChoice(data.Str("choice")));
        // These pages keep their data ready before they are opened (after sign in, or when it changes).
        bridge.On("social.changed", _ => GetPage("social").Refresh());
        bridge.On("locker.changed", _ => GetPage("locker").Refresh());
        bridge.On("quests.changed", _ => RefreshIfShown("quests"));
        // Pages that load before they are opened: once the core is up and once sign in has settled,
        // and again after signing in or out.
        bridge.On("core.hello", _ => PrefetchPages());
        bridge.On("account.changed", _ => PrefetchPages());
        bridge.On("views.reset", data =>
        {
            // Signed in or out, or setup changed the config: account pages drop their data and
            // load again, the settings editors reload, shown or not.
            if (!data.TryGetProperty("keys", out var keys) || keys.ValueKind != JsonValueKind.Array)
                return;
            foreach (var key in keys.EnumerateArray().Select(k => k.GetString() ?? ""))
            {
                if (!_items.ContainsKey(key))
                    continue;
                if (GetPage(key) is IPrefetchPage prefetch)
                    prefetch.ResetData();
                else if (_pages.TryGetValue(key, out var page))
                    page.Refresh();
            }
        });
        if (Environment.GetEnvironmentVariable("FA11Y_UI_TEST") == "1")
        {
            bridge.On("test.screenshot", data => SaveScreenshot(data.Str("path")));
            bridge.On("test.locker_category", data => (GetPage("locker") as LockerPage)?.OpenCategoryForTest(data.Str("name")));
            bridge.On("test.social_tab", data => (GetPage("social") as SocialPage)?.SelectTabForTest(data.Str("tab")));
            bridge.On("test.where", _ => ReportTestFocus());
            bridge.On("test.key", data => RaiseTestKey(data.Str("key"), data.Bool("up"), data.Str("mods"), data.Str("held")));
        }
    }

    /// <summary>
    /// Test builds only: press a key in the element that has focus, without needing the window to be in
    /// front (Windows only lets a window that got the last real input take the foreground, which an
    /// unattended test never has). The key goes through the same tunneling and bubbling events as a real one.
    /// </summary>
    /// <summary>Test builds only: the element with focus, in the front-most window that has one.</summary>
    private static IInputElement? TestFocus()
    {
        if (Keyboard.FocusedElement is { } real)
            return real;
        foreach (var window in Application.Current.Windows.OfType<Window>().Reverse())
        {
            if (window.IsVisible && FocusManager.GetFocusedElement(window) is { } focused)
                return focused;
        }
        return null;
    }

    private static void ReportTestFocus()
    {
        var focus = TestFocus() as DependencyObject;
        var name = focus == null ? "" : AutomationProperties.GetName(focus);
        if (focus is ContentControl { Content: string content } && name.Length == 0)
            name = content;
        App.Bridge.SendEvent("test.focused", new { name, type = focus?.GetType().Name ?? "" });
    }

    private void RaiseTestKey(string name, bool up, string mods, string held)
    {
        try
        {
            if (!Enum.TryParse<Key>(name, out var key))
                return;
            // mods: "Control,Shift" held while the key goes down; held: keys to report as held ("LeftShift").
            KeyState.ModifiersOverride = Enum.TryParse<ModifierKeys>(mods.Length > 0 ? mods : "None", out var modifiers)
                ? modifiers : ModifierKeys.None;
            KeyState.HeldOverride = held.Split(',', StringSplitOptions.RemoveEmptyEntries)
                .Select(k => Enum.TryParse<Key>(k, out var parsed) ? parsed : Key.None).ToHashSet();
            var target = TestFocus();
            if (target is not Visual visual || PresentationSource.FromVisual(visual) is not { } source)
                return;
            var args = new KeyEventArgs(Keyboard.PrimaryDevice, source, Environment.TickCount, key)
            {
                RoutedEvent = up ? Keyboard.PreviewKeyUpEvent : Keyboard.PreviewKeyDownEvent,
            };
            target.RaiseEvent(args);
            if (!args.Handled)
            {
                args.RoutedEvent = up ? Keyboard.KeyUpEvent : Keyboard.KeyDownEvent;
                target.RaiseEvent(args);
            }
        }
        catch (Exception e)
        {
            Log.Error("Test key failed", e);
        }
        finally
        {
            KeyState.ModifiersOverride = null;
            KeyState.HeldOverride = null;
        }
    }

    /// <summary>Test builds only (FA11Y_UI_TEST=1): draw the window to a PNG, since screen capture can't see it.</summary>
    private void SaveScreenshot(string path)
    {
        try
        {
            var dpi = VisualTreeHelper.GetDpi(this);
            var content = (FrameworkElement)Content;
            var bitmap = new RenderTargetBitmap((int)Math.Ceiling(content.ActualWidth * dpi.DpiScaleX),
                (int)Math.Ceiling(content.ActualHeight * dpi.DpiScaleY), 96 * dpi.DpiScaleX, 96 * dpi.DpiScaleY,
                PixelFormats.Pbgra32);
            bitmap.Render(content);
            var encoder = new System.Windows.Media.Imaging.PngBitmapEncoder();
            encoder.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bitmap));
            using var file = System.IO.File.Create(path);
            encoder.Save(file);
        }
        catch (Exception e)
        {
            Log.Error("Saving a screenshot failed", e);
        }
    }

    private FortnitePage? FortnitePage => GetPage("fortnite") as FortnitePage;

    // First-run setup -----------------------------------------------------------------

    /// <summary>Show setup instead of the sidebar and pages. Does nothing if it is already showing.</summary>
    private void StartSetup(bool summon)
    {
        if (Setup.IsActive)
            return;
        EndStartup(focus: false);
        Startup.Visibility = Visibility.Collapsed;
        MainArea.Visibility = Visibility.Collapsed;
        Setup.Visibility = Visibility.Visible;
        Title = "FA11y setup";
        Setup.Begin();
        if (summon)
            Summon(false, false);
    }

    /// <summary>Setup is over: back to the sidebar and pages.</summary>
    private void ExitSetup()
    {
        Setup.Visibility = Visibility.Collapsed;
        MainArea.Visibility = Visibility.Visible;
        if (_current != null && _pages.TryGetValue(_current, out var page))
        {
            Title = $"FA11y - {page.Title}";
            page.OnShown();
        }
        FocusSidebar();
    }

    private void PrefetchPages()
    {
        foreach (var spec in Specs)
            if (GetPage(spec.Key) is IPrefetchPage page)
                page.Prefetch();
    }

    private void RefreshIfShown(string key)
    {
        if (_current == key && _pages.TryGetValue(key, out var page))
            page.Refresh();
    }

    // Pages -----------------------------------------------------------------

    private IHubPage GetPage(string key)
    {
        if (_pages.TryGetValue(key, out var existing))
            return existing;
        IHubPage page = key switch
        {
            "home" => new HomePage(),
            "account" => new AccountPage(),
            "about" => new AboutPage(),
            "fortnite" => new FortnitePage(),
            "social" => new SocialPage(),
            "locker" => new LockerPage(),
            "discover" => new DiscoverPage(),
            "quests" => new QuestsPage(),
            "settings" or "keybinds" => new SettingsPage(key),
            _ => throw new ArgumentException($"Unknown page: {key}"),
        };
        var element = (FrameworkElement)page;
        element.Visibility = key == _current ? Visibility.Visible : Visibility.Collapsed;
        PageHost.Children.Add(element);
        _pages[key] = page;
        return page;
    }

    private void ShowPage(string key, bool fromUser)
    {
        if (key == _current)
            return;
        var page = GetPage(key);
        if (_current != null && _pages.TryGetValue(_current, out var old))
        {
            ((FrameworkElement)old).Visibility = Visibility.Collapsed;
            old.OnHidden();
        }
        ((FrameworkElement)page).Visibility = Visibility.Visible;
        _current = key;
        if (!Setup.IsActive)
            Title = $"FA11y - {page.Title}";
        _selecting = true;
        try { Sidebar.SelectedItem = _items[key]; }
        finally { _selecting = false; }
        page.OnShown();
        if (IsLoaded || fromUser)
            App.Bridge.SendEvent("ui.page", new { key });
        if (fromUser)
            App.Bridge.Notify("app.sound", new { name = "navigate" });
    }

    private void OnSidebarSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_selecting || Sidebar.SelectedItem is not NavListItem item)
            return;
        ShowPage(item.Key, fromUser: true);
    }

    private void CyclePage(int step)
    {
        var index = Array.FindIndex(Specs, s => s.Key == _current);
        var key = Specs[(Math.Max(index, 0) + step + Specs.Length) % Specs.Length].Key;
        ShowPage(key, fromUser: true);
        FocusSidebar();
    }

    // Focus -----------------------------------------------------------------

    public void FocusSidebar()
    {
        if (_starting)
        {
            Startup.FocusBar();
            return;
        }
        if (Setup.IsActive)
        {
            Setup.FocusIntro();
            return;
        }
        UpdateLayout();
        Sidebar.FocusSelected();
    }

    public void FocusContent()
    {
        if (_starting)
        {
            Startup.FocusBar();
            return;
        }
        if (Setup.IsActive)
        {
            Setup.FocusIntro();
            return;
        }
        if (_current == null || !_pages.TryGetValue(_current, out var page))
            return;
        UpdateLayout();
        var target = page.FirstFocus();
        if (target == null || !target.Focus())
            ((FrameworkElement)page).MoveFocus(new TraversalRequest(FocusNavigationDirection.First));
    }

    private bool FocusIsInPageTabs() =>
        Keyboard.FocusedElement is DependencyObject focused && FindAncestor<TabControl>(focused) != null;

    private static T? FindAncestor<T>(DependencyObject start) where T : DependencyObject
    {
        for (DependencyObject? node = start; node != null;
             node = node is Visual ? VisualTreeHelper.GetParent(node) : LogicalTreeHelper.GetParent(node))
        {
            if (node is T found)
                return found;
        }
        return null;
    }

    // Showing and hiding -------------------------------------------------------

    private DispatcherTimer? _foregroundTimer;

    /// <summary>Bring the window to the front, like the Open FA11y keybind or the tray icon does.</summary>
    public void Summon(bool focusContent, bool overGame)
    {
        _summonedOverGame = overGame;
        WindowTools.BringToFront(this);
        KeepForeground();
        Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
        {
            if (focusContent)
                FocusContent();
            else
                FocusSidebar();
        });
    }

    /// <summary>
    /// Windows can take the foreground back right after the window comes forward: the hidden
    /// icons flyout closing after a tray click, or the program that had focus when the Open FA11y
    /// keybind was pressed. Check a few times over the next half second and bring the window
    /// forward again if it lost the foreground.
    /// </summary>
    private void KeepForeground()
    {
        _foregroundTimer?.Stop();
        var hwnd = new System.Windows.Interop.WindowInteropHelper(this).Handle;
        var tries = 0;
        var timer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(150) };
        timer.Tick += (_, _) =>
        {
            if (!IsVisible || ++tries > 4)
            {
                timer.Stop();
                return;
            }
            if (NativeMethods.GetForegroundWindow() != hwnd)
                WindowTools.BringToFront(this);
        };
        _foregroundTimer = timer;
        timer.Start();
    }

    private void RequestQuit()
    {
        if (!App.Bridge.Connected)
        {
            Quit();
            return;
        }
        App.Bridge.Notify("app.quit");
        // The core answers by sending ui.quit; if it never does, don't leave a tray icon behind.
        var timer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(5) };
        timer.Tick += (_, _) => Quit();
        timer.Start();
    }

    private IntPtr WatchMinimize(IntPtr hwnd, int msg, IntPtr wParam, IntPtr lParam, ref bool handled)
    {
        const int WM_SYSCOMMAND = 0x0112, SC_MINIMIZE = 0xF020;
        if (msg == WM_SYSCOMMAND && ((int)wParam & 0xFFF0) == SC_MINIMIZE)
            _userMinimized = true;
        return IntPtr.Zero;
    }

    /// <summary>Minimizing hides to the tray unless MinimizeToTray is off.</summary>
    private async Task MinimizeToTrayAsync()
    {
        if (_quitting || !App.Bridge.Connected)
            return;
        try
        {
            var answer = await App.Bridge.RequestAsync("app.minimize_action", null, TimeSpan.FromSeconds(3));
            if (!answer.Bool("to_tray") || WindowState != WindowState.Minimized)
                return;
            HideWindow(fromUser: true, refocusGame: false);
            WindowState = WindowState.Normal; // hidden now, so it comes back normal next time
        }
        catch (Exception e)
        {
            Log.Error("Minimizing to the tray failed", e);
        }
    }

    private void HideWindow(bool fromUser, bool refocusGame)
    {
        // Minimized counts as shown here: the core already heard "not visible" when it was minimized,
        // so it needs to be told the window really was up to give the tray notification.
        var wasShown = IsVisible;
        if (IsVisible)
            Hide();
        _summonedOverGame = false;
        TrimMemoryLater();
        if (fromUser)
            App.Bridge.Notify("app.window_hidden", new { refocus_game = refocusGame, was_shown = wasShown });
    }

    private DispatcherTimer? _trimTimer;

    private void TrimMemoryLater()
    {
        _trimTimer?.Stop();
        _trimTimer = new DispatcherTimer(TimeSpan.FromSeconds(3), DispatcherPriority.ApplicationIdle, (_, _) =>
        {
            _trimTimer?.Stop();
            if (!IsVisible)
                WindowTools.TrimMemory();
        }, Dispatcher);
        _trimTimer.Start();
    }

    public void Quit()
    {
        if (_quitting)
            return;
        _quitting = true;
        _tray?.Dispose();
        _tray = null;
        Application.Current.Shutdown();
    }

    private void ReportVisibility()
    {
        var visible = IsVisible && WindowState != WindowState.Minimized;
        var active = IsActive;
        if (visible == _reportedVisible && active == _reportedActive)
            return;
        _reportedVisible = visible;
        _reportedActive = active;
        App.Bridge.SendEvent("ui.visibility", new { visible, active });
    }

    // Keyboard ------------------------------------------------------------------

    private void OnPreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (Setup.IsActive)
            return; // setup has its own keys
        if (KeyCapture.Active)
            return; // a keybind is waiting for any key, these included
        var modifiers = Keyboard.Modifiers;
        if (e.Key == Key.Tab && (modifiers & ModifierKeys.Control) != 0 && (modifiers & ModifierKeys.Alt) == 0)
        {
            if (FocusIsInPageTabs())
                return; // the tabs inside the page switch instead
            e.Handled = true;
            CyclePage((modifiers & ModifierKeys.Shift) != 0 ? -1 : 1);
        }
        else if (e.Key == Key.F6 && modifiers == ModifierKeys.None)
        {
            e.Handled = true;
            if (Sidebar.IsKeyboardFocusWithin)
                FocusContent();
            else
                FocusSidebar();
        }
    }

    // Escape is handled on the way back up, so a control that used it (a drop-down) keeps it.
    private void OnKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key != Key.Escape || Keyboard.Modifiers != ModifierKeys.None || e.Handled || Setup.IsActive)
            return;
        e.Handled = true;
        if (_current != null && _pages.TryGetValue(_current, out var page) && page.HandleEscape())
            return;
        if (Sidebar.IsKeyboardFocusWithin || _summonedOverGame || AppState.FortniteRunning)
            HideWindow(fromUser: true, refocusGame: true);
        else
            FocusSidebar();
    }

    // Closing -------------------------------------------------------------------

    protected override void OnClosing(CancelEventArgs e)
    {
        base.OnClosing(e);
        if (_quitting || _closing)
            return;
        e.Cancel = true;
        _ = HandleCloseAsync();
    }

    private async Task HandleCloseAsync()
    {
        _closing = true;
        try
        {
            var action = "ask";
            try
            {
                if (App.Bridge.Connected)
                    action = (await App.Bridge.RequestAsync("app.close_action", null, TimeSpan.FromSeconds(5))).Str("action", "ask");
                else
                    action = Dialogs.Quit;
            }
            catch (Exception e)
            {
                Log.Error("Asking for the close action failed", e);
            }

            if (action == "ask")
            {
                var (choice, remember) = Dialogs.AskClose(this);
                if (choice == null)
                    return;
                action = choice;
                if (remember)
                    App.Bridge.Notify("app.set_close_action", new { action });
            }

            if (action == Dialogs.Quit)
            {
                Hide();
                RequestQuit();
            }
            else
            {
                HideWindow(fromUser: true, refocusGame: false);
            }
        }
        catch (Exception e)
        {
            Log.Error("Closing the window failed", e);
        }
        finally
        {
            _closing = false;
        }
    }
}
