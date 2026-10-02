using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using FA11y.UI.Core;
using FA11y.UI.Shell;

namespace FA11y.UI.Controls;

/// <summary>
/// One pass (Battle Royale, Rocket Racing and so on): ownership and level, pages of rewards, the
/// selected reward's details, and the claim and unlock buttons. The core holds the account state
/// and builds every text and button state (lib/utilities/passes_view.py), as for the wx view.
/// Page Up and Page Down change the page; nothing is claimed or bought without a confirmation.
/// </summary>
public partial class PassPanel : UserControl
{
    private readonly PassSession _session;
    private readonly string _key;
    private int _page;
    private int _reward;
    private int _token;
    private bool _suppress;
    private string? _detailsKey;

    public PassPanel(PassSession session, JsonElement definition)
    {
        InitializeComponent();
        _session = session;
        _key = definition.Str("key");
        var pages = new List<string>();
        if (definition.TryGetProperty("pages", out var array) && array.ValueKind == JsonValueKind.Array)
            foreach (var item in array.EnumerateArray())
                pages.Add(item.GetString() ?? "");
        _suppress = true;
        PageBox.ItemsSource = pages;
        PageBox.SelectedIndex = pages.Count > 0 ? 0 : -1;
        _suppress = false;
        StatusText.Text = "Account status unavailable. Refresh to check this pass.";
        MessageText.Text = session.Message;
        session.Changed += OnSessionChanged;
        IsVisibleChanged += (_, _) =>
        {
            if (IsVisible)
                Render();
        };
        PreviewKeyDown += OnPreviewKeyDown;
    }

    /// <summary>A quest view limited to these quests was asked for: scope id, heading, label, and the control to return focus to.</summary>
    public event Action<string, string, string, FrameworkElement>? QuestsRequested;

    public FrameworkElement FirstFocus => StatusText;

    private UIElement Anchor => (UIElement?)Window.GetWindow(this) ?? this;

    private void OnSessionChanged()
    {
        MessageText.Text = _session.Message;
        if (IsVisible)
            Render();
    }

    /// <summary>Ask the core for the page's texts and button states for the current page and reward.</summary>
    public async void Render()
    {
        var token = ++_token;
        try
        {
            var view = await App.Bridge.RequestAsync("passes.view", new { pass = _key, page = _page, reward = _reward });
            if (token != _token)
                return;
            Apply(view);
        }
        catch (Exception e)
        {
            Log.Error("passes.view failed", e);
        }
    }

    private void Apply(JsonElement view)
    {
        StatusText.Text = view.Str("status");
        var rows = new List<ListRow>();
        var index = 0;
        if (view.TryGetProperty("rewards", out var array) && array.ValueKind == JsonValueKind.Array)
            foreach (var item in array.EnumerateArray())
                rows.Add(new ListRow((index++).ToString(), item.GetString() ?? ""));
        _suppress = true;
        try
        {
            RewardList.SetRows(rows);
            if (RewardList.SelectedIndex < 0 && rows.Count > 0)
                RewardList.SelectedIndex = 0;
        }
        finally
        {
            _suppress = false;
        }
        var details = view.Str("details");
        if (Details.Text != details)
        {
            var caret = _detailsKey == _reward + ":" + _page ? Details.CaretIndex : 0;
            Details.Text = details;
            Details.CaretIndex = Math.Min(caret, details.Length);
        }
        _detailsKey = _reward + ":" + _page;

        var focused = Keyboard.FocusedElement as FrameworkElement;
        var buttons = view.TryGetProperty("buttons", out var b) ? b : default;
        RewardButton.IsEnabled = buttons.Bool("reward");
        PageButton.IsEnabled = buttons.Bool("page");
        SetButton.IsEnabled = buttons.Bool("set");
        SetButton.Visibility = buttons.Bool("set_visible", true) ? Visibility.Visible : Visibility.Collapsed;
        UnlockButton.IsEnabled = buttons.Bool("unlock");
        PurchaseButton.IsEnabled = buttons.Bool("purchase");
        QuestsButton.IsEnabled = buttons.Bool("quests");
        var notice = buttons.Bool("set_notice");
        SetNotice.Text = notice ? view.Str("set_notice") : "";
        SetNotice.Visibility = notice ? Visibility.Visible : Visibility.Collapsed;
        RefreshButton.IsEnabled = !_session.Busy;
        PassQuestsButton.IsEnabled = true;
        // A button that just turned off must not take the keyboard with it.
        if (focused is Button { IsEnabled: false } or Button { Visibility: not Visibility.Visible })
            RewardList.FocusSelected();
    }

