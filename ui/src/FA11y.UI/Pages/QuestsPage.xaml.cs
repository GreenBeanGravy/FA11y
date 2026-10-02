using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using FA11y.UI.Controls;
using FA11y.UI.Core;

namespace FA11y.UI.Pages;

/// <summary>
/// Quests and passes: the account's quests, and a tab for each season pass with its rewards. The
/// quests of a pass reward open in place of the tabs; Escape or Close goes back. Signed out, the
/// page says so. Everything loads before the page is first opened, once sign in has settled.
/// </summary>
public partial class QuestsPage : PageBase, IPrefetchPage
{
    private const string LoadingText = "Loading…";
    private const string SignedOutText = "Sign in on the Epic account page to see your quests.";

    private readonly QuestPanel _quests = new();
    private readonly PassSession _session;
    private readonly List<PassPanel> _passPanels = new();
    private bool _loading;
    private bool _ready;
    private bool _shown;
    private bool _passesBuilt;
    private QuestPanel? _scoped;
    private FrameworkElement? _scopeOpener;

    public QuestsPage()
    {
        InitializeComponent();
        _session = new PassSession(() => (UIElement?)Host ?? this);
        QuestsTab.Content = _quests;
        _quests.SignedOut += OnSignedOut;
        Message.Text = LoadingText;
    }

    public override string Key => "quests";
    public override string Title => "Quests and passes";

    public override void OnShown()
    {
        _shown = true;
        if (!_ready && !_loading)
            Load();
        else if (_ready)
            Activate();
    }

    public override void OnHidden()
    {
        _shown = false;
        _quests.Deactivate();
        _scoped?.Deactivate();
    }

    public override FrameworkElement? FirstFocus()
    {
        if (!_ready)
            return Message;
        if (_scoped != null)
            return _scoped.FirstFocus;
        return Tabs.SelectedItem switch
        {
            var t when t == QuestsTab => _quests.FirstFocus,
            TabItem { Content: PassPanel pass } => pass.FirstFocus,
            _ => null,
        };
    }

    public override bool HandleEscape()
    {
        if (_scoped == null)
            return false;
        CloseScope();
        return true;
    }

    /// <summary>The core says quests changed (match packets, or a refresh): redraw the list.</summary>
    public override void Refresh()
    {
        if (!_ready)
            return;
        _quests.Render();
        _scoped?.Render();
    }

    public void Prefetch()
    {
        if (!_ready && !_loading)
            Load();
    }

    /// <summary>Signed in or out: show Loading and load again, keeping the keyboard on the page.</summary>
    public void ResetData()
    {
        var hadFocus = IsKeyboardFocusWithin;
        CloseScope();
        _quests.Deactivate();
        _ready = false;
        Tabs.Visibility = Visibility.Collapsed;
        Message.Text = LoadingText;
        Message.Visibility = Visibility.Visible;
        if (hadFocus)
            Message.Focus();
        if (!_loading)
            Load();
    }

    private async void Load()
    {
        _loading = true;
        try
        {
            var state = await App.Bridge.RequestAsync("quests.state");
            if (!state.Bool("signed_in"))
            {
                ShowMessage(SignedOutText);
                return;
            }
            if (!_passesBuilt)
                await BuildPassTabs();
            var hadFocus = Message.IsKeyboardFocused || (IsKeyboardFocusWithin && !_ready);
            _ready = true;
            Message.Visibility = Visibility.Collapsed;
            Tabs.Visibility = Visibility.Visible;
            if (_shown)
                Activate();
            if (hadFocus)
                FirstFocus()?.Focus();
        }
        catch (Exception e)
        {
            Log.Error("Loading quests failed", e);
            ShowMessage("Couldn't load your quests. Open this page again to retry.");
        }
        finally
        {
            _loading = false;
        }
    }

    private async Task BuildPassTabs()
    {
        var info = await App.Bridge.RequestAsync("passes.definitions");
        if (info.TryGetProperty("passes", out var array) && array.ValueKind == JsonValueKind.Array)
        {
            foreach (var definition in array.EnumerateArray())
            {
                var panel = new PassPanel(_session, definition);
                panel.QuestsRequested += ShowScope;
                _passPanels.Add(panel);
                var name = definition.Str("name");
                var tab = new TabItem { Header = name, Content = panel };
                System.Windows.Automation.AutomationProperties.SetName(tab, name);
                Tabs.Items.Add(tab);
            }
        }
        _passesBuilt = true;
    }

    private void ShowMessage(string text)
    {
        _ready = false;
        Tabs.Visibility = Visibility.Collapsed;
        Message.Text = text;
        Message.Visibility = Visibility.Visible;
    }

    private void OnSignedOut()
    {
        // The account went away while the page was open; same message as when it opens signed out.
        var hadFocus = IsKeyboardFocusWithin;
        CloseScope();
        ShowMessage(SignedOutText);
        if (hadFocus)
            Message.Focus();
    }

    private void Activate()
    {
        _quests.Activate();
        _scoped?.Activate();
        EnsurePassesLoaded();
    }

    private void OnTabChanged(object sender, SelectionChangedEventArgs e)
    {
        if (e.OriginalSource != Tabs)
            return; // a combo box or list inside a tab
        EnsurePassesLoaded();
    }

    /// <summary>The first time a pass tab is open, load the account's pass state.</summary>
    private async void EnsurePassesLoaded()
    {
        if (!_ready || _session.Loaded || Tabs.SelectedItem is not TabItem { Content: PassPanel })
            return;
        await _session.RefreshAsync();
    }

    // Quests of a pass reward ------------------------------------------------------------

    private void ShowScope(string scopeId, string heading, string label, FrameworkElement opener)
    {
        if (scopeId.Length == 0)
            return;
        CloseScope();
        _scopeOpener = opener;
        _scoped = new QuestPanel(scopeId, heading);
        _scoped.CloseRequested += CloseScope;
        _scoped.SignedOut += OnSignedOut;
        SubView.Content = _scoped;
        Tabs.Visibility = Visibility.Collapsed;
        SubView.Visibility = Visibility.Visible;
        _scoped.Activate();
        UpdateLayout();
        _scoped.FirstFocus.Focus();
    }

    private void CloseScope()
    {
        if (_scoped == null)
            return;
        _scoped.Deactivate();
        _scoped = null;
        SubView.Content = null;
        SubView.Visibility = Visibility.Collapsed;
        if (_ready)
            Tabs.Visibility = Visibility.Visible;
        var opener = _scopeOpener;
        _scopeOpener = null;
        UpdateLayout();
        if (opener is { IsEnabled: true, IsVisible: true })
            opener.Focus();
    }
}
