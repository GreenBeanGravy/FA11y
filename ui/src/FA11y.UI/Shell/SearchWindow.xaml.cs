using System.Windows;
using System.Windows.Input;
using System.Windows.Threading;
using FA11y.UI.Core;

namespace FA11y.UI.Shell;

/// <summary>One setting in the search index: what is shown ("Announce ammo, Toggles") and where it is.</summary>
public sealed record SearchEntry(string Id, string Label, string Tab, string TabName, string? Map, string Hay, string Text);

/// <summary>
/// The Ctrl+F popup: type to filter the settings, Up and Down move through the matches without leaving the
/// text box, Enter picks one, Escape closes. The matching and ordering are the wx search's: every word
/// must appear in the label, key name or description, and exact and leading matches of the label come first.
/// </summary>
public partial class SearchWindow : Window
{
    private readonly IReadOnlyList<SearchEntry> _entries;
    private List<SearchEntry> _shown = new();
    private readonly DispatcherTimer _countTimer = new() { Interval = TimeSpan.FromMilliseconds(500) };

    public SearchWindow(Window? owner, IReadOnlyList<SearchEntry> entries)
    {
        InitializeComponent();
        WindowTools.UseDarkTitleBar(this);
        _entries = entries;
        if (owner != null && owner.IsVisible)
            Owner = owner;
        else
            WindowStartupLocation = WindowStartupLocation.CenterScreen;

        SearchBox.TextChanged += (_, _) =>
        {
            Populate(SearchBox.Text);
            _countTimer.Stop();
            _countTimer.Start();
        };
        _countTimer.Tick += (_, _) =>
        {
            _countTimer.Stop();
            Announcer.Announce(this, Status.AccessibleText);
        };
        SearchBox.PreviewKeyDown += OnSearchKeyDown;
        Results.PreviewKeyDown += (_, e) =>
        {
            if (e.Key == Key.Enter)
            {
                e.Handled = true;
                Accept();
            }
        };
        Results.MouseDoubleClick += (_, _) => Accept();
        PreviewKeyDown += (_, e) =>
        {
            if (e.Key == Key.Escape)
            {
                e.Handled = true;
                DialogResult = false;
            }
        };
        Loaded += (_, _) =>
        {
            SearchBox.Focus();
            Announcer.Announce(this, "Search settings.", important: true);
        };
        Closed += (_, _) => _countTimer.Stop();
        Populate("");
    }

    /// <summary>The setting picked, or null when the popup was closed without one.</summary>
    public SearchEntry? Result { get; private set; }

    private void Populate(string query)
    {
        var q = query.Trim().ToLowerInvariant();
        if (q.Length == 0)
        {
            _shown = _entries.ToList();
        }
        else
        {
            var terms = q.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            _shown = _entries
                .Where(e => terms.All(t => e.Hay.Contains(t, StringComparison.Ordinal)))
                .Select(e => (Entry: e, Label: e.Label.ToLowerInvariant()))
                .Select(x => (x.Entry, x.Label, Score: x.Label == q ? -1000 : x.Label.StartsWith(q, StringComparison.Ordinal) ? -500
                                                  : x.Label.Contains(q, StringComparison.Ordinal) ? -100 : 0))
                .OrderBy(x => x.Score)
                .ThenBy(x => x.Label, StringComparer.Ordinal)
                .Select(x => x.Entry)
                .ToList();
        }
        Results.ItemsSource = _shown.Select(e => e.Text).ToList();
        if (_shown.Count > 0)
            Results.SelectedIndex = 0;
        Status.Text = _shown.Count == 1 ? "1 match" : $"{_shown.Count} matches";
    }

    private void OnSearchKeyDown(object sender, KeyEventArgs e)
    {
        switch (e.Key)
        {
            case Key.Down:
                e.Handled = true;
                MoveSelection(1);
                break;
            case Key.Up:
                e.Handled = true;
                MoveSelection(-1);
                break;
            case Key.Enter:
                e.Handled = true;
                Accept();
                break;
        }
    }

    private void MoveSelection(int delta)
    {
        if (_shown.Count == 0)
            return;
        var index = Math.Max(0, Math.Min(_shown.Count - 1, Math.Max(Results.SelectedIndex, 0) + delta));
        if (index == Results.SelectedIndex)
            return;
        Results.SelectedIndex = index;
        Results.ScrollIntoView(Results.SelectedItem);
        // Focus stays in the text box, so say what is selected.
        _countTimer.Stop();
        Announcer.Announce(this, _shown[index].Text);
    }

    private void Accept()
    {
        var index = Results.SelectedIndex;
        if (index < 0 || index >= _shown.Count)
            return;
        Result = _shown[index];
        DialogResult = true;
    }
}
