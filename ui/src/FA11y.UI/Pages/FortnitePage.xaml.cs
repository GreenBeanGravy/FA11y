using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using System.Windows.Threading;
using FA11y.UI.Controls;
using FA11y.UI.Core;
using FA11y.UI.Shell;
using Microsoft.Win32;

namespace FA11y.UI.Pages;

/// <summary>
/// Fortnite: status, Play, install, update, verify, move, uninstall, launch options and mouse
/// passthrough. Long operations run in the core; this page shows what the core reports with
/// operation.progress and operation.finished and lets the user cancel.
/// </summary>
public partial class FortnitePage : PageBase
{
    private static readonly string[] ApiKeys = { "default", "dx11", "dx12", "performance" };

    private JsonElement _state;
    private bool _haveState;
    private int _refreshToken;

    private bool _busy;
    private long? _operationId;
    private string _operationName = "";
    private readonly List<(string Name, JsonElement Data)> _early = new();

    private bool _checkingUpdates;
    private bool _signingIn;
    private bool _detectingMouse;
    private bool _loadingOptions;
    private bool _mouseAvailable = true;

    public FortnitePage()
    {
        InitializeComponent();
        Summary.Text = "Checking your Fortnite install…";
        ApplyStatus();
        ApplyPlay();
        AppState.Changed += ApplyPlay;
        LoadLaunchOptions();
        LoadMouse();
    }

    public override string Key => "fortnite";
    public override string Title => "Fortnite";

    public override void OnShown()
    {
        if (!_busy)
            Refresh();
        LoadMouse();
    }

    public override void OnHidden() => SaveLaunchOptions();

    public override FrameworkElement? FirstFocus() => PlayButton;

    // Escape doesn't cancel downloads by accident; the Cancel button does.
    public override bool HandleEscape() => false;

    private UIElement Anchor => Host ?? (UIElement)this;

    // Status ----------------------------------------------------------------------

    public override async void Refresh()
    {
        var token = ++_refreshToken;
        try
        {
            var state = await App.Bridge.RequestAsync("fortnite.state", null, TimeSpan.FromSeconds(120));
            if (token != _refreshToken)
                return;
            UseState(state);
        }
        catch (Exception e)
        {
            Log.Error("fortnite.state failed", e);
            if (!_haveState && token == _refreshToken)
                Summary.Text = "Couldn't check your Fortnite install.";
        }
    }

    private void UseState(JsonElement state)
    {
        _state = state;
        _haveState = true;
        if (!_busy && state.TryGetProperty("operation", out var op) && op.ValueKind == JsonValueKind.Object)
        {
            // The window was restarted while an operation runs: pick it up again.
            BeginOperation(op.Str("name"), op.TryGetProperty("id", out var id) && id.TryGetInt64(out var n) ? n : null);
            ShowProgress(op.TryGetProperty("percent", out var p) && p.ValueKind == JsonValueKind.Number ? p.GetDouble() : null,
                op.Str("message"));
        }
        ApplyStatus();
    }

    private void ApplyStatus()
    {
        var hadFocus = IsKeyboardFocusWithin;
        var st = _haveState ? _state : default;
        var checkedOnce = _haveState && st.Bool("checked");
        if (!_checkingUpdates)
            Summary.Text = _haveState ? st.Str("summary") : "Checking your Fortnite install…";
        var installed = checkedOnce && st.Bool("installed");
        var eglOnly = checkedOnce && st.Bool("egl_only");

        SignInCard.Visibility = checkedOnce && st.Bool("show_signin") ? Visibility.Visible : Visibility.Collapsed;
        if (!_signingIn)
            SignInText.Text = "Downloads, updates and Play need your Epic account.";
        EglCard.Visibility = eglOnly && !_busy ? Visibility.Visible : Visibility.Collapsed;
        if (eglOnly)
            EglText.Text = st.Str("egl_text");
        InstallButton.Visibility = checkedOnce && st.Bool("show_install") && !_busy ? Visibility.Visible : Visibility.Collapsed;
        Actions.Visibility = installed && !_busy ? Visibility.Visible : Visibility.Collapsed;
        if (installed)
            UpdateButton.Content = st.Bool("update_available") ? "_Update now" : "Check for _updates";
        ApplyPlay();
        KeepFocus(hadFocus);
    }

