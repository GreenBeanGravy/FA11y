using System.Text.Json;
using System.Windows;
using System.Windows.Input;
using FA11y.UI.Controls;
using FA11y.UI.Core;
using FA11y.UI.Shell;

namespace FA11y.UI.Pages;

/// <summary>Epic account: who is signed in, and Sign in / Sign out.</summary>
public partial class AccountPage : PageBase
{
    private bool _busy;
    private bool _loaded;

    public AccountPage()
    {
        InitializeComponent();
        AccountText.Text = "Loading…";
        SignInButton.Visibility = Visibility.Collapsed;
        SignOutButton.Visibility = Visibility.Collapsed;
    }

    public override string Key => "account";
    public override string Title => "Epic account";

    public override void OnShown() => Refresh();

    // Who is signed in first, then the buttons.
    public override FrameworkElement? FirstFocus() => AccountText;

    public override async void Refresh()
    {
        try
        {
            Apply(await App.Bridge.RequestAsync("account.state"));
        }
        catch (Exception e)
        {
            Log.Error("account.state failed", e);
            if (!_loaded)
                AccountText.Text = "Couldn't check your Epic account.";
        }
    }

    private void Apply(JsonElement info)
    {
        _loaded = true;
        var signedIn = info.Bool("signed_in");
        var valid = info.Bool("valid");
        AccountText.SetLines(
            new TextLine(info.Str("name"), 16, System.Windows.FontWeights.SemiBold),
            new TextLine(info.Str("detail"), 0, null, (System.Windows.Media.Brush)FindResource("TextSecondary"), 4));
        SignInButton.Content = signedIn ? "_Sign in again" : "_Sign in";
        SignInButton.Visibility = valid ? Visibility.Collapsed : Visibility.Visible;
        SignOutButton.Visibility = signedIn ? Visibility.Visible : Visibility.Collapsed;
    }

    private async void OnSignInClick(object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;
        _busy = true;
        try
        {
            // The sign in dialog is the core's (still wx); this returns when it closes.
            var result = await App.Bridge.RequestAsync("account.sign_in", null, Timeout.InfiniteTimeSpan);
            Apply(result);
            BringBackIfOurs();
            (result.Bool("authenticated") ? SignOutButton : SignInButton).Focus();
        }
        catch (Exception ex)
        {
            Log.Error("account.sign_in failed", ex);
            SignInButton.Focus();
        }
        finally
        {
            _busy = false;
        }
    }

    private async void OnSignOutClick(object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;
        if (!Dialogs.Confirm(Host,
                "Sign out",
                "Sign out of your Epic account? Locker, friends, quests and Fortnite downloads will stop working until you sign in again."))
        {
            SignOutButton.Focus();
            return;
        }
        _busy = true;
        try
        {
            Apply(await App.Bridge.RequestAsync("account.sign_out"));
            Announcer.Announce(Host ?? (UIElement)this, "Signed out.");
        }
        catch (Exception ex)
        {
            Log.Error("account.sign_out failed", ex);
        }
        finally
        {
            _busy = false;
        }
        SignInButton.Focus();
    }

    /// <summary>After a dialog of the core's closes, take the window back unless the user went elsewhere.</summary>
    private void BringBackIfOurs()
    {
        if (Host is { } host && WindowTools.ForegroundIsFa11y(App.CoreProcessId))
            WindowTools.BringToFront(host);
    }
}
