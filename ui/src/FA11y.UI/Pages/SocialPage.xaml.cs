using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using WpfKey = System.Windows.Input.Key;
using System.Windows.Threading;
using FA11y.UI.Core;
using FA11y.UI.Shell;

namespace FA11y.UI.Pages;

/// <summary>One row of a Social list (friend, request or party member).</summary>
/// <param name="Id">Epic account id.</param>
/// <param name="Name">What type-ahead matches and the row says (without the favorite star).</param>
/// <param name="Display">What is drawn.</param>
/// <param name="Spoken">What a screen reader says for the row.</param>
public sealed record SocialRow(string Id, string Name, string Display, string Spoken, bool Incoming = true, bool Me = false)
{
    public override string ToString() => Spoken;
}

/// <summary>
/// Friends, friend requests, party and your own account stats. Enter invites (friends) or
/// accepts (requests), F favorites, Delete declines, up and down wrap, and typing jumps to a name. Lists come from the core's cached data; changing tab asks the core to refresh.
/// </summary>
public partial class SocialPage : PageBase
{
    private const string UnavailableText =
        "Sign in on the Epic account page to see your friends, requests and party.";

    private bool _stateKnown;
    private bool _prefetched;
    private bool _available;
    private bool _busy;
    private bool _accountLoaded;
    private int _friendsVersion, _requestsVersion, _partyVersion;
    private bool _partyHasMembers;
    private string _partySummary = "Not in a party";
    private readonly DispatcherTimer _searchTimer;

