using System.Text.Json;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using FA11y.UI.Controls;
using FA11y.UI.Core;
using FA11y.UI.Shell;
using WpfKey = System.Windows.Input.Key;

namespace FA11y.UI.Pages;

/// <summary>
/// The Settings and Keybinds pages: one editor the core describes with settings.schema (tabs, groups,
/// settings) and this page draws. A change is saved as it is made (settings.set); the numbers wait a moment
/// after the last keystroke or arrow press. Shortcuts: R resets the focused setting,
/// T tests a volume, Delete unbinds a keybind, Ctrl+F searches. Each tab's controls are built the first time
/// the tab is shown, or while the window is idle. Messages that aren't tied to focus are announced.
/// </summary>
public partial class SettingsPage : PageBase
{
    private const string MapHelp = "Pick which map's per-object tracking settings to view and edit.";

    /// <summary>One setting's control and its state while it is saved.</summary>
    private sealed class SettingView
    {
        public SettingView(SettingModel model, TabState tab)
        {
            Model = model;
            Tab = tab;
        }

        public SettingModel Model { get; }
        public TabState Tab { get; }
        public FrameworkElement Control { get; set; } = null!;
        public NumberBox? Number { get; set; }
        public KeybindButton? Keybind { get; set; }
        public bool Applying { get; set; }
        public Func<object> Read { get; set; } = () => "";
        public Action<JsonElement> Apply { get; set; } = _ => { };
        public DispatcherTimer? Debounce { get; set; }
        public bool Wanted { get; set; }
        public Task? Saving { get; set; }
    }

    private sealed class TabState
    {
        public string Name = "";
        public JsonElement Data;
        public TabItem? Item;
        public ScrollViewer Scroll = null!;
        public StackPanel Host = null!;
        public bool Built;
        public readonly List<SettingView> Order = new();
        // The GameObjects tab: a map picker, and one panel of settings per map, fetched when first shown.
        public List<(string Key, string Name)> Maps = new();
        public ComboBox? Picker;
        public StackPanel? MapHost;
        public readonly Dictionary<string, StackPanel> MapPanels = new();
        public string? WantedMap;
    }

    private readonly string _view;
    private readonly Dictionary<string, SettingView> _settings = new();
    private readonly List<TabState> _tabs = new();
    private TabControl? _tabControl;
    private bool _loaded;
    private bool _loading;
    private int _generation;
    private IReadOnlyList<SearchEntry>? _entries;
    private KeybindButton? _capturing;
    private Task _captureChain = Task.CompletedTask;

    public SettingsPage(string view)
    {
        _view = view;
        InitializeComponent();
        Heading.Text = Title;
        LoadingText.Text = "Loading…";
        PreviewKeyDown += OnPagePreviewKeyDown;
        if (App.Bridge.Connected)
            _ = LoadAsync();
        else
            LoadingText.Text = "FA11y isn't running, so there is nothing to show.";
    }

    public override string Key => _view;
    public override string Title => _view == "keybinds" ? "Keybinds" : "Settings";

    public override void OnShown()
    {
        if (!_loaded && !_loading && App.Bridge.Connected)
            _ = LoadAsync();
        Perf.Measure(Dispatcher, $"{_view} page shown", () => { });
    }

    public override void OnHidden()
    {
        CancelCapture();
        _ = FlushAsync();
        App.Bridge.Notify("settings.leave");
    }

    public override void Refresh() => _ = LoadAsync();

    public override FrameworkElement? FirstFocus()
    {
        if (!_loaded)
            return LoadingText;
        var tab = CurrentTab();
        if (tab == null)
            return null;
        EnsureBuilt(tab);
        return tab.Order.FirstOrDefault()?.Control ?? tab.Picker ?? (FrameworkElement?)_tabControl;
    }

    // Loading ---------------------------------------------------------------------------------------

