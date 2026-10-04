using System.Text.Json;
using System.Windows;
using FA11y.UI.Controls;
using FA11y.UI.Core;

namespace FA11y.UI.Pages;

/// <summary>Home: Play button, the Fortnite, Epic account and FA11y cards, the keybind hint and what's new.</summary>
public partial class HomePage : PageBase
{
    private readonly HashSet<string> _inFlight = new();
    private bool _canRestart;
    private string? _pendingUpdate;

    public HomePage()
    {
        InitializeComponent();
        FortniteCard.Set("Loading…");
        AccountCard.Set("Loading…");
        Fa11yCard.Set("Loading…");
        ShowAppState();
        AppState.Changed += () =>
        {
            ShowAppState();
            UpdateRestartButton();
        };
    }

    public override string Key => "home";
    public override string Title => "Home";

    public override void OnShown() => Refresh();

    public override FrameworkElement? FirstFocus() =>
        UpdateButton.Visibility == Visibility.Visible ? UpdateButton : PlayButton;

    /// <summary>Fill in what's known now, then fetch the slower parts; each card fills in as its own check finishes.</summary>
    public override void Refresh()
    {
        ShowAppState();
        _ = LoadInfoAsync();
        _ = LoadCardAsync("home.account", ApplyAccount);
        _ = LoadCardAsync("home.fa11y", ApplyFa11y);
        _ = LoadCardAsync("home.fortnite", ApplyFortnite);
    }

    private void ShowAppState()
    {
        PlayButton.Content = AppState.FortniteRunning ? "Fortnite is running" : "Play Fortnite";
        if (!AppState.HelloReceived)
            return;
        var keybinds = AppState.KeybindsOn ? "FA11y's keybinds are on." : "FA11y's keybinds turn on when Fortnite starts.";
        KeybindText.Text = $"{keybinds} Open this window any time with {AppState.OpenKeybind}.";
    }

    private async Task LoadInfoAsync()
    {
        if (!_inFlight.Add("info"))
            return;
        try
        {
            var info = await App.Bridge.RequestAsync("home.info");
            _canRestart = info.Bool("can_restart_to_update");
            if (WhatsNew.Text != info.Str("whats_new"))
                WhatsNew.Text = info.Str("whats_new");
            AppState.SetKeybinds(info.Bool("keybinds_on"), info.Str("open_keybind"));
            AppState.SetFortniteRunning(info.Bool("fortnite_running"));
            UpdateRestartButton();
        }
        catch (Exception e)
        {
            Log.Error("home.info failed", e);
        }
        finally
        {
            _inFlight.Remove("info");
        }
    }

    private async Task LoadCardAsync(string method, Action<JsonElement> apply)
    {
        if (!_inFlight.Add(method))
            return;
        try
        {
            apply(await App.Bridge.RequestAsync(method));
        }
        catch (Exception e)
        {
            Log.Error($"{method} failed", e);
            var card = method switch
            {
                "home.account" => AccountCard,
                "home.fa11y" => Fa11yCard,
                _ => FortniteCard,
            };
            card.Set("Unknown", "Couldn't check");
        }
        finally
        {
            _inFlight.Remove(method);
        }
    }

    private void ApplyAccount(JsonElement account)
    {
        var name = account.NullableStr("name");
        WelcomeText.Text = string.IsNullOrEmpty(name) ? "Welcome to FA11y" : $"Welcome back, {name}";
        AccountCard.Set(account.Str("value"), account.Str("detail"), account.Str("level"));
    }

    private void ApplyFa11y(JsonElement fa11y)
    {
        Fa11yCard.Set(fa11y.Str("value"), fa11y.Str("detail"), fa11y.Str("level"));
        _pendingUpdate = fa11y.NullableStr("update");
        UpdateRestartButton();
    }

    private void ApplyFortnite(JsonElement fortnite) =>
        FortniteCard.Set(fortnite.Str("value"), fortnite.Str("detail"), fortnite.Str("level"));

    private void UpdateRestartButton()
    {
        var show = (!string.IsNullOrEmpty(_pendingUpdate) || !string.IsNullOrEmpty(AppState.Update))
                   && (_canRestart || AppState.CanRestartToUpdate);
        UpdateButton.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
    }

    private void OnPlayClick(object sender, RoutedEventArgs e) => App.Bridge.Notify("app.play_fortnite");

    private void OnUpdateClick(object sender, RoutedEventArgs e) => App.Bridge.Notify("app.restart_to_update");
}
