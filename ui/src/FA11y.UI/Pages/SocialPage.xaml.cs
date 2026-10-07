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
public sealed record SocialRow(string Id, string Name, string Display, string Spoken, bool Incoming = true, bool Me = false,
    string Kind = "")
{
    public override string ToString() => Spoken;
}

/// <summary>
/// Friends, friend requests, party, party invites, messages and your own account stats. Enter invites
/// (friends) or accepts (requests and invites), F favorites, Delete declines, up and down wrap, and typing
/// jumps to a name. Lists come from the core's cached data; changing tab asks the core to refresh.
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
    private int _friendsVersion, _requestsVersion, _partyVersion, _invitesVersion, _chatsVersion, _historyVersion;
    private readonly Dictionary<string, (string Type, List<string> Members)> _chats = new();
    private string? _openChat;
    private (string Id, string Type, List<string> Members, string Title)? _pendingChat;
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
        EpicText.Text = FortniteText.Text = RankedText.Text = HordeText.Text = "Loading…";
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
            3 => InvitesList,
            4 => ChatsList,
            5 => EpicText,
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
        3 => LoadInvites(refresh, announce),
        4 => LoadChats(announce),
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

    private async Task LoadInvites(bool refresh, bool announce)
    {
        var version = ++_invitesVersion;
        try
        {
            var result = await App.Bridge.RequestAsync("social.invites", new { refresh });
            if (version != _invitesVersion)
                return;
            var rows = result.GetProperty("invites").EnumerateArray()
                .Select(i =>
                {
                    var label = $"Party invite from {i.Str("name")}";
                    return new SocialRow(i.Str("id"), i.Str("name"), label, label, Kind: "invite");
                })
                .Concat(result.GetProperty("join_requests").EnumerateArray().Select(r =>
                {
                    var label = $"{r.Str("name")} wants to join your party";
                    return new SocialRow(r.Str("id"), r.Str("name"), label, label, Kind: "join_request");
                })).ToList();
            SetRows(InvitesList, rows);
            if (announce)
                Say(result.Str("summary"));
        }
        catch (Exception e)
        {
            Log.Error("social.invites failed", e);
        }
    }

    private async Task LoadChats(bool announce, string? select = null)
    {
        var version = ++_chatsVersion;
        try
        {
            var result = await App.Bridge.RequestAsync("social.chats", null, TimeSpan.FromSeconds(30));
            if (version != _chatsVersion)
                return;
            if (result.Str("message") is { Length: > 0 } problem)
            {
                Say(problem);
                return;
            }
            _chats.Clear();
            var rows = new List<SocialRow>();
            foreach (var chat in result.GetProperty("chats").EnumerateArray())
            {
                var id = chat.Str("id");
                _chats[id] = (chat.Str("type"),
                    chat.GetProperty("members").EnumerateArray().Select(m => m.GetString() ?? "").ToList());
                var title = chat.Str("title");
                var unread = chat.TryGetProperty("unread", out var u) ? u.GetInt32() : 0;
                var label = unread > 0 ? $"{title}, {unread} unread" : title;
                rows.Add(new SocialRow(id, title, label, label));
            }
            // A DM that has no messages yet isn't in Epic's list: show it anyway when it was just opened.
            if (select != null && rows.All(r => r.Id != select) && _pendingChat is { } pending && pending.Id == select)
            {
                _chats[select] = (pending.Type, pending.Members);
                rows.Insert(0, new SocialRow(select, pending.Title, pending.Title, pending.Title));
            }
            SetRows(ChatsList, rows);
            if (select != null)
            {
                var index = rows.FindIndex(r => r.Id == select);
                if (index >= 0)
                    ChatsList.SelectedIndex = index;
            }
            if (announce)
                Say(rows.Count == 0 ? "No conversations" : $"{rows.Count} conversations");
            if (ChatsList.SelectedItem is SocialRow row && row.Id != _openChat)
                await LoadHistory(row.Id, announce: false);
        }
        catch (Exception e)
        {
            Log.Error("social.chats failed", e);
        }
    }

    private async Task LoadHistory(string id, bool announce)
    {
        var version = ++_historyVersion;
        _openChat = id;
        try
        {
            var type = _chats.TryGetValue(id, out var info) ? info.Type : "dm";
            var result = await App.Bridge.RequestAsync("social.chat_messages", new { id, type }, TimeSpan.FromSeconds(30));
            if (version != _historyVersion)
                return;
            if (result.Str("message") is { Length: > 0 } problem)
            {
                HistoryText.Text = problem;
                _openChat = null;
                if (problem.StartsWith("Epic is temporarily limiting", StringComparison.Ordinal) ||
                    problem.StartsWith("Reconnecting to Epic", StringComparison.Ordinal))
                {
                    await Task.Delay(TimeSpan.FromSeconds(30));
                    if (version == _historyVersion && _available && Tabs.SelectedIndex == 4 &&
                        ChatsList.SelectedItem is SocialRow selected && selected.Id == id)
                        await LoadHistory(id, announce: false);
                }
                return;
            }
            var lines = result.GetProperty("messages").EnumerateArray()
                .Select(m => $"{m.Str("sender")}, {m.Str("time")}: {m.Str("text")}").ToList();
            HistoryText.Text = lines.Count == 0 ? "No messages yet." : string.Join(Environment.NewLine, lines);
            // Put the caret on the newest message, so reading starts there.
            var last = HistoryText.Text.LastIndexOf(Environment.NewLine, StringComparison.Ordinal);
            HistoryText.CaretIndex = last < 0 ? 0 : last + Environment.NewLine.Length;
            HistoryText.ScrollToEnd();
            if (announce && lines.Count > 0)
                Say(lines[^1]);
        }
        catch (Exception e)
        {
            if (version == _historyVersion)
                _openChat = null;
            Log.Error("social.chat_messages failed", e);
        }
    }

    /// <summary>The core got or sent a message in a conversation: show it if that conversation is open.</summary>
    public void OnChatChanged(string id)
    {
        if (!_available || Tabs.SelectedIndex != 4)
            return;
        if (id == _openChat)
            _ = LoadHistory(id, announce: false);
        else
            _ = LoadChats(announce: false);
    }

    private int _hordeRequest;

    private async Task LoadHorde()
    {
        var request = ++_hordeRequest;
        try
        {
            var result = await App.Bridge.RequestAsync("social.horde_rank", null, TimeSpan.FromSeconds(60));
            if (request == _hordeRequest)
            {
                HordeText.Text = result.Str("text");
                HordeText.CaretIndex = 0;
            }
        }
        catch (Exception e)
        {
            Log.Error("social.horde_rank failed", e);
            if (request == _hordeRequest)
                HordeText.Text = "Could not load your Horde rank. Refresh to retry.";
        }
    }

    private async Task LoadAccount()
    {
        var horde = LoadHorde();
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
        await horde;
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

    private void OnInvitesKeyDown(object sender, KeyEventArgs e)
    {
        if (Keyboard.Modifiers != ModifierKeys.None)
            return;
        if (Wrap(InvitesList, e))
            return;
        if (e.Key == WpfKey.Enter)
        {
            e.Handled = true;
            OnAcceptInvite(sender, e);
        }
        else if (e.Key == WpfKey.Delete)
        {
            e.Handled = true;
            OnDeclineInvite(sender, e);
        }
    }

    private void OnChatsKeyDown(object sender, KeyEventArgs e)
    {
        if (Keyboard.Modifiers != ModifierKeys.None)
            return;
        if (Wrap(ChatsList, e))
            return;
        if (e.Key == WpfKey.Enter)
        {
            e.Handled = true;
            MessageBox.Focus();
        }
    }

    private void OnMessageKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == WpfKey.Enter && Keyboard.Modifiers == ModifierKeys.None)
        {
            e.Handled = true;
            OnSend(sender, e);
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

    private async void OnMessageFriend(object sender, RoutedEventArgs e)
    {
        if (Selected(FriendsList, "No friend selected") is not { } friend)
            return;
        var result = await Act("social.open_dm", new { id = friend.Id }, TimeSpan.FromSeconds(30));
        if (result is not { } dm)
            return;
        if (dm.Str("message") is { Length: > 0 } problem)
        {
            Say(problem);
            return;
        }
        var id = dm.Str("id");
        _pendingChat = (id, "dm", dm.GetProperty("members").EnumerateArray().Select(m => m.GetString() ?? "").ToList(),
            dm.Str("title"));
        _chatsVersion++;  // the tab change starts a load without the selection; this one wins
        Tabs.SelectedIndex = 4;
        await LoadChats(announce: false, select: id);
        Say($"Message {friend.Name}");
        MessageBox.Focus();
    }

    // Party invites --------------------------------------------------------------------------------

    private async void OnAcceptInvite(object sender, RoutedEventArgs e) => await AnswerInvite(accept: true);

    private async void OnDeclineInvite(object sender, RoutedEventArgs e) => await AnswerInvite(accept: false);

    private async Task AnswerInvite(bool accept)
    {
        if (Selected(InvitesList, "No invite selected") is not { } row)
            return;
        var result = await Act(accept ? "social.accept_invite" : "social.decline_invite",
            new { id = row.Id, kind = row.Kind }, TimeSpan.FromSeconds(60));
        if (result is not { } done)
            return;
        if (done.Str("message") is { Length: > 0 } message)
            Say(message);
        await LoadInvites(refresh: false, announce: false);
    }

    // Messages --------------------------------------------------------------------------------------

    private void OnChatSelected(object sender, SelectionChangedEventArgs e)
    {
        if (e.OriginalSource == ChatsList && ChatsList.SelectedItem is SocialRow row && row.Id != _openChat)
            _ = LoadHistory(row.Id, announce: false);
    }

    private async void OnSend(object sender, RoutedEventArgs e)
    {
        var text = MessageBox.Text.Trim();
        if (text.Length == 0)
        {
            Say("Type a message first");
            return;
        }
        if (ChatsList.SelectedItem is not SocialRow chat || !_chats.TryGetValue(chat.Id, out var info))
        {
            Say("Choose a conversation first");
            return;
        }
        var result = await Act("social.send_message",
            new { id = chat.Id, type = info.Type, members = info.Members, text }, TimeSpan.FromSeconds(30));
        if (result is not { } done)
        {
            Say("Couldn't send the message.");
            return;
        }
        if (done.Str("message") is { Length: > 0 } problem)
        {
            Say(problem);
            return;
        }
        MessageBox.Text = "";
        Say("Sent");
        await LoadHistory(chat.Id, announce: false);
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