    private async Task LoadAsync()
    {
        if (_loading)
            return;
        _loading = true;
        try
        {
            var schema = await App.Bridge.RequestAsync("settings.schema", new { view = _view }, TimeSpan.FromSeconds(30));
            Rebuild(schema);
        }
        catch (Exception e)
        {
            Log.Error($"settings.schema ({_view}) failed", e);
            if (!_loaded)
                LoadingText.Text = $"Couldn't load the {Title.ToLowerInvariant()}.";
        }
        finally
        {
            _loading = false;
        }
    }

    private void Rebuild(JsonElement schema)
    {
        var hadFocus = LoadingText.IsKeyboardFocused;
        var selected = CurrentTab()?.Name;
        _generation++;
        CancelCapture();
        foreach (var view in _settings.Values)
            view.Debounce?.Stop();
        _settings.Clear();
        _tabs.Clear();
        _entries = null;
        _tabControl = null;
        ContentHost.Children.Clear();

        foreach (var tab in schema.GetProperty("tabs").EnumerateArray())
        {
            var state = new TabState { Name = tab.Str("name"), Data = tab };
            if (tab.TryGetProperty("maps", out var maps) && maps.ValueKind == JsonValueKind.Array)
                state.Maps = maps.EnumerateArray().Select(m => (m.Str("key"), m.Str("name"))).ToList();
            state.Host = new StackPanel();
            Grid.SetIsSharedSizeScope(state.Host, true);
            state.Scroll = new ScrollViewer
            {
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
                Content = state.Host,
            };
            _tabs.Add(state);
        }

        if (_tabs.Count == 0)
        {
            LoadingText.Text = "There is nothing to show here.";
            return;
        }
        if (_tabs.Count == 1)
        {
            ContentHost.Children.Add(_tabs[0].Scroll);
            EnsureBuilt(_tabs[0]);
        }
        else
        {
            var control = new TabControl();
            AutomationProperties.SetName(control, "Tabs");
            foreach (var state in _tabs)
            {
                var item = new TabItem { Header = state.Name, Content = state.Scroll, Tag = state };
                AutomationProperties.SetName(item, state.Name);
                state.Item = item;
                control.Items.Add(item);
            }
            var wanted = _tabs.FirstOrDefault(t => t.Name == selected) ?? _tabs[0];
            control.SelectedItem = wanted.Item;
            control.SelectionChanged += OnTabChanged;
            _tabControl = control;
            ContentHost.Children.Add(control);
            EnsureBuilt(wanted);
        }

        _loaded = true;
        if (hadFocus || LoadingText.IsKeyboardFocused)
        {
            Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
            {
                UpdateLayout();
                FirstFocus()?.Focus();
            });
        }

