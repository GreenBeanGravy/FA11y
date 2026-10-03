using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using FA11y.UI.Controls;
using FA11y.UI.Core;
using FA11y.UI.Shell;

namespace FA11y.UI.Pages;

/// <summary>About and updates: the version, checking for updates, folders, and the changelog.</summary>
public partial class AboutPage : PageBase
{
    private const string RepoUrl = "https://github.com/GreenBeanGravy/FA11y";
    private bool _checking;
    private string? _update;
    private bool _canRestart;
    private bool _haveInfo;
    private string _currentBranch = "";
    private List<(string Name, string Label, string Description)> _branches = new();

    public AboutPage()
    {
        InitializeComponent();
        VersionText.SetLines(new TextLine("Loading…", 14.6666667, FontWeights.SemiBold));
        ApplyUpdateText();
        AppState.Changed += () =>
        {
            if (!_haveInfo)
                return;
            _update = AppState.Update;
            _canRestart = AppState.CanRestartToUpdate;
            ShowVersion(AppState.Version);
        };
    }

    public override string Key => "about";
    public override string Title => "About and updates";

    public override void OnShown() => Refresh();

    // The version and update state first, then the buttons.
    public override FrameworkElement? FirstFocus() => VersionText;

    public override async void Refresh()
    {
        try
        {
            var info = await App.Bridge.RequestAsync("about.info");
            _haveInfo = true;
            _update = info.NullableStr("update");
            _canRestart = info.Bool("can_restart_to_update");
            var changelog = info.Str("changelog");
            if (Changelog.Text != changelog)
                Changelog.Text = changelog;
            ShowVersion(info.Str("version"));
        }
        catch (Exception e)
        {
            Log.Error("about.info failed", e);
        }
        await LoadBranchesAsync();
    }

    private async Task LoadBranchesAsync()
    {
        try
        {
            var result = await App.Bridge.RequestAsync("about.branches", null, TimeSpan.FromSeconds(20));
            _currentBranch = result.Str("current");
            _branches = result.GetProperty("branches").EnumerateArray()
                .Select(b => (b.Str("name"), b.Str("label"), b.Str("description"))).ToList();
            var canSwitch = result.Bool("can_switch");
            BranchBox.ItemsSource = _branches.Select(b => b.Label).ToList();
            var index = _branches.FindIndex(b => b.Name == _currentBranch);
            BranchBox.SelectedIndex = index;
            var current = index >= 0 ? _branches[index].Label : _currentBranch;
            BranchText.SetLines(new TextLine($"Branch: {current} ({_currentBranch})", 14.6666667, FontWeights.Normal));
            BranchRow.Visibility = canSwitch && _branches.Count > 1 ? Visibility.Visible : Visibility.Collapsed;
            UpdateBranchControls();
        }
        catch (Exception e)
        {
            Log.Error("about.branches failed", e);
        }
    }

    private void OnBranchChanged(object sender, SelectionChangedEventArgs e) => UpdateBranchControls();

    private void UpdateBranchControls()
    {
        var i = BranchBox.SelectedIndex;
        SwitchButton.IsEnabled = i >= 0 && i < _branches.Count && _branches[i].Name != _currentBranch;
        System.Windows.Automation.AutomationProperties.SetHelpText(BranchBox,
            i >= 0 && i < _branches.Count ? _branches[i].Description : "");
    }

    private void OnSwitchClick(object sender, RoutedEventArgs e)
    {
        var i = BranchBox.SelectedIndex;
        if (i < 0 || i >= _branches.Count || _branches[i].Name == _currentBranch)
            return;
        var b = _branches[i];
        if (!Dialogs.Confirm(Host, "Switch branch",
                $"Switch FA11y to the {b.Label} branch? FA11y will close, update, and start again. Your settings stay."))
            return;
        App.Bridge.Notify("about.switch_branch", new { name = b.Name });
    }

    private void ShowVersion(string version)
    {
        VersionText.SetLines(new TextLine($"FA11y {(version.Length > 0 ? version : "version unknown")}", 14.6666667,
            FontWeights.SemiBold));
        ApplyUpdateText();
    }

    private void ApplyUpdateText()
    {
        if (!_haveInfo)
        {
            UpdateText.Text = "";
            return;
        }
        UpdateText.Text = UpdateMessage();
        RestartButton.Visibility = !string.IsNullOrEmpty(_update) && _canRestart ? Visibility.Visible : Visibility.Collapsed;
    }

    private string UpdateMessage() =>
        !string.IsNullOrEmpty(_update)
            ? $"FA11y {_update} is available." + (_canRestart ? "" : " Run Updater.exe to install it.")
            : "FA11y checks for updates while it runs.";

    private async void OnCheckClick(object sender, RoutedEventArgs e)
    {
        if (_checking)
            return;
        _checking = true;
        UpdateText.Text = "Checking for updates…";
        string message;
        try
        {
            var result = await App.Bridge.RequestAsync("about.check_updates", null, TimeSpan.FromSeconds(60));
            _update = result.NullableStr("update");
            _canRestart = result.Bool("can_restart_to_update");
            var found = result.NullableBool("found");
            if (found == null)
            {
                message = "Couldn't reach GitHub to check for updates.";
                App.Bridge.Notify("app.sound", new { name = "error" });
                ApplyUpdateText();
            }
            else if (found == true)
            {
                ApplyUpdateText();
                message = UpdateMessage();
                AppState.SetUpdate(_update);
            }
            else
            {
                message = "FA11y is up to date.";
                AppState.SetUpdate(null);
                ApplyUpdateText();
                UpdateText.Text = message;
            }
        }
        catch (Exception ex)
        {
            Log.Error("about.check_updates failed", ex);
            message = "Couldn't reach GitHub to check for updates.";
            ApplyUpdateText();
        }
        _checking = false;
        Announcer.Announce(Host ?? (UIElement)this, message);
        CheckButton.Focus();
    }

    private void OnRestartClick(object sender, RoutedEventArgs e) => App.Bridge.Notify("app.restart_to_update");
    private void OnLogsClick(object sender, RoutedEventArgs e) => App.Bridge.Notify("app.open_folder", new { name = "logs" });
    private void OnSettingsClick(object sender, RoutedEventArgs e) => App.Bridge.Notify("app.open_folder", new { name = "config" });
    private void OnGitHubClick(object sender, RoutedEventArgs e) => App.Bridge.Notify("app.open_url", new { url = RepoUrl });
    private void OnSetupClick(object sender, RoutedEventArgs e) => App.Bridge.Notify("app.start_setup");
}
