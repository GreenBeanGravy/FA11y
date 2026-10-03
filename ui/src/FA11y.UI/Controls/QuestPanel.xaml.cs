using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using FA11y.UI.Core;

namespace FA11y.UI.Controls;

/// <summary>
/// The quest browser: filters (mode, category, search, status, expired), the list of quests, and
/// the selected quest's details. The core decides what each filter offers and what each row says
/// (lib/utilities/quest_view.py). With a scope it shows only the quests
/// linked to a pass reward, and Close returns to the pass.
/// </summary>
public partial class QuestPanel : UserControl
{
    private readonly string? _scopeId;
    private readonly DispatcherTimer _accountTimer = new() { Interval = TimeSpan.FromSeconds(60) };
    private readonly DispatcherTimer _searchTimer = new() { Interval = TimeSpan.FromMilliseconds(250) };
    private bool _suppress;
    private bool _loading;
    private bool _active;
    private int _token;
    private string? _mode;
    private string? _category;
    private string? _detailsKey;
    private string _emptyDetails = "No quests match these filters.";

    public QuestPanel(string? scopeId = null, string? heading = null)
    {
        InitializeComponent();
        _scopeId = scopeId;
        Intro.Text = heading ?? "Browse your account quests before or during a match.";
        StatusBox.SelectedIndex = scopeId != null ? 2 : 0;
        if (scopeId != null)
            _mode = "All modes";
        StatusText.Text = "Quests have not been loaded.";
        _accountTimer.Tick += async (_, _) =>
        {
            if (IsVisible)
                await RefreshAsync();
        };
        _searchTimer.Tick += (_, _) =>
        {
            _searchTimer.Stop();
            Render();
        };
    }

    /// <summary>The quest list was replaced by "not signed in": the page shows its own message.</summary>
    public event Action? SignedOut;

    /// <summary>Close was pressed on a scoped panel.</summary>
    public event Action? CloseRequested;

    public FrameworkElement FirstFocus => SearchBox;

    /// <summary>Shown: load the account's quests (the main panel) and keep them fresh.</summary>
    public async void Activate()
    {
        _active = true;
        Render();
        if (_scopeId == null)
            await RefreshAsync();
    }

    public void Deactivate()
    {
        _active = false;
        _accountTimer.Stop();
        _searchTimer.Stop();
    }

    public async Task RefreshAsync()
    {
        if (_loading)
            return;
        _loading = true;
        StatusText.Text = "Loading quests from Epic Games.";
        try
        {
            var result = await App.Bridge.RequestAsync("quests.refresh", null, TimeSpan.FromSeconds(60));
            if (!result.NullableBool("signed_in").GetValueOrDefault(true))
            {
                SignedOut?.Invoke();
                return;
            }
            // A failed refresh stops the timer; the next good one restarts it.
            if (result.Str("error").Length > 0)
                _accountTimer.Stop();
            else if (_active)
                _accountTimer.Start();
        }
        catch (Exception e)
        {
            Log.Error("quests.refresh failed", e);
            _accountTimer.Stop();
        }
        finally
        {
            _loading = false;
        }
        Render();
    }

    /// <summary>Ask the core what to show for the current filters.</summary>
    public async void Render()
    {
        var token = ++_token;
        try
        {
            var result = await App.Bridge.RequestAsync("quests.view", new
            {
                mode = _mode,
                category = _category,
                status = ((ComboBoxItem?)StatusBox.SelectedItem)?.Content as string ?? "Active",
                query = SearchBox.Text,
                expired = ExpiredBox.IsChecked == true,
                scope_id = _scopeId,
            });
            if (token != _token)
                return;
            if (!result.Bool("signed_in"))
            {
                SignedOut?.Invoke();
                return;
            }
            Apply(result);
        }
        catch (Exception e)
        {
            Log.Error("quests.view failed", e);
            if (token == _token)
                StatusText.Text = "Couldn't load quests. Refresh to retry.";
        }
    }

    private void Apply(JsonElement view)
    {
        _suppress = true;
        try
        {
            _mode = view.Str("mode");
            _category = view.Str("category");
            SetChoices(ModeBox, Strings(view, "modes"), _mode);
            SetChoices(CategoryBox, Strings(view, "categories"), _category);
        }
        finally
        {
            _suppress = false;
        }
        _emptyDetails = view.Str("empty_details", _emptyDetails);
        var rows = new List<ListRow>();
        if (view.TryGetProperty("rows", out var array) && array.ValueKind == JsonValueKind.Array)
            foreach (var item in array.EnumerateArray())
                rows.Add(new ListRow(item.Str("id"), item.Str("label"), item.Str("details")));
        QuestList.SetRows(rows);
        ShowDetails();
        StatusText.Text = view.Str("status");
        var heading = view.Str("heading");
        if (heading.Length > 0)
            Intro.Text = heading;
    }

    private static List<string> Strings(JsonElement view, string name)
    {
        var list = new List<string>();
        if (view.TryGetProperty(name, out var array) && array.ValueKind == JsonValueKind.Array)
            foreach (var item in array.EnumerateArray())
                if (item.ValueKind == JsonValueKind.String)
                    list.Add(item.GetString() ?? "");
        return list;
    }

    /// <summary>Replace a combo box's items only when they changed, and select one.</summary>
    private static void SetChoices(ComboBox box, List<string> values, string selected)
    {
        var current = box.Items.Cast<object>().Select(o => o.ToString() ?? "").ToList();
        if (!current.SequenceEqual(values))
            box.ItemsSource = values;
        var index = values.IndexOf(selected);
        if (box.SelectedIndex != index)
            box.SelectedIndex = index;
    }

    private void ShowDetails()
    {
        var row = QuestList.SelectedRow;
        var text = row?.Details ?? _emptyDetails;
        var key = row?.Key;
        if (Details.Text == text)
        {
            _detailsKey = key;
            return;
        }
        // Keep the reading position when the same quest's numbers change.
        var caret = key != null && key == _detailsKey ? Details.CaretIndex : 0;
        Details.Text = text;
        Details.CaretIndex = Math.Min(caret, text.Length);
        _detailsKey = key;
    }

    // Controls ------------------------------------------------------------------------

    private void OnQuestSelected(object sender, SelectionChangedEventArgs e) => ShowDetails();

    private void OnModeChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_suppress || ModeBox.SelectedItem is not string mode)
            return;
        _mode = mode;
        _category = null; // a new mode starts on all its categories
        Render();
    }

    private void OnFilterChanged(object sender, RoutedEventArgs e)
    {
        if (_suppress || !IsLoaded)
            return;
        if (sender == CategoryBox)
        {
            if (CategoryBox.SelectedItem is not string category)
                return;
            _category = category;
        }
        Render();
    }

    private void OnSearchChanged(object sender, TextChangedEventArgs e)
    {
        if (!IsLoaded)
            return;
        _searchTimer.Stop();
        _searchTimer.Start();
    }

    private async void OnRefreshClick(object sender, RoutedEventArgs e) => await RefreshAsync();

    private async void OnCloseClick(object sender, RoutedEventArgs e)
    {
        if (_scopeId != null)
        {
            CloseRequested?.Invoke();
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
