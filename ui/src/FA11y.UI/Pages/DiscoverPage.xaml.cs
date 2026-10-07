using System.Windows;
using System.Windows.Input;
using FA11y.UI.Controls;
using FA11y.UI.Core;

namespace FA11y.UI.Pages;

/// <summary>
/// Discover: Epic's gamemodes, popular islands, search, a creator's maps, and lookup by code. Pick
/// an island and copy its code or launch it. The Epic and Browse lists load before the page is
/// first opened and again when they are five minutes old.
/// </summary>
public partial class DiscoverPage : PageBase, IPrefetchPage
{
    private static readonly TimeSpan StaleAfter = TimeSpan.FromMinutes(5);
    private DateTime? _loaded;
    private int _lookupToken;

    public DiscoverPage()
    {
        InitializeComponent();
        EpicPanel.ShowMessage("Loading Epic Games gamemodes...");
        EpicPanel.MatchOptions = MatchOptions;
        BrowsePanel.ShowMessage("Loading... (switch to this tab to load data)");
        SearchBox.KeyDown += (_, e) => EnterIn(e, OnSearch);
        CreatorBox.KeyDown += (_, e) => EnterIn(e, OnLoadCreator);
        CodeBox.KeyDown += (_, e) => EnterIn(e, OnLookup);
    }

    public override string Key => "discover";
    public override string Title => "Discover";

    public override void OnShown()
    {
        if (_loaded == null || DateTime.UtcNow - _loaded > StaleAfter)
            LoadAll();
    }

    public void Prefetch()
    {
        if (_loaded == null)
            LoadAll();
    }

    // Discover works signed out, so signing in or out changes nothing here.
    public void ResetData() { }

    public override FrameworkElement? FirstFocus() => Tabs.SelectedItem switch
    {
        var t when t == SearchTab => SearchBox,
        var t when t == CreatorTab => CreatorBox,
        var t when t == CodeTab => CodeBox,
        var t when t == BrowseTab => BrowsePanel.Rows,
        _ => EpicPanel.Rows,
    };

    private static void EnterIn(KeyEventArgs e, Action action)
    {
        if (e.Key != System.Windows.Input.Key.Enter || Keyboard.Modifiers != ModifierKeys.None)
            return;
        e.Handled = true;
        action();
    }

    private UIElement Anchor => (UIElement?)Host ?? this;

    private void LoadAll()
    {
        _loaded = DateTime.UtcNow;
        LoadEpic();
        LoadBrowse();
    }

    private void LoadEpic() => Load(EpicPanel, "discover.epic", null, "Loading Epic Games gamemodes...",
        "Couldn't load Epic gamemodes. Try refreshing.");

    private void LoadBrowse() => Load(BrowsePanel, "discover.browse", null, "Loading islands from fortnite.gg...",
        "Couldn't load islands. Try refreshing.");

    private async void Load(IslandPanel panel, string method, object? parameters, string loading, string failed)
    {
        var token = panel.BeginLoad(loading);
        try
        {
            panel.Apply(token, await App.Bridge.RequestAsync(method, parameters, TimeSpan.FromSeconds(60)));
        }
        catch (Exception e)
        {
            Log.Error($"{method} failed", e);
            panel.Fail(token, failed);
        }
    }

    private void OnRefreshEpic(object sender, RoutedEventArgs e) => LoadEpic();

    private void OnRefreshBrowse(object sender, RoutedEventArgs e)
    {
        _loaded = DateTime.UtcNow;
        LoadBrowse();
    }

    private void OnSearchClick(object sender, RoutedEventArgs e) => OnSearch();

    private void OnSearch()
    {
        var query = SearchBox.Text.Trim();
        if (query.Length == 0)
        {
            Announcer.Announce(Anchor, "Please enter a search term");
            return;
        }
        Announcer.Announce(Anchor, $"Searching for {query}");
        Load(SearchPanel, "discover.search", new { query }, $"Searching fortnite.gg for '{query}'...",
            $"Couldn't search for '{query}'. Try again.");
    }

    private void OnLoadCreatorClick(object sender, RoutedEventArgs e) => OnLoadCreator();

    private void OnLoadCreator()
    {
        var name = CreatorBox.Text.Trim();
        if (name.Length == 0)
        {
            Announcer.Announce(Anchor, "Please enter a creator name");
            return;
        }
        LoadCreator(name);
    }

    private void OnLoadEpicCreatorClick(object sender, RoutedEventArgs e)
    {
        CreatorBox.Text = "epic";
        LoadCreator("epic");
    }

    private void LoadCreator(string name)
    {
        Announcer.Announce(Anchor, $"Loading maps from {name}");
        Load(CreatorPanel, "discover.creator", new { name }, $"Loading maps from {name}...",
            $"Couldn't load maps from {name}. Try again.");
    }

    private void OnLookupClick(object sender, RoutedEventArgs e) => OnLookup();

    private static readonly string[] TeamSizes = { "solo", "duo", "trio", "squad" };

    /// <summary>The Epic tab's match options; the core uses the ones the launched gamemode offers.</summary>
    private object MatchOptions() => new
    {
        team = TeamSizes[Math.Clamp(TeamGroup.SelectedIndex, 0, TeamSizes.Length - 1)],
        zero_build = BuildGroup.SelectedIndex == 1,
        ranked = RankedBox.IsChecked == true,
    };

    private async void OnLookup()
    {
        var code = CodeBox.Text.Trim();
        if (code.Length == 0)
        {
            Announcer.Announce(Anchor, "Please enter an island code");
            return;
        }
        var token = ++_lookupToken;
        IslandInfo.Text = "Looking up island...";
        Announcer.Announce(Anchor, $"Looking up code {code}");
        try
        {
            var result = await App.Bridge.RequestAsync("discover.lookup", new { code }, TimeSpan.FromSeconds(30));
            if (token != _lookupToken)
                return;
            IslandInfo.Text = result.Str("text");
            IslandInfo.CaretIndex = 0;
            Announcer.Announce(Anchor, result.Str("announce"));
        }
        catch (Exception e)
        {
            Log.Error("discover.lookup failed", e);
            if (token == _lookupToken)
            {
                IslandInfo.Text = $"Couldn't look up {code}. Try again.";
                Announcer.Announce(Anchor, "Couldn't look up that code");
            }
        }
    }
}
