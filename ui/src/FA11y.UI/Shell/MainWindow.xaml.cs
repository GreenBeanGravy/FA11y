using System.ComponentModel;
using System.Diagnostics;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
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

    // The same pages, order, icons and sections as the wx hub (lib/hub/pages/__init__.py).
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
    private bool _closing;
    private bool? _reportedVisible;
    private bool? _reportedActive;

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
        StateChanged += (_, _) => ReportVisibility();

        SubscribeToCore();
        ShowPage("home", fromUser: false);
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
                open: RequestSummon,
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
            var page = hello.Str("page");
            if (page.Length > 0 && _items.ContainsKey(page) && page != _current)
                ShowPage(page, fromUser: false);
            if (hello.Bool("setup"))
                StartSetup(false);
        });
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
        if (Environment.GetEnvironmentVariable("FA11Y_UI_TEST") == "1")
            bridge.On("test.screenshot", data => SaveScreenshot(data.Str("path")));
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
            _ => new PlaceholderPage(key, Specs.First(s => s.Key == key).Label),
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

    /// <summary>Bring the window to the front, like the Open FA11y keybind or the tray icon does.</summary>
    public void Summon(bool focusContent, bool overGame)
    {
        _summonedOverGame = overGame;
        WindowTools.BringToFront(this);
        Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
        {
            if (focusContent)
                FocusContent();
            else
                FocusSidebar();
        });
    }

    private void RequestSummon()
    {
        if (App.Bridge.Connected)
            App.Bridge.Notify("app.summon", new { focus_content = false });
        else
            Summon(false, false);
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

    private void HideWindow(bool fromUser, bool refocusGame)
    {
        if (IsVisible)
            Hide();
        _summonedOverGame = false;
        TrimMemoryLater();
        if (fromUser)
            App.Bridge.Notify("app.window_hidden", new { refocus_game = refocusGame });
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