    // Choosing -----------------------------------------------------------------------

    private void OnPageChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_suppress || PageBox.SelectedIndex < 0)
            return;
        _page = PageBox.SelectedIndex;
        _reward = 0;
        Render();
    }

    private void OnRewardSelected(object sender, SelectionChangedEventArgs e)
    {
        if (_suppress || RewardList.SelectedIndex < 0 || RewardList.SelectedIndex == _reward)
            return;
        _reward = RewardList.SelectedIndex;
        Render();
    }

    private void OnPreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key is not (Key.PageUp or Key.PageDown) || Keyboard.Modifiers != ModifierKeys.None || PageBox.IsDropDownOpen)
            return;
        e.Handled = true;
        var step = e.Key == Key.PageUp ? -1 : 1;
        var next = Math.Clamp(PageBox.SelectedIndex + step, 0, Math.Max(0, PageBox.Items.Count - 1));
        if (next == PageBox.SelectedIndex)
        {
            Announcer.Announce(Anchor, step < 0 ? "First page." : "Last page.");
            return;
        }
        PageBox.SelectedIndex = next; // OnPageChanged redraws
        RewardList.FocusSelected();
        Announcer.Announce(Anchor, PageBox.SelectedItem as string ?? "");
    }

    // Actions ------------------------------------------------------------------------

    private void OnRewardClick(object sender, RoutedEventArgs e) => Act("reward");
    private void OnPageClick(object sender, RoutedEventArgs e) => Act("page");
    private void OnSetClick(object sender, RoutedEventArgs e) => Act("set");
    private void OnUnlockClick(object sender, RoutedEventArgs e) => Act("unlock");
    private void OnPurchaseClick(object sender, RoutedEventArgs e) => Act("purchase");

    /// <summary>Work out the action in the core, ask the user to confirm it, then do it.</summary>
    private async void Act(string kind)
    {
        if (_session.Busy)
            return;
        try
        {
            var prepared = await App.Bridge.RequestAsync("passes.prepare",
                new { pass = _key, page = _page, reward = _reward, kind });
            var message = prepared.Str("message");
            if (message.Length > 0)
            {
                _session.Say(message);
                return;
            }
            var summary = prepared.Str("summary");
            if (summary.Length == 0)
                return;
            if (!Dialogs.Confirm(Window.GetWindow(this), "FA11y Locker Passes: Confirm", summary + "\n\nContinue?"))
            {
                RewardList.FocusSelected();
                return;
            }
            _session.SetBusy(true);
            string result;
            try
            {
                var done = await App.Bridge.RequestAsync("passes.execute", new { token = prepared.GetProperty("token").GetInt32() },
                    TimeSpan.FromSeconds(120));
                result = done.Str("message");
            }
            catch (Exception ex)
            {
                Log.Error("passes.execute failed", ex);
                result = "The result is uncertain. Refresh before trying again.";
            }
            finally
            {
                _session.SetBusy(false);
            }
            _session.Say(result);
        }
        catch (Exception ex)
        {
            Log.Error("passes.prepare failed", ex);
            _session.Say("Pass data could not be loaded. Refresh to retry.");
        }
    }

    private async void OnRefreshClick(object sender, RoutedEventArgs e) => await _session.RefreshAsync();

    private void OnRewardQuestsClick(object sender, RoutedEventArgs e) => OpenQuests(true, QuestsButton);

    private void OnPassQuestsClick(object sender, RoutedEventArgs e) => OpenQuests(false, PassQuestsButton);

    private async void OpenQuests(bool forReward, FrameworkElement opener)
    {
        try
        {
            var scope = await App.Bridge.RequestAsync("passes.quest_scope",
                new { pass = _key, page = _page, reward = forReward ? _reward : -1 });
            QuestsRequested?.Invoke(scope.Str("scope_id"), scope.Str("heading"), scope.Str("label"), opener);
        }
        catch (Exception e)
        {
            Log.Error("passes.quest_scope failed", e);
        }
    }

    private async void OnCloseClick(object sender, RoutedEventArgs e)
    {
        if (_session.Busy)
        {
            _session.Say("An account request is in progress. Close after it finishes.");
            return;
        }
        try
        {
            await App.Bridge.RequestAsync("quests.close");
        }
        catch (Exception ex)
        {
            Log.Error("quests.close failed", ex);
        }
    }
}
