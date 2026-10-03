using System.Text.Json;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using FA11y.UI.Core;

namespace FA11y.UI.Controls;

/// <summary>An island in a Discover list: its code and title, which the core needs to copy or launch it.</summary>
public sealed record IslandRef(string Code, string Title);

/// <summary>
/// One Discover list: a heading, optional controls above, the list, and Copy code and Launch
/// gamemode (Enter, a double click and Ctrl+C do the same on the selected row). The core builds
/// every row's text.
/// </summary>
public partial class IslandPanel : UserControl
{
    private int _token;

    public IslandPanel()
    {
        InitializeComponent();
        List.Activated += row => Launch(row);
        List.PreviewKeyDown += (_, e) =>
        {
            if (e.Key == Key.C && Keyboard.Modifiers == ModifierKeys.Control && List.SelectedRow is { } row)
            {
                e.Handled = true;
                Copy(row);
            }
        };
    }

    /// <summary>The list's name for screen readers.</summary>
    public string Heading
    {
        get => AutomationProperties.GetName(List);
        set => AutomationProperties.SetName(List, value);
    }

    public object? Extra
    {
        get => ExtraHost.Content;
        set => ExtraHost.Content = value;
    }

    public RowList Rows => List;

    /// <summary>Show one line that isn't an island (Loading..., an error). Returns a token for <see cref="Apply"/>.</summary>
    public int BeginLoad(string message)
    {
        ShowMessage(message);
        return ++_token;
    }

    public void ShowMessage(string message) =>
        List.SetRows(new[] { new ListRow("message", message, tag: new IslandRef("", "")) });

    /// <summary>Show a result from the core (rows, announce, only_if_focused), unless a newer load started.</summary>
    public void Apply(int token, JsonElement result)
    {
        if (token != _token)
            return;
        var rows = new List<ListRow>();
        var seen = new Dictionary<string, int>();
        if (result.TryGetProperty("rows", out var array) && array.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in array.EnumerateArray())
            {
                var code = item.Str("code");
                var key = code.Length == 0 ? "message" : code;
                seen[key] = seen.GetValueOrDefault(key) + 1;
                if (seen[key] > 1)
                    key += "#" + seen[key];
                rows.Add(new ListRow(key, item.Str("label"), tag: new IslandRef(code, item.Str("title"))));
            }
        }
        List.SetRows(rows);
        var announce = result.Str("announce");
        if (announce.Length > 0 && (!result.Bool("only_if_focused") || List.IsKeyboardFocusWithin))
            Announcer.Announce(this, announce);
    }

    /// <summary>The load failed before the core answered.</summary>
    public void Fail(int token, string message)
    {
        if (token != _token)
            return;
        ShowMessage(message);
        Announcer.Announce(this, message.TrimEnd('.'));
    }

    private void OnCopyClick(object sender, RoutedEventArgs e)
    {
        if (List.SelectedRow is { } row)
            Copy(row);
    }

    private void OnLaunchClick(object sender, RoutedEventArgs e)
    {
        if (List.SelectedRow is { } row)
            Launch(row);
    }

    private async void Copy(ListRow row)
    {
        var island = (IslandRef)row.Tag!;
        try
        {
            var result = await App.Bridge.RequestAsync("discover.copy", new { code = island.Code, title = island.Title });
            Announcer.Announce(this, result.Str("announce"));
        }
        catch (Exception e)
        {
            Log.Error("discover.copy failed", e);
        }
    }

    private async void Launch(ListRow row)
    {
        var island = (IslandRef)row.Tag!;
        try
        {
            // On success the core speaks, then hides the window.
            var result = await App.Bridge.RequestAsync("discover.launch", new { code = island.Code, title = island.Title });
            if (!result.Bool("launched"))
                Announcer.Announce(this, result.Str("announce"));
        }
        catch (Exception e)
        {
            Log.Error("discover.launch failed", e);
            Announcer.Announce(this, "Couldn't launch the gamemode");
        }
    }
}