    private void ApplyPlay() =>
        PlayButton.Content = AppState.FortniteRunning ? "Fortnite is _running" : "_Play";

    /// <summary>If the control that had focus has just gone away, put focus on Play rather than nowhere.</summary>
    private void KeepFocus(bool hadFocus)
    {
        if (!hadFocus)
            return;
        Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
        {
            if (!IsKeyboardFocusWithin && IsVisible && Keyboard.FocusedElement is null or Window)
                PlayButton.Focus();
        });
    }

    // Long operations ---------------------------------------------------------------

    private async void StartOperation(string name, string method, object? args = null)
    {
        if (_busy)
            return;
        BeginOperation(name, null);
        ShowProgress(0, $"{name}…");
        try
        {
            var result = await App.Bridge.RequestAsync(method, args, TimeSpan.FromSeconds(30));
            _operationId = result.TryGetProperty("id", out var id) && id.TryGetInt64(out var n) ? n : null;
            // Anything the core sent before this answer arrived.
            var early = _early.ToList();
            _early.Clear();
            foreach (var (eventName, data) in early)
                Route(eventName, data);
        }
        catch (Exception e)
        {
            Log.Error($"{method} failed", e);
            _early.Clear();
            EndOperation();
            Summary.Text = e.Message;
            Announcer.Announce(Anchor, e.Message);
            Refresh();
            FocusAfterOperation();
        }
    }

    private void BeginOperation(string name, long? id)
    {
        _busy = true;
        _operationName = name;
        _operationId = id;
        ProgressPanel.Visibility = Visibility.Visible;
        ApplyStatus();
        Dispatcher.BeginInvoke(DispatcherPriority.Input, () => CancelButton.Focus());
    }

    private void EndOperation()
    {
        _busy = false;
        _operationId = null;
        ProgressPanel.Visibility = Visibility.Collapsed;
    }

    private double? _shownPercent;

    private void ShowProgress(double? percent, string message)
    {
        if (percent is { } value)
        {
            Progress.IsIndeterminate = false;
            // Nobody wants a screen reader reading every fraction: the bar moves in whole percents.
            var whole = Math.Round(Math.Max(0, Math.Min(100, value)));
            if (_shownPercent != whole)
            {
                _shownPercent = whole;
                Progress.Value = whole;
            }
        }
        else
        {
            _shownPercent = null;
            Progress.IsIndeterminate = true;
        }
        if (message.Length > 0 && ProgressText.AccessibleText != message)
            ProgressText.Text = message;
    }

    /// <summary>operation.progress from the core.</summary>
    public void OnOperationProgress(JsonElement data) => Route("operation.progress", data);

    /// <summary>operation.finished from the core.</summary>
    public void OnOperationFinished(JsonElement data) => Route("operation.finished", data);

    private void Route(string name, JsonElement data)
    {
        if (!_busy)
            return;
        var id = data.TryGetProperty("id", out var idElement) && idElement.TryGetInt64(out var n) ? n : (long?)null;
        if (_operationId == null)
        {
            _early.Add((name, data)); // the answer to the start request hasn't come yet
            return;
        }
        if (id != _operationId)
            return;
        if (name == "operation.progress")
        {
            ShowProgress(data.TryGetProperty("percent", out var p) && p.ValueKind == JsonValueKind.Number ? p.GetDouble() : null,
                data.Str("message"));
            return;
        }
        var message = data.Str("message");
        EndOperation();
        Summary.Text = message;
        Announcer.Announce(Anchor, message);
        ApplyStatus();
        Refresh();
        FocusAfterOperation();
    }

    private void FocusAfterOperation()
    {
        // Focus was on Cancel, which is gone now. Leave it alone if the user went elsewhere.
        Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
        {
            if (!IsVisible || (Keyboard.FocusedElement is DependencyObject focused && !IsAncestorOf(focused)
                                                          && focused is not Window))
                return;
            foreach (var target in new FrameworkElement[] { PlayButton, InstallButton, EglManageButton })
            {
                if (target.IsVisible)
                {
                    target.Focus();
                    return;
                }
            }
        });
    }

    private void OnCancelClick(object sender, RoutedEventArgs e)
    {
        if (!_busy)
            return;
        ProgressText.Text = "Cancelling…";
        App.Bridge.Notify("fortnite.cancel");
    }

    // Buttons -----------------------------------------------------------------------

    private async void OnPlayClick(object sender, RoutedEventArgs e)
    {
        try
        {
            await App.Bridge.RequestAsync("fortnite.play", null, TimeSpan.FromSeconds(60));
        }
        catch (Exception ex)
        {
            Log.Error("fortnite.play failed", ex);
        }
    }

    /// <summary>fortnite.launch_failed from the core (it has already spoken and played the sound).</summary>
    public void OnLaunchFailed(JsonElement data)
    {
        if (!_checkingUpdates)
            Summary.Text = data.Str("message");
    }

    private async void OnSignInClick(object sender, RoutedEventArgs e)
    {
        if (_signingIn)
            return;
        _signingIn = true;
        SignInText.Text = "Signing in…";
        try
        {
            var result = await App.Bridge.RequestAsync("fortnite.sign_in", null, TimeSpan.FromSeconds(90));
            _signingIn = false;
            var message = result.Str("message");
            Announcer.Announce(Anchor, message);
            if (result.Bool("needs_account"))
                App.Bridge.Notify("app.show_page", new { key = "account", summon = true });
        }
        catch (Exception ex)
        {
            _signingIn = false;
            Log.Error("fortnite.sign_in failed", ex);
            Announcer.Announce(Anchor, "Couldn't sign in.");
        }
        SignInText.Text = "Downloads, updates and Play need your Epic account.";
        Refresh();
    }

    private async void OnInstallClick(object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;
        var start = _haveState ? _state.Str("default_install_base") : "";
        var dialog = new OpenFolderDialog
        {
            Title = "Choose where to install Fortnite. FA11y adds a Fortnite folder inside it.",
            InitialDirectory = System.IO.Directory.Exists(start) ? start : "",
        };
        if (dialog.ShowDialog(Host) != true)
            return;
        var folder = dialog.FolderName;
        string question;
        try
        {
            question = (await App.Bridge.RequestAsync("fortnite.install_question", new { @base = folder })).Str("question");
        }
        catch (Exception ex)
        {
            Log.Error("fortnite.install_question failed", ex);
            Announcer.Announce(Anchor, ex.Message);
            return;
        }
        if (!Dialogs.Confirm(Host, "Install Fortnite", question, defaultYes: true))
        {
            InstallButton.Focus();
            return;
        }
        StartOperation("Installing", "fortnite.install", new { @base = folder });
    }

    private async void OnUpdateClick(object sender, RoutedEventArgs e)
    {
        if (_busy || _checkingUpdates)
            return;
        if (_haveState && _state.Bool("update_available"))
        {
            StartOperation("Updating", "fortnite.update");
            return;
        }
        _checkingUpdates = true;
        Summary.Text = "Checking for updates…";
        string message;
        try
        {
            var state = await App.Bridge.RequestAsync("fortnite.state", new { check_updates = true }, TimeSpan.FromSeconds(120));
            _checkingUpdates = false;
            UseState(state);
            message = state.Str("message");
        }
        catch (Exception ex)
        {
            _checkingUpdates = false;
            Log.Error("Checking for updates failed", ex);
            message = "Couldn't check for updates.";
            ApplyStatus();
        }
        Announcer.Announce(Anchor, message);
        UpdateButton.Focus();
    }

    private void OnVerifyClick(object sender, RoutedEventArgs e) => StartOperation("Verifying", "fortnite.verify");

    private void OnMoveClick(object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;
        var dialog = new OpenFolderDialog { Title = "Choose the folder to move Fortnite into." };
        if (dialog.ShowDialog(Host) != true)
            return;
        StartOperation("Moving", "fortnite.move", new { target = dialog.FolderName });
    }

    private void OnOpenFolderClick(object sender, RoutedEventArgs e) => App.Bridge.Notify("fortnite.open_folder");

    private void OnUninstallClick(object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;
        if (!Dialogs.Confirm(Host, "Uninstall Fortnite",
                "Uninstall Fortnite and delete its files? You'll have to download it again to play."))
            return;
        StartOperation("Uninstalling", "fortnite.uninstall");
    }

    private void OnEglManageClick(object sender, RoutedEventArgs e) => StartOperation("Setting up", "fortnite.import_egl");

    private void OnEglKeepClick(object sender, RoutedEventArgs e) => StartOperation("Syncing", "fortnite.egl_sync");

    /// <summary>After first-run setup: take over ("manage") or sync with ("sync") the Epic Games Launcher install.</summary>
    public void OnSetupChoice(string choice)
    {
        if (choice == "manage")
            StartOperation("Setting up", "fortnite.import_egl");
        else if (choice == "sync")
            StartOperation("Syncing", "fortnite.egl_sync");
    }

    // Launch options -------------------------------------------------------------------

    private async void LoadLaunchOptions()
    {
        try
        {
            var options = await App.Bridge.RequestAsync("fortnite.launch_options");
            _loadingOptions = true;
            var index = Array.IndexOf(ApiKeys, options.Str("api", "default"));
            ApiGroup.SelectedIndex = index < 0 ? 0 : index;
            SkipSplash.IsChecked = options.Bool("skip_splash");
            ExtraArgs.Text = options.Str("extra");
        }
        catch (Exception e)
        {
            Log.Error("fortnite.launch_options failed", e);
        }
        finally
        {
            _loadingOptions = false;
        }
    }

    private void SaveLaunchOptions()
    {
        if (_loadingOptions)
            return;
        var index = ApiGroup.SelectedIndex;
        App.Bridge.Notify("fortnite.save_launch_options", new
        {
            api = ApiKeys[index < 0 ? 0 : index],
            skip_splash = SkipSplash.IsChecked == true,
            extra = ExtraArgs.Text,
        });
    }

    private void OnOptionChanged(object sender, RoutedEventArgs e) => SaveLaunchOptions();

    private void OnExtraBlur(object sender, KeyboardFocusChangedEventArgs e) => SaveLaunchOptions();

    // Mouse passthrough ------------------------------------------------------------------

    private async void LoadMouse()
    {
        if (_detectingMouse)
            return;
        try
        {
            ShowMouse(await App.Bridge.RequestAsync("fortnite.mouse"));
        }
        catch (Exception e)
        {
            Log.Error("fortnite.mouse failed", e);
        }
    }

    private void ShowMouse(JsonElement info)
    {
        _mouseAvailable = info.Bool("available", true);
        MouseText.Text = info.Str("text");
        MouseButton.Content = info.Bool("detected") ? "_Detect mouse again" : "_Detect mouse";
        MouseButton.IsEnabled = _mouseAvailable;
    }

    private async void OnDetectMouseClick(object sender, RoutedEventArgs e)
    {
        if (_detectingMouse || !_mouseAvailable)
            return;
        _detectingMouse = true;
        try
        {
            var result = await App.Bridge.RequestAsync("fortnite.detect_mouse");
            MouseText.Text = result.Str("text");
        }
        catch (Exception ex)
        {
            _detectingMouse = false;
            Log.Error("fortnite.detect_mouse failed", ex);
            LoadMouse();
        }
    }

    /// <summary>fortnite.mouse_detected from the core, after the user moved a mouse (or none moved).</summary>
    public void OnMouseDetected(JsonElement info)
    {
        _detectingMouse = false;
        ShowMouse(info);
    }
}