    public SocialPage()
    {
        InitializeComponent();
        Message.Text = "Loading…";
        _searchTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(300) };
        _searchTimer.Tick += async (_, _) =>
        {
            _searchTimer.Stop();
            await LoadFriends(refresh: false, announce: true);
        };
        EpicText.Text = FortniteText.Text = RankedText.Text = "Loading…";
        // Fill the lists in the background once the core has said hello, so the first visit is instant.
        AppState.Changed += PrefetchOnce;
    }

    public override string Key => "social";
    public override string Title => "Social";

    private void PrefetchOnce()
    {
        if (!AppState.HelloReceived || _stateKnown || _prefetched)
            return;
        _prefetched = true;
        Refresh();
    }

    public override void OnShown()
    {
        if (!_stateKnown)
            Refresh();
        else if (_available)
            _ = ReloadCurrent(refresh: false, announce: false);
    }

    // The list on the selected tab.
    public override FrameworkElement? FirstFocus()
    {
        if (!_available)
            return Message;
        return Tabs.SelectedIndex switch
        {
            1 => RequestsList,
            2 => PartyList,
            3 => EpicText,
            _ => FriendsList,
        };
    }

    // Loading ---------------------------------------------------------------------

    public override async void Refresh()
    {
        try
        {
            var state = await App.Bridge.RequestAsync("social.state");
            var available = state.Bool("available");
            var focusWasOnMessage = Message.IsKeyboardFocusWithin;
            _stateKnown = true;
            _available = available;
            Tabs.Visibility = available ? Visibility.Visible : Visibility.Collapsed;
            Message.Visibility = available ? Visibility.Collapsed : Visibility.Visible;
            if (!available)
            {
                Message.Text = UnavailableText;
                return;
            }
            await ReloadCurrent(refresh: false, announce: false);
            if (focusWasOnMessage)
                FirstFocus()?.Focus();
        }
        catch (Exception e)
        {
            Log.Error("social.state failed", e);
            if (!_stateKnown)
                Message.Text = "Couldn't load your friends. Open this page again to try again.";
        }
    }

    private Task ReloadCurrent(bool refresh, bool announce) => Tabs.SelectedIndex switch
    {
        0 => LoadFriends(refresh, announce),
        1 => LoadRequests(refresh, announce),
        2 => LoadParty(refresh, announce),
        // The stats cost three Epic calls: only when asked for, or when never loaded.
        _ => refresh || !_accountLoaded ? LoadAccount() : Task.CompletedTask,
    };

    private void OnTabChanged(object sender, SelectionChangedEventArgs e)
    {
        if (e.OriginalSource != Tabs || !_available)
            return;
        _ = ReloadCurrent(refresh: true, announce: true);
    }

    private bool FavoritesOnly => FavoritesRadio.IsChecked == true;
    private bool IncomingOnly => IncomingRadio.IsChecked == true;

    private async Task LoadFriends(bool refresh, bool announce)
    {
        var version = ++_friendsVersion;
        try
        {
            var result = await App.Bridge.RequestAsync("social.friends",
                new { favorites_only = FavoritesOnly, search = SearchBox.Text, refresh });
            if (version != _friendsVersion)
                return;
            var rows = result.GetProperty("friends").EnumerateArray()
                .Select(f =>
                {
                    var name = f.Str("name");
                    var favorite = f.Bool("favorite");
                    return new SocialRow(f.Str("id"), name, favorite ? "★ " + name : name,
                        favorite ? $"{name}, favorite" : name);
                }).ToList();
            SetRows(FriendsList, rows);
            if (announce)
                Say(result.Str("summary"));
        }
        catch (Exception e)
        {
            Log.Error("social.friends failed", e);
        }
    }

    private async Task LoadRequests(bool refresh, bool announce)
    {
        var version = ++_requestsVersion;
        try
        {
            var result = await App.Bridge.RequestAsync("social.requests", new { incoming = IncomingOnly, refresh });
            if (version != _requestsVersion)
                return;
            var rows = result.GetProperty("requests").EnumerateArray()
                .Select(r =>
                {
                    var incoming = r.Bool("incoming");
                    var label = $"Request {(incoming ? "from" : "to")} {r.Str("name")}";
                    return new SocialRow(r.Str("id"), label, label, label, incoming);
                }).ToList();
            SetRows(RequestsList, rows);
            if (announce)
                Say(result.Str("summary"));
        }
        catch (Exception e)
        {
            Log.Error("social.requests failed", e);
        }
    }

    private async Task LoadParty(bool refresh, bool announce)
    {
        var version = ++_partyVersion;
        try
        {
            var result = await App.Bridge.RequestAsync("social.party", new { refresh });
            if (version != _partyVersion)
                return;
            var rows = result.GetProperty("members").EnumerateArray()
                .Select(m =>
                {
                    var label = m.Bool("leader") ? $"{m.Str("name")} (Leader)" : m.Str("name");
                    return new SocialRow(m.Str("id"), label, label, label, Me: m.Bool("me"));
                }).ToList();
            SetRows(PartyList, rows);
            _partyHasMembers = rows.Count > 0;
            _partySummary = result.Str("summary");
            // Only the leader can promote or kick.
            var leader = result.Bool("am_leader");
            PromoteButton.IsEnabled = leader;
            KickButton.IsEnabled = leader;
            if (announce)
                Say(_partySummary);
        }
        catch (Exception e)
        {
            Log.Error("social.party failed", e);
        }
    }

    private async Task LoadAccount()
    {
        try
        {
            var result = await App.Bridge.RequestAsync("social.account_info", null, TimeSpan.FromSeconds(60));
            EpicText.Text = result.Str("epic");
            FortniteText.Text = result.Str("fortnite");
            RankedText.Text = result.Str("ranked");
            _accountLoaded = true;
        }
        catch (Exception e)
        {
            Log.Error("social.account_info failed", e);
            if (!_accountLoaded)
                EpicText.Text = FortniteText.Text = RankedText.Text = "Couldn't load your account information.";
        }
    }

    /// <summary>Put rows in a list, keeping the selection on the same person (or the first row).</summary>
    private static void SetRows(ListBox list, List<SocialRow> rows)
    {
        var keep = (list.SelectedItem as SocialRow)?.Id;
        var hadFocus = list.IsKeyboardFocusWithin;
        list.ItemsSource = rows;
        var index = keep == null ? -1 : rows.FindIndex(r => r.Id == keep);
        if (index < 0 && rows.Count > 0)
            index = 0;
        list.SelectedIndex = index;
        if (hadFocus && index >= 0)
            FocusRow(list, index);
    }

    private static void FocusRow(ListBox list, int index)
    {
        list.SelectedIndex = index;
        list.ScrollIntoView(list.SelectedItem);
        list.UpdateLayout();
        if (list.ItemContainerGenerator.ContainerFromIndex(index) is ListBoxItem item)
            item.Focus();
    }

    /// <summary>Test builds only: switch tab without keys.</summary>
    public void SelectTabForTest(string header)
    {
        foreach (TabItem tab in Tabs.Items)
            if ((tab.Header as string) == header)
                Tabs.SelectedItem = tab;
    }

    private void Say(string text) => Announcer.Announce(Host ?? (UIElement)this, text);

    // Filters and search --------------------------------------------------------------

    private void OnFriendFilterChanged(object sender, RoutedEventArgs e)
    {
        if (_available && IsLoaded)
            _ = LoadFriends(refresh: false, announce: true);
    }

    private void OnRequestFilterChanged(object sender, RoutedEventArgs e)
    {
        if (_available && IsLoaded)
            _ = LoadRequests(refresh: false, announce: true);
    }

    private void OnSearchChanged(object sender, TextChangedEventArgs e)
    {
        if (!_available || !IsLoaded)
            return;
        _searchTimer.Stop();
        _searchTimer.Start();
    }

    private void OnClearSearch(object sender, RoutedEventArgs e)
    {
        SearchBox.Text = "";
        SearchBox.Focus();
    }

    // Keys ---------------------------------------------------------------------------------

    private bool Wrap(ListBox list, KeyEventArgs e)
    {
        if (list.Items.Count == 0)
            return false;
        if (e.Key == WpfKey.Up && list.SelectedIndex <= 0)
            FocusRow(list, list.Items.Count - 1);
        else if (e.Key == WpfKey.Down && list.SelectedIndex >= list.Items.Count - 1)
            FocusRow(list, 0);
        else
            return false;
        e.Handled = true;
        return true;
    }

    private void OnFriendsKeyDown(object sender, KeyEventArgs e)
    {
        if (Keyboard.Modifiers != ModifierKeys.None)
            return;
        if (Wrap(FriendsList, e))
            return;
        if (e.Key == WpfKey.Enter)
        {
            e.Handled = true;
            OnInvite(sender, e);
        }
        else if (e.Key == WpfKey.F)
        {
            e.Handled = true;
            _ = ToggleFavorite();
        }
    }

    private void OnRequestsKeyDown(object sender, KeyEventArgs e)
    {
        if (Keyboard.Modifiers != ModifierKeys.None)
            return;
        if (Wrap(RequestsList, e))
            return;
        if (e.Key == WpfKey.Enter)
        {
            e.Handled = true;
            OnAccept(sender, e);
        }
        else if (e.Key == WpfKey.Delete)
        {
            e.Handled = true;
            OnDecline(sender, e);
        }
    }

    private void OnFriendsDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (e.OriginalSource is DependencyObject source && ItemsControl.ContainerFromElement(FriendsList, source) != null)
            OnInvite(sender, e);
    }

    // Friends ---------------------------------------------------------------------------------

    private SocialRow? Selected(ListBox list, string none)
    {
        if (list.SelectedItem is SocialRow row)
            return row;
        Say(none);
        return null;
    }

    private async Task ToggleFavorite()
    {
        if (Selected(FriendsList, "No friend selected") is not { } friend || _busy)
            return;
        _busy = true;
        try
        {
            await App.Bridge.RequestAsync("social.toggle_favorite", new { id = friend.Id });
            await LoadFriends(refresh: false, announce: false);
        }
        catch (Exception e)
        {
            Log.Error("social.toggle_favorite failed", e);
        }
        finally
        {
            _busy = false;
        }
    }

    private async void OnInvite(object sender, RoutedEventArgs e)
    {
        if (Selected(FriendsList, "No friend selected") is { } friend)
            await Act("social.invite", new { id = friend.Id });
    }

    private async void OnRequestJoin(object sender, RoutedEventArgs e)
    {
        if (Selected(FriendsList, "No friend selected") is { } friend)
            await Act("social.request_join", new { id = friend.Id });
    }

    private async void OnRemoveFriend(object sender, RoutedEventArgs e)
    {
        if (Selected(FriendsList, "No friend selected") is not { } friend)
            return;
        if (!Dialogs.Confirm(Host, "Confirm Remove Friend",
                $"Remove {friend.Name} from your friends list?"))
        {
            FocusRow(FriendsList, FriendsList.SelectedIndex);
            return;
        }
        if (await Act("social.remove_friend", new { id = friend.Id }) != null)
            await LoadFriends(refresh: false, announce: true);
    }

    private async void OnAddFriend(object sender, RoutedEventArgs e)
    {
        var username = Prompts.Ask(Host, "Add Friend", "Enter Epic Games username to search:")?.Trim();
        if (username == null)
        {
            Say("Cancelled");
            return;
        }
        if (username.Length == 0)
        {
            Say("No username entered");
            return;
        }
        Say($"Searching for {username}");
        var result = await Act("social.find_users", new { username }, TimeSpan.FromSeconds(60));
        if (result is not { } found)
            return;
        switch (found.Str("status"))
        {
            case "none":
                Say($"No users found matching {username}");
                break;
            case "sent":
                await LoadRequests(refresh: false, announce: false);
                break;
            case "choose":
                var users = found.GetProperty("users").EnumerateArray().ToList();
                var index = Prompts.Choose(Host, "Select User", "Multiple users found. Select one:",
                    users.Select(u => u.Str("label")).ToList());
                if (index < 0)
                {
                    Say("Cancelled");
                    return;
                }
                var chosen = users[index];
                await Act("social.send_request",
                    new { account_id = chosen.Str("account_id"), display_name = chosen.Str("display_name") },
                    TimeSpan.FromSeconds(60));
                await LoadRequests(refresh: false, announce: false);
                break;
        }
    }

    // Requests --------------------------------------------------------------------------------------

    private async void OnAccept(object sender, RoutedEventArgs e)
    {
        if (Selected(RequestsList, "No request selected") is not { } request)
            return;
        var result = await Act("social.accept_request", new { id = request.Id, incoming = request.Incoming });
        if (result is not { } done)
            return;
        var message = done.Str("message");
        if (message.Length > 0)
        {
            Say(message);
            return;
        }
        await LoadRequests(refresh: false, announce: true);
    }

    private async void OnDecline(object sender, RoutedEventArgs e)
    {
        if (Selected(RequestsList, "No request selected") is not { } request)
            return;
        if (await Act("social.decline_request", new { id = request.Id, incoming = request.Incoming }) != null)
            await LoadRequests(refresh: false, announce: true);
    }

    // Party ---------------------------------------------------------------------------------------------

    private async void OnPromote(object sender, RoutedEventArgs e)
    {
        if (Selected(PartyList, "No member selected") is not { } member)
            return;
        var result = await Act("social.promote", new { id = member.Id });
        if (result is not { } done)
            return;
        var message = done.Str("message");
        if (message.Length > 0)
        {
            Say(message);
            return;
        }
        await LoadParty(refresh: false, announce: true);
    }

    private async void OnKick(object sender, RoutedEventArgs e)
    {
        if (Selected(PartyList, "No member selected") is not { } member)
            return;
        // The core checks first (you can't kick yourself), then we confirm, then it kicks.
        if (member.Me)
        {
            if (await Act("social.kick", new { id = member.Id }) is { } refused)
                Say(refused.Str("message"));
            return;
        }
        if (!Dialogs.Confirm(Host, "Confirm Kick Member", $"Kick {member.Name} from the party?"))
        {
            FocusRow(PartyList, PartyList.SelectedIndex);
            return;
        }
        var result = await Act("social.kick", new { id = member.Id });
        if (result is not { } done)
            return;
        var message = done.Str("message");
        if (message.Length > 0)
        {
            Say(message);
            return;
        }
        await LoadParty(refresh: false, announce: true);
    }

    private async void OnLeave(object sender, RoutedEventArgs e)
    {
        if (!_partyHasMembers)
        {
            Say(_partySummary);
            return;
        }
        if (!Dialogs.Confirm(Host, "Confirm Leave Party", "Leave the party?"))
        {
            LeaveButton.Focus();
            return;
        }
        if (await Act("social.leave_party", new { }) != null)
            await LoadParty(refresh: false, announce: true);
    }

    // Me ----------------------------------------------------------------------------------------------------

    private async void OnRefreshAccount(object sender, RoutedEventArgs e)
    {
        Say("Refreshing account information");
        await LoadAccount();
        Say("Account information refreshed");
    }

    // Requests that change something ------------------------------------------------------------------

    /// <summary>Run an action in the core. Returns the answer, or null when it failed. One at a time.</summary>
    private async Task<JsonElement?> Act(string method, object parameters, TimeSpan? timeout = null)
    {
        if (_busy)
            return null;
        _busy = true;
        try
        {
            return await App.Bridge.RequestAsync(method, parameters, timeout ?? TimeSpan.FromSeconds(90));
        }
        catch (Exception e)
        {
            Log.Error($"{method} failed", e);
            return null;
        }
        finally
        {
            _busy = false;
        }
    }
}