        var generation = _generation;
        Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, () => BuildNext(generation));
    }

    /// <summary>While the window is idle, build the tabs nobody has opened yet, one at a time.</summary>
    private void BuildNext(int generation)
    {
        if (generation != _generation)
            return;
        var next = _tabs.FirstOrDefault(t => !t.Built);
        if (next == null)
            return;
        EnsureBuilt(next);
        Dispatcher.BeginInvoke(DispatcherPriority.ApplicationIdle, () => BuildNext(generation));
    }

    private void OnTabChanged(object sender, SelectionChangedEventArgs e)
    {
        if (e.OriginalSource != _tabControl)
            return; // a combo box inside a tab
        if (CurrentTab() is { } tab)
            Perf.Measure(Dispatcher, $"{_view} tab {tab.Name}", () => EnsureBuilt(tab));
    }

    private TabState? CurrentTab() =>
        _tabs.Count == 1 ? _tabs[0] : (_tabControl?.SelectedItem as TabItem)?.Tag as TabState;

    // Building a tab -------------------------------------------------------------------------------------

    private void EnsureBuilt(TabState tab)
    {
        if (tab.Built)
            return;
        tab.Built = true;
        foreach (var group in tab.Data.GetProperty("groups").EnumerateArray())
            tab.Host.Children.Add(BuildGroup(group, tab, tab.Order));
        if (tab.Maps.Count > 0)
            BuildMapPicker(tab);
    }

    private SettingsGroup BuildGroup(JsonElement group, TabState tab, List<SettingView> order)
    {
        var heading = group.Str("heading");
        var rows = new StackPanel();
        var box = new SettingsGroup { Header = heading, Content = rows };
        AutomationProperties.SetName(box, heading);
        foreach (var setting in group.GetProperty("settings").EnumerateArray())
            rows.Children.Add(BuildSetting(SettingModel.From(setting), tab, order));
        return box;
    }

    private UIElement BuildSetting(SettingModel model, TabState tab, List<SettingView> order)
    {
        var view = new SettingView(model, tab);
        _settings[model.Id] = view;
        order.Add(view);
        var describe = model.ShowDescription && model.Description.Length > 0;

        if (model.Kind == "toggle")
        {
            var check = new CheckOption
            {
                Content = model.Label,
                IsChecked = model.Value.ValueKind == JsonValueKind.True,
                Tag = view,
            };
            Describe(check, model);
            check.Checked += (_, _) => Changed(view, immediate: true);
            check.Unchecked += (_, _) => Changed(view, immediate: true);
            view.Control = check;
            view.Read = () => check.IsChecked == true;
            view.Apply = v => WithoutEvents(view, () => check.IsChecked = v.ValueKind == JsonValueKind.True);
            var stack = new StackPanel { Margin = new Thickness(0, 0, 0, 4) };
            stack.Children.Add(check);
            if (describe)
                stack.Children.Add(DescriptionText(model.Description, 28));
            return stack;
        }

        FrameworkElement control;
        FrameworkElement placed;
        switch (model.Kind)
        {
            case "number":
            case "volume":
                var number = NewNumberBox(model, view);
                control = placed = number;
                if (model.Kind == "volume")
                {
                    var test = new IconButton { Content = "Test", Margin = new Thickness(8, 0, 0, 0), Tag = view };
                    AutomationProperties.SetName(test, $"Test {model.Label}");
                    test.Click += (_, _) => _ = TestVolumeAsync(view);
                    placed = new StackPanel { Orientation = Orientation.Horizontal, Children = { number, test } };
                }
                break;
            case "choice":
                var combo = new ComboBox { Width = 260, Tag = view, ItemsSource = model.Choices.Select(c => c.Label).ToList() };
                combo.SelectedIndex = Math.Max(0, IndexOf(model, model.Value.ValueKind == JsonValueKind.String ? model.Value.GetString() : null));
                combo.SelectionChanged += (_, e) =>
                {
                    if (e.OriginalSource == combo && combo.SelectedIndex >= 0)
                        Changed(view, immediate: true);
                };
                view.Read = () => model.Choices[Math.Max(0, combo.SelectedIndex)].Value;
                view.Apply = v => WithoutEvents(view, () =>
                    combo.SelectedIndex = Math.Max(0, IndexOf(model, v.ValueKind == JsonValueKind.String ? v.GetString() : null)));
                control = placed = combo;
                break;
            case "keybind":
                var button = new KeybindButton { Action = model.Key, Width = 220, Tag = view };
                button.SetKey(model.Display);
                button.Click += (_, _) => BeginCapture(button);
                button.Captured += (vk, modifiers) => _ = BindAsync(button, model.Key, vk, modifiers);
                button.Cancelled += () =>
                {
                    if (_capturing == button)
                        _capturing = null;
                    HideKeyCapture();
                    _ = SetCaptureAsync(false);
                };
                view.Keybind = button;
                control = placed = button;
                break;
            default:
                var text = new TextBox { Width = 260, Text = model.Value.ValueKind == JsonValueKind.String ? model.Value.GetString() : "", Tag = view };
                text.TextChanged += (_, _) => Changed(view, immediate: false);
                text.LostKeyboardFocus += (_, _) =>
                {
                    if (view.Debounce is { IsEnabled: true })
                        Changed(view, immediate: true);
                };
                view.Read = () => text.Text ?? "";
                view.Apply = v => WithoutEvents(view, () => text.Text = v.GetString() ?? "");
                control = placed = text;
                break;
        }
        view.Control = control;
        if (model.Kind != "keybind")
            AutomationProperties.SetName(control, model.Label);
        AutomationProperties.SetHelpText(control, model.Description);

        var grid = new Grid { Margin = new Thickness(0, 0, 0, 4) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto, SharedSizeGroup = "label" });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        var label = new HiddenText { Text = model.Label, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 16, 0) };
        grid.Children.Add(label);
        Grid.SetColumn(placed, 1);
        placed.VerticalAlignment = VerticalAlignment.Center;
        grid.Children.Add(placed);
        if (!describe)
            return grid;
        // The note sits outside the grid so its width doesn't stretch the shared label column.
        grid.Margin = new Thickness(0, 0, 0, 0);
        var note = DescriptionText(model.Description, 0);
        var row = new StackPanel();
        row.Children.Add(grid);
        row.Children.Add(note);
        return row;
    }

    private NumberBox NewNumberBox(SettingModel model, SettingView view)
    {
        var box = new NumberBox
        {
            Width = 130,
            Minimum = model.Min,
            Maximum = model.Max,
            Step = model.Step,
            Decimals = model.Decimals,
            Tag = view,
        };
        box.SetValue(model.Value.ValueKind == JsonValueKind.Number ? model.Value.GetDouble() : 0);
        box.Edited += immediate => Changed(view, immediate);
        view.Number = box;
        view.Read = () => box.Value;
        view.Apply = v => WithoutEvents(view, () =>
        {
            if (v.ValueKind == JsonValueKind.Number)
                box.SetValue(v.GetDouble());
        });
        return box;
    }

    private static int IndexOf(SettingModel model, string? value)
    {
        for (var i = 0; i < model.Choices.Count; i++)
        {
            if (model.Choices[i].Value == value)
                return i;
        }
        return 0;
    }

    private static void Describe(FrameworkElement control, SettingModel model) =>
        AutomationProperties.SetHelpText(control, model.Description);

    private TextBlock DescriptionText(string text, double indent) => new HiddenText
    {
        Text = text,
        TextWrapping = TextWrapping.Wrap,
        MaxWidth = 560,
        HorizontalAlignment = HorizontalAlignment.Left,
        Foreground = (Brush)FindResource("TextMuted"),
        FontSize = (double)FindResource("SmallFontSize"),
        Margin = new Thickness(indent, 0, 0, 6),
    };

    private static void WithoutEvents(SettingView view, Action action)
    {
        view.Applying = true;
        try { action(); }
        finally { view.Applying = false; }
    }

    // The GameObjects tab: universal settings, then a map picker and the picked map's settings -------------

    private void BuildMapPicker(TabState tab)
    {
        var rows = new StackPanel();
        var box = new SettingsGroup { Header = "Each map", Content = rows };
        AutomationProperties.SetName(box, "Each map");

        var combo = new ComboBox { Width = 260, ItemsSource = tab.Maps.Select(m => m.Name).ToList(), SelectedIndex = 0 };
        AutomationProperties.SetName(combo, "Map");
        AutomationProperties.SetHelpText(combo, MapHelp);
        combo.SelectionChanged += (_, e) =>
        {
            if (e.OriginalSource == combo && combo.SelectedIndex >= 0)
                _ = ShowMapAsync(tab, tab.Maps[combo.SelectedIndex].Key);
        };
        tab.Picker = combo;

        var grid = new Grid { Margin = new Thickness(0, 0, 0, 4) };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto, SharedSizeGroup = "label" });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.Children.Add(new HiddenText { Text = "Map", VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 0, 16, 0) });
        Grid.SetColumn(combo, 1);
        grid.Children.Add(combo);
        rows.Children.Add(grid);
        tab.Host.Children.Add(box);

        tab.MapHost = new StackPanel();
        tab.Host.Children.Add(tab.MapHost);
        _ = ShowMapAsync(tab, tab.Maps[0].Key);
    }

    /// <summary>Show one map's settings, asking the core for them the first time.</summary>
    private async Task ShowMapAsync(TabState tab, string map)
    {
        if (tab.MapHost == null)
            return;
        tab.WantedMap = map;
        var generation = _generation;
        if (!tab.MapPanels.ContainsKey(map))
        {
            JsonElement data;
            try
            {
                data = await App.Bridge.RequestAsync("settings.map", new { map });
            }
            catch (Exception e)
            {
                Log.Error($"settings.map {map} failed", e);
                Announcer.Announce(Host ?? (UIElement)this, "Couldn't load that map's settings.");
                return;
            }
            if (generation != _generation)
                return;
            if (!tab.MapPanels.ContainsKey(map))
            {
                var panel = new StackPanel { Visibility = Visibility.Collapsed };
                foreach (var group in data.GetProperty("groups").EnumerateArray())
                    panel.Children.Add(BuildGroup(group, tab, new List<SettingView>()));
                tab.MapPanels[map] = panel;
                tab.MapHost.Children.Add(panel);
            }
        }
        foreach (var (key, panel) in tab.MapPanels)
            panel.Visibility = key == tab.WantedMap ? Visibility.Visible : Visibility.Collapsed;
    }

    // Saving --------------------------------------------------------------------------------------------

    private void Changed(SettingView view, bool immediate)
    {
        if (view.Applying)
            return;
        if (immediate)
        {
            view.Debounce?.Stop();
            _ = CommitAsync(view);
            return;
        }
        if (view.Debounce == null)
        {
            view.Debounce = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(600) };
            view.Debounce.Tick += (_, _) =>
            {
                view.Debounce.Stop();
                _ = CommitAsync(view);
            };
        }
        view.Debounce.Stop();
        view.Debounce.Start();
    }

    private Task CommitAsync(SettingView view)
    {
        view.Wanted = true;
        if (view.Saving != null)
            return view.Saving;
        var task = SaveLoopAsync(view);
        if (!task.IsCompleted)
            view.Saving = task;
        return task;
    }

    /// <summary>Save the setting; if it changed again while saving, save that too, so the last edit wins.</summary>
    private async Task SaveLoopAsync(SettingView view)
    {
        try
        {
            while (view.Wanted)
            {
                view.Wanted = false;
                var model = view.Model;
                try
                {
                    var result = await App.Bridge.RequestAsync("settings.set",
                        new { section = model.Section, key = model.Key, kind = model.Kind, value = view.Read() });
                    // The core may have held the value to its range; show what was saved.
                    if (!view.Wanted && view.Debounce is not { IsEnabled: true } && result.TryGetProperty("value", out var saved))
                        view.Apply(saved);
                }
                catch (Exception e)
                {
                    Log.Error($"settings.set {model.Id} failed", e);
                    Announce($"Couldn't save {model.Label}.");
                }
            }
        }
        finally
        {
            view.Saving = null;
        }
    }

    /// <summary>Save everything that is waiting on a timer.</summary>
    private Task FlushAsync()
    {
        var tasks = new List<Task>();
        foreach (var view in _settings.Values)
        {
            if (view.Debounce is { IsEnabled: true })
            {
                view.Debounce.Stop();
                tasks.Add(CommitAsync(view));
            }
            else if (view.Saving != null)
            {
                tasks.Add(view.Saving);
            }
        }
        return Task.WhenAll(tasks);
    }

    private async Task ResetAsync(SettingView view)
    {
        var model = view.Model;
        view.Debounce?.Stop();
        view.Wanted = false;
        try
        {
            var result = await App.Bridge.RequestAsync("settings.reset",
                new { section = model.Section, key = model.Key, kind = model.Kind, label = model.Label });
            if (result.Bool("changed"))
            {
                if (model.Kind == "keybind")
                    ApplyKeybindChanges(result);
                else if (result.TryGetProperty("value", out var value))
                    view.Apply(value);
            }
            Announce(result.Str("message"));
        }
        catch (Exception e)
        {
            Log.Error($"settings.reset {model.Id} failed", e);
            Announce($"Couldn't reset {model.Label}.");
        }
    }

    private async Task TestVolumeAsync(SettingView view)
    {
        try
        {
            await FlushAsync();
            await App.Bridge.RequestAsync("settings.test_volume", new { key = view.Model.Key, value = view.Number?.Value ?? 100 });
        }
        catch (Exception e)
        {
            Log.Error("settings.test_volume failed", e);
        }
    }

    // Keybinds ------------------------------------------------------------------------------------------

    private void BeginCapture(KeybindButton button)
    {
        if (_capturing != null && _capturing != button)
            _capturing.EndCapture(true);
        _capturing = button;
        // Full screen "press a key" screen; clicks anywhere on it reach the button as mouse buttons.
        if (Window.GetWindow(this) is Shell.MainWindow main)
        {
            main.ShowKeyCapture(button.Action, button.CaptureMouseButton);
            button.Focus();
        }
        button.BeginCapture();
        _ = SetCaptureAsync(true);
    }

    private void CancelCapture()
    {
        if (_capturing is not { Capturing: true } button)
            return;
        button.EndCapture(true);
        _capturing = null;
        HideKeyCapture();
        _ = SetCaptureAsync(false);
    }

    /// <summary>Tell the core whether FA11y's own keybinds should stay quiet. Requests are sent in order.</summary>
    private Task SetCaptureAsync(bool active)
    {
        var previous = _captureChain;
        async Task Send()
        {
            try { await previous; } catch { /* the earlier one already logged */ }
            try { await App.Bridge.RequestAsync("keybinds.capture", new { active }, TimeSpan.FromSeconds(10)); }
            catch (Exception e) { Log.Error("keybinds.capture failed", e); }
        }
        return _captureChain = Send();
    }

    private async Task BindAsync(KeybindButton button, string action, int vk, int[] modifiers)
    {
        _capturing = null;
        var off = SetCaptureAsync(false);
        try
        {
            var result = await App.Bridge.RequestAsync("keybinds.bind", new { action, vk, modifiers });
            if (result.Bool("ok"))
                ApplyKeybindChanges(result);
            else
                button.RestoreKey();
            Announce(result.Str("message"));
        }
        catch (Exception e)
        {
            Log.Error($"keybinds.bind {action} failed", e);
            button.RestoreKey();
            Announce($"Couldn't change {action}.");
        }
        // Leave full screen only now: the window changing size makes screen readers read the focused
        // button again, and it should say the new key.
        HideKeyCapture();
        await off;
    }

    private void HideKeyCapture()
    {
        if (Window.GetWindow(this) is Shell.MainWindow main)
            main.HideKeyCapture();
    }

    private async Task UnbindAsync(SettingView view)
    {
        var action = view.Model.Key;
        try
        {
            var result = await App.Bridge.RequestAsync("keybinds.clear", new { action });
            ApplyKeybindChanges(result);
            Announce(result.Str("message"));
        }
        catch (Exception e)
        {
            Log.Error($"keybinds.clear {action} failed", e);
            Announce($"Couldn't unbind {action}.");
        }
    }

    private void ApplyKeybindChanges(JsonElement result)
    {
        if (!result.TryGetProperty("changes", out var changes) || changes.ValueKind != JsonValueKind.Array)
            return;
        foreach (var change in changes.EnumerateArray())
        {
            if (_settings.TryGetValue($"Keybinds/{change.Str("action")}", out var view))
                view.Keybind?.SetKey(change.Str("display", "Unbound"));
        }
    }

    // Keys ------------------------------------------------------------------------------------------------

    private void OnPagePreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (KeyCapture.Active || !_loaded)
            return;
        var modifiers = KeyState.Modifiers;
        if (e.Key == WpfKey.F && modifiers == ModifierKeys.Control)
        {
            e.Handled = true;
            _ = OpenSearchAsync();
            return;
        }
        if (modifiers != ModifierKeys.None || FocusedSetting(e.OriginalSource as DependencyObject) is not { } view || view.Model.Kind == "text")
            return;
        if (e.Key == WpfKey.R)
        {
            e.Handled = true;
            _ = ResetAsync(view);
        }
        else if (e.Key == WpfKey.Delete && view.Model.Kind == "keybind")
        {
            e.Handled = true;
            _ = UnbindAsync(view);
        }
        else if (e.Key == WpfKey.T && view.Model.Kind == "volume")
        {
            e.Handled = true;
            _ = TestVolumeAsync(view);
        }
    }

    /// <summary>The setting whose control (or part of it) the key was pressed in.</summary>
    private static SettingView? FocusedSetting(DependencyObject? source)
    {
        for (var node = source; node != null;
             node = node is Visual or System.Windows.Media.Media3D.Visual3D ? VisualTreeHelper.GetParent(node) : LogicalTreeHelper.GetParent(node))
        {
            if (node is FrameworkElement { Tag: SettingView view })
                return view;
        }
        return null;
    }

    public override bool HandleEscape()
    {
        if (_capturing is { Capturing: true })
        {
            CancelCapture();
            return true;
        }
        return false;
    }

    // Search ----------------------------------------------------------------------------------------------

    private async Task OpenSearchAsync()
    {
        try
        {
            if (_entries == null)
            {
                var result = await App.Bridge.RequestAsync("settings.search_index", new { view = _view });
                _entries = result.GetProperty("entries").EnumerateArray()
                    .Select(e => new SearchEntry(e.Str("id"), e.Str("label"), e.Str("tab"), e.Str("tab_name"),
                        e.NullableStr("map"), e.Str("hay"), e.Str("text")))
                    .ToList();
            }
        }
        catch (Exception e)
        {
            Log.Error("settings.search_index failed", e);
            Announce("Search unavailable.");
            return;
        }
        if (_entries.Count == 0)
        {
            Announce("No settings to search.");
            return;
        }
        Perf.Mark("search window opening");
        SearchEntry? picked;
        try
        {
            var dialog = new SearchWindow(Host, _entries);
            var closed = dialog.ShowDialog();
            Perf.Mark($"search window closed ({closed})");
            picked = closed == true ? dialog.Result : null;
        }
        catch (Exception e)
        {
            Log.Error("The search window failed", e);
            Announce("Search unavailable.");
            return;
        }
        if (picked != null)
            await NavigateToAsync(picked);
    }

    /// <summary>Switch to the setting's tab (and map), then focus it.</summary>
    private async Task NavigateToAsync(SearchEntry entry)
    {
        var tab = _tabs.FirstOrDefault(t => t.Name == entry.TabName);
        if (tab == null)
        {
            Announce($"Could not focus {entry.Label}");
            return;
        }
        if (_tabControl != null && tab.Item != null)
            _tabControl.SelectedItem = tab.Item;
        EnsureBuilt(tab);
        if (entry.Map != null && tab.Picker != null)
        {
            var index = tab.Maps.FindIndex(m => m.Key == entry.Map);
            if (index >= 0)
            {
                if (tab.Picker.SelectedIndex != index)
                    tab.Picker.SelectedIndex = index;
                await ShowMapAsync(tab, entry.Map);
            }
        }
        if (!_settings.TryGetValue(entry.Id, out var view))
        {
            Announce($"Could not focus {entry.Label}");
            return;
        }
        await Dispatcher.InvokeAsync(() =>
        {
            UpdateLayout();
            view.Control.Focus();
            view.Control.BringIntoView();
        }, DispatcherPriority.Input);
        Announce($"{entry.Label} on {entry.TabName} tab");
    }

    private void Announce(string message)
    {
        if (message.Length > 0)
            Announcer.Announce(Host ?? (UIElement)this, message);
    }
}
