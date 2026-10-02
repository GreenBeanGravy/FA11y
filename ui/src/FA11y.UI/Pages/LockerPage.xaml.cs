using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using WpfKey = System.Windows.Input.Key;
using System.Windows.Media;
using System.Windows.Threading;
using FA11y.UI.Core;
using FA11y.UI.Shell;

namespace FA11y.UI.Pages;

/// <summary>An entry of the category menu.</summary>
public sealed record CategoryRow(string Name)
{
    public string Display => Name;
    public string Spoken => Name;
    public override string ToString() => Name;
}

/// <summary>A saved loadout in the loadouts list.</summary>
public sealed record LoadoutRow(int Id, string Name, string BareName, bool Local, string Detail)
{
    public string Display => Name;
    public string Spoken => Name;
    public override string ToString() => Name;
}

/// <summary>
/// One row of a category list: a cosmetic, or one of the special rows (Random, Randomize Track,
/// Unequip) that come first.
/// </summary>
public sealed class CosmeticRow
{
    private static readonly Dictionary<string, Brush> Colors = new()
    {
        ["common"] = Rgb(170, 170, 170), ["uncommon"] = Rgb(96, 170, 58), ["rare"] = Rgb(73, 172, 242),
        ["epic"] = Rgb(177, 91, 226), ["legendary"] = Rgb(211, 120, 65), ["mythic"] = Rgb(255, 223, 0),
        ["marvel"] = Rgb(197, 51, 52), ["dc"] = Rgb(84, 117, 199), ["starwars"] = Rgb(231, 196, 19),
        ["icon"] = Rgb(0, 217, 217), ["gaminglegends"] = Rgb(137, 86, 255),
    };

    private static readonly Brush Plain = Rgb(232, 230, 223);

    private static Brush Rgb(byte r, byte g, byte b)
    {
        var brush = new SolidColorBrush(Color.FromRgb(r, g, b));
        brush.Freeze();
        return brush;
    }

    public string Kind { get; init; } = "cosmetic"; // cosmetic, random, randomize or unequip
    public string Id { get; init; } = "";
    public string Name { get; init; } = "";
    public string TypeText { get; init; } = "";
    public string Rarity { get; init; } = "";
    public string RarityKey { get; init; } = "";
    public double Value { get; init; }
    public string SeasonText { get; init; } = "";
    public string Chapter { get; init; } = "?";
    public string SeasonNumber { get; init; } = "?";
    public string Description { get; init; } = "";
    public bool Favorite { get; set; }
    public bool ShowType { get; init; }
    public string SpecialDetails { get; init; } = "";

    public bool IsSpecial => Kind != "cosmetic";
    public string Display => Favorite ? "⭐ " + Name : Name;
    public Brush RarityBrush => Colors.GetValueOrDefault(RarityKey) ?? Plain;

    public string Spoken
    {
        get
        {
            var parts = new List<string> { Favorite ? $"{Name}, favorite" : Name };
            if (ShowType)
                parts.Add(TypeText);
            parts.Add(Rarity);
            parts.Add(SeasonText);
            return string.Join(", ", parts);
        }
    }

    public override string ToString() => Spoken;

    /// <summary>The text under "Cosmetic Details".</summary>
    public string Details()
    {
        if (IsSpecial)
            return SpecialDetails;
        var lines = new List<string>
        {
            $"Name: {Name}",
            $"Type: {TypeText}",
            $"Rarity: {Rarity}",
            $"Season: Chapter {Chapter}, Season {SeasonNumber}",
        };
        if (Description.Length > 0)
            lines.Add($"\nDescription: {Description}");
        if (Favorite)
            lines.Add("\n⭐ FAVORITE");
        return string.Join("\n", lines);
    }
}

/// <summary>
/// The locker: pick a category, browse its cosmetics (search, favorites), equip one in Fortnite by
/// mouse automation, and work with loadouts. The core sends each category's cosmetics once as compact
/// records; searching, the favorites filter and sorting happen here, so typing is instant. Escape
/// goes back one view.
/// </summary>
public partial class LockerPage : PageBase
{
    private enum View { Main, Category, Equipped, Loadouts }

    private const string UnavailableText =
        "Couldn't load cosmetics. Check your internet connection, then open this page again.";

    private View _view = View.Main;
    private bool _loaded;
    private bool _prefetched;
    private bool _loading;
    private bool _signedIn;
    private bool _updating;
    private bool _busy;
    private int _loadVersion;
    private int _categoryVersion;
    private string _category = "";
    private bool _allCosmetics;
    private bool _hasRandom, _hasRandomize;
    private string? _unequipTerm;
    private string _randomDetails = "", _randomizeDetails = "", _unequipDetails = "";
    private List<CosmeticRow> _records = new();
    private List<CosmeticRow> _shown = new();
    private readonly DispatcherTimer _searchTimer;
    private bool _loadoutsLoading;

    public LockerPage()
    {
        InitializeComponent();
        Message.Text = "Loading cosmetics…";
        _searchTimer = new DispatcherTimer { Interval = TimeSpan.FromMilliseconds(200) };
        _searchTimer.Tick += (_, _) =>
        {
            _searchTimer.Stop();
            ApplyCategoryFilter(announce: false);
        };
        AppState.Changed += PrefetchOnce;
    }

    public override string Key => "locker";
    public override string Title => "Locker";

    private void PrefetchOnce()
    {
        if (!AppState.HelloReceived || _loaded || _loading || _prefetched)
            return;
        _prefetched = true;
        Refresh();
    }

    public override void OnShown()
    {
        if (!_loaded && !_loading)
            Refresh();
    }

    // The login status first, like the identity text on the account page.
    public override FrameworkElement? FirstFocus()
    {
        if (!_loaded)
            return Message;
        FrameworkElement target = _view switch
        {
            View.Category => CosmeticsList,
            View.Equipped => EquippedBox,
            View.Loadouts => LoadoutsList,
            _ => LoginText,
        };
        return target;
    }

    public override bool HandleEscape()
    {
        if (_view == View.Main || !_loaded)
            return false;
        if (_busy)
            return true;
        GoBack();
        return true;
    }

    /// <summary>Test builds only: open a category without keys.</summary>
    public void OpenCategoryForTest(string name) => _ = OpenCategory(name);

    private void Say(string text) => Announcer.Announce(Host ?? (UIElement)this, text);

    // Loading ----------------------------------------------------------------------------

    /// <summary>(Re)load the cosmetics and what the account owns. The core reads the database and asks Epic.</summary>
    public override async void Refresh()
    {
        var version = ++_loadVersion;
        _loading = true;
        try
        {
            var focusWasInPage = IsKeyboardFocusWithin;
            if (!_loaded)
            {
                Message.Text = "Loading cosmetics…";
            }
            var result = await App.Bridge.RequestAsync("locker.load", null, TimeSpan.FromMinutes(3));
            if (version != _loadVersion)
                return;
            var focusWasOnMessage = Message.IsKeyboardFocusWithin;
            if (!result.Bool("available"))
            {
                _loaded = false;
                Views.Visibility = Visibility.Collapsed;
                Message.Visibility = Visibility.Visible;
                Message.Text = UnavailableText;
                return;
            }

            _loaded = true;
            _signedIn = result.Bool("signed_in");
            Message.Visibility = Visibility.Collapsed;
            Views.Visibility = Visibility.Visible;
            CategoriesList.ItemsSource = result.GetProperty("categories").EnumerateArray()
                .Select(c => new CategoryRow(c.GetString() ?? "")).ToList();
            ApplySignIn(result.Str("name"), result.Bool("owned_only"));
            if (_view != View.Main)
                ShowView(View.Main);
            if (CategoriesList.SelectedIndex < 0)
                CategoriesList.SelectedIndex = 0;
            if (focusWasOnMessage || (focusWasInPage && !IsKeyboardFocusWithin))
                FirstFocus()?.Focus();
        }
        catch (Exception e)
        {
            Log.Error("locker.load failed", e);
            if (!_loaded && version == _loadVersion)
                Message.Text = UnavailableText;
        }
        finally
        {
            if (version == _loadVersion)
                _loading = false;
        }
    }

    private void ApplySignIn(string name, bool ownedOnly)
    {
        LoginText.Text = _signedIn ? $"Logged in as: {name}" : "Not logged in";
        LoginButton.Visibility = _signedIn ? Visibility.Collapsed : Visibility.Visible;
        EquippedButton.Visibility = LoadoutsButton.Visibility = SaveButton.Visibility =
            _signedIn ? Visibility.Visible : Visibility.Collapsed;
        _updating = true;
        try
        {
            OwnedCheck.IsEnabled = _signedIn;
            OwnedCheck.IsChecked = ownedOnly;
        }
        finally
        {
            _updating = false;
        }
    }

    // Views ----------------------------------------------------------------------------------

    private void ShowView(View view)
    {
        _view = view;
        MainView.Visibility = view == View.Main ? Visibility.Visible : Visibility.Collapsed;
        CategoryView.Visibility = view == View.Category ? Visibility.Visible : Visibility.Collapsed;
        EquippedView.Visibility = view == View.Equipped ? Visibility.Visible : Visibility.Collapsed;
        LoadoutsView.Visibility = view == View.Loadouts ? Visibility.Visible : Visibility.Collapsed;
        Heading.Text = view switch
        {
            View.Category => $"{_category} - Fortnite Locker",
            View.Equipped => "Currently Equipped Cosmetics",
            View.Loadouts => $"Loadouts ({LoadoutsList.Items.Count})",
            _ => "Locker",
        };
    }

    private void GoBack()
    {
        var from = _view;
        ShowView(View.Main);
        FrameworkElement target = from switch
        {
            View.Equipped => EquippedButton,
            View.Loadouts => LoadoutsButton,
            _ => CategoriesList,
        };
        _ = Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
        {
            if (from == View.Category && CategoriesList.SelectedIndex >= 0)
                FocusRow(CategoriesList, CategoriesList.SelectedIndex);
            else
                target.Focus();
        });
    }

    private void OnBackToCategories(object sender, RoutedEventArgs e) => GoBack();
    private void OnBackFromView(object sender, RoutedEventArgs e) => GoBack();

    private static void FocusRow(ListBox list, int index)
    {
        list.SelectedIndex = index;
        list.ScrollIntoView(list.SelectedItem);
        list.UpdateLayout();
        if (list.ItemContainerGenerator.ContainerFromIndex(index) is ListBoxItem item)
            item.Focus();
    }

    // The category menu ----------------------------------------------------------------------------------

    private void OnCategoriesKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == WpfKey.Enter && Keyboard.Modifiers == ModifierKeys.None && CategoriesList.SelectedItem is CategoryRow row)
        {
            e.Handled = true;
            _ = OpenCategory(row.Name);
        }
    }

    private void OnCategoriesDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (e.OriginalSource is DependencyObject source && ItemsControl.ContainerFromElement(CategoriesList, source) != null
            && CategoriesList.SelectedItem is CategoryRow row)
            _ = OpenCategory(row.Name);
    }

    private async Task OpenCategory(string name)
    {
        if (_busy)
            return;
        var version = ++_categoryVersion;
        Say($"Opening {name} category");
        try
        {
            var result = await App.Bridge.RequestAsync("locker.category", new { name }, TimeSpan.FromSeconds(60));
            if (version != _categoryVersion)
                return;
            _category = name;
            _allCosmetics = name == "All Cosmetics";
            var options = result.GetProperty("options");
            _hasRandom = options.Bool("random");
            _hasRandomize = options.Bool("randomize");
            _unequipTerm = options.NullableStr("unequip");
            var special = result.GetProperty("special");
            _randomDetails = special.Str("random");
            _randomizeDetails = special.Str("randomize");
            _unequipDetails = special.Str("unequip");
            _records = result.GetProperty("records").EnumerateArray().Select(ToRow).ToList();

            CosmeticsList.ItemTemplate = (DataTemplate)Resources[_allCosmetics ? "AllRow" : "CategoryRow"];
            TypeHeaderColumn.Width = _allCosmetics ? new GridLength(130) : new GridLength(0);
            _updating = true;
            FavoritesOnlyCheck.IsChecked = false;
            SortFavoritesCheck.IsChecked = false;
            CategorySearch.Text = "";
            _updating = false;
            ShowView(View.Category);
            ApplyCategoryFilter(announce: false);
            _ = Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
            {
                if (CosmeticsList.Items.Count > 0)
                    FocusRow(CosmeticsList, 0);
                else
                    CategorySearch.Focus();
            });
        }
        catch (Exception e)
        {
            Log.Error("locker.category failed", e);
            Say("Error opening category");
            Prompts.Message(Host, "Error", $"Error: {e.Message}");
        }
    }

    private CosmeticRow ToRow(JsonElement r) => new()
    {
        Id = r.Str("i"),
        Name = r.Str("n", "Unknown"),
        TypeText = r.Str("t"),
        Rarity = r.Str("r"),
        RarityKey = r.Str("k"),
        Value = r.TryGetProperty("v", out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : 0,
        SeasonText = r.Str("s"),
        Chapter = AsText(r, "c"),
        SeasonNumber = AsText(r, "e"),
        Description = r.Str("d"),
        Favorite = r.Bool("f"),
        ShowType = _allCosmetics,
    };

    private static string AsText(JsonElement e, string name) =>
        e.TryGetProperty(name, out var v) ? (v.ValueKind == JsonValueKind.String ? v.GetString() ?? "?" : v.ToString()) : "?";

    // One category ------------------------------------------------------------------------------------------------

    private void OnCategoryFilterChanged(object sender, RoutedEventArgs e)
    {
        if (_updating || !IsLoaded)
            return;
        if (ReferenceEquals(sender, FavoritesOnlyCheck))
            Say(FavoritesOnlyCheck.IsChecked == true ? "Filtering to favorites only" : "Showing all cosmetics");
        else
            Say(SortFavoritesCheck.IsChecked == true ? "Sorting favorites first" : "Default sorting");
        ApplyCategoryFilter(announce: false);
    }

    private void OnCategorySearchChanged(object sender, TextChangedEventArgs e)
    {
        if (_updating || !IsLoaded)
            return;
        _searchTimer.Stop();
        _searchTimer.Start();
    }

    private void OnClearCategorySearch(object sender, RoutedEventArgs e)
    {
        CategorySearch.Text = "";
        CategorySearch.Focus();
    }

    /// <summary>Filter, sort and show the category's cosmetics (the same rules as the wx list).</summary>
    private void ApplyCategoryFilter(bool announce, string? keepId = null)
    {
        var favoritesOnly = FavoritesOnlyCheck.IsChecked == true;
        var favoritesFirst = SortFavoritesCheck.IsChecked == true;
        var search = CategorySearch.Text;

        IEnumerable<CosmeticRow> rows = _records;
        if (favoritesOnly)
            rows = rows.Where(r => r.Favorite);
        if (search.Length > 0)
        {
            var needle = search.ToLowerInvariant();
            rows = rows.Where(r => r.Name.ToLowerInvariant().Contains(needle)
                                   || r.Description.ToLowerInvariant().Contains(needle)
                                   || r.RarityKey.Contains(needle));
        }
        var cosmetics = rows.ToList();
        if (favoritesFirst)
            cosmetics = cosmetics.OrderBy(r => !r.Favorite).ThenByDescending(r => r.Value)
                .ThenBy(r => r.Name, StringComparer.Ordinal).ToList();
        _shown = cosmetics;

        var list = new List<CosmeticRow>();
        if (_hasRandom)
            list.Add(Special("random", "Random", _randomDetails));
        if (_hasRandomize)
            list.Add(Special("randomize", "Randomize Track", _randomizeDetails));
        if (_unequipTerm != null)
            list.Add(Special("unequip", $"Unequip ({_unequipTerm})", _unequipDetails));
        list.AddRange(cosmetics);

        var filterText = favoritesOnly ? " (favorites only)" : favoritesFirst ? " (favorites first)" : "";
        ResultsText.Text = search.Length > 0
            ? $"Showing {cosmetics.Count} {_category} cosmetics matching '{search}'{filterText}"
            : $"Showing {cosmetics.Count} {_category} cosmetics{filterText}";

        var hadFocus = CosmeticsList.IsKeyboardFocusWithin;
        CosmeticsList.ItemsSource = list;
        var index = keepId == null ? -1 : list.FindIndex(r => r.Id == keepId);
        if (index < 0 && list.Count > 0)
            index = 0;
        CosmeticsList.SelectedIndex = index;
        if (index >= 0)
            CosmeticsList.ScrollIntoView(list[index]);
        if (hadFocus && index >= 0)
            FocusRow(CosmeticsList, index);
        if (index < 0)
            DetailsBox.Text = "";
    }

    private CosmeticRow Special(string kind, string name, string details) => new()
    {
        Kind = kind,
        Name = name,
        TypeText = "-",
        Rarity = "Special",
        SeasonText = "-",
        ShowType = _allCosmetics,
        SpecialDetails = details,
    };

    private void OnCosmeticSelected(object sender, SelectionChangedEventArgs e)
    {
        DetailsBox.Text = (CosmeticsList.SelectedItem as CosmeticRow)?.Details() ?? "";
    }

    private void OnCosmeticsKeyDown(object sender, KeyEventArgs e)
    {
        if (Keyboard.Modifiers != ModifierKeys.None)
            return;
        if (e.Key == WpfKey.Enter)
        {
            e.Handled = true;
            _ = EquipSelected();
        }
        else if (e.Key == WpfKey.F)
        {
            e.Handled = true;
            _ = ToggleFavorite();
        }
    }

    private void OnCosmeticsDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (e.OriginalSource is DependencyObject source && ItemsControl.ContainerFromElement(CosmeticsList, source) != null)
            _ = EquipSelected();
    }

    private async Task ToggleFavorite()
    {
        if (_busy)
            return;
        if (CosmeticsList.SelectedItem is not CosmeticRow row)
        {
            Say("No cosmetic selected");
            return;
        }
        if (row.IsSpecial)
        {
            Say("Cannot favorite special options");
            return;
        }
        _busy = true;
        try
        {
            var result = await App.Bridge.RequestAsync("locker.toggle_favorite", new { id = row.Id }, TimeSpan.FromSeconds(90));
            switch (result.Str("result"))
            {
                case "ok":
                    row.Favorite = result.Bool("favorite");
                    ApplyCategoryFilter(announce: false, keepId: row.Id);
                    break;
                case "login":
                    Prompts.Message(Host, "Login Required", "You must be logged in to use the favorites feature.");
                    break;
                case "failed":
                    Prompts.Message(Host, "Failed", "Failed to update favorite status via API. Check logs for details.");
                    break;
                case "error":
                    Prompts.Message(Host, "Error", "Error toggling favorite.");
                    break;
            }
        }
        catch (Exception e)
        {
            Log.Error("locker.toggle_favorite failed", e);
        }
        finally
        {
            _busy = false;
        }
    }

    // Equipping ------------------------------------------------------------------------------------------------------

    private void OnEquip(object sender, RoutedEventArgs e) => _ = EquipSelected();

    private async Task EquipSelected()
    {
        if (_busy)
            return;
        if (CosmeticsList.SelectedItem is not CosmeticRow row)
        {
            Say("No item selected");
            Prompts.Message(Host, "No Selection", "Please select an item to equip");
            return;
        }
        _busy = true;
        try
        {
            var plan = await App.Bridge.RequestAsync("locker.equip_plan", new
            {
                kind = row.Kind,
                category = _category,
                id = row.Id,
                ids = row.Kind == "randomize" ? _shown.Select(r => r.Id).ToArray() : null,
            }, TimeSpan.FromSeconds(30));
            var error = plan.Str("error");
            if (error.Length > 0)
            {
                Prompts.Message(Host, row.Kind == "randomize" ? "Cannot Randomize" : "Cannot Equip", error);
                return;
            }

            int? slot = plan.TryGetProperty("slot", out var s) && s.ValueKind == JsonValueKind.Number ? s.GetInt32() : null;
            if (plan.TryGetProperty("ask", out var ask))
            {
                var choices = ask.GetProperty("choices").EnumerateArray().Select(c => c.GetString() ?? "").ToList();
                var index = Prompts.Choose(Host, ask.Str("title"), ask.Str("message"), choices);
                if (index < 0)
                    return;
                slot = index + 1;
            }

            var result = await RunInGame("locker.equip", new
            {
                kind = plan.Str("kind"),
                category = _category,
                id = plan.NullableStr("id") ?? "",
                slot,
            });
            if (result is not { } done)
                return;
            if (!done.Bool("ok"))
                Prompts.Message(Host, "Equip Failed", done.Str("message", "Failed to equip cosmetic."));
        }
        catch (Exception e)
        {
            Log.Error("equipping failed", e);
            Prompts.Message(Host, "Error", $"Error: {e.Message}");
        }
        finally
        {
            _busy = false;
            _ = Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
            {
                if (_view == View.Category && CosmeticsList.SelectedIndex >= 0)
                    FocusRow(CosmeticsList, CosmeticsList.SelectedIndex);
            });
        }
    }

    /// <summary>
    /// Run something that clicks around in Fortnite. This window gets out of the way first (the core
    /// brings Fortnite forward) and comes back when it is done, like the wx window did.
    /// </summary>
    private async Task<JsonElement?> RunInGame(string method, object parameters)
    {
        var host = Host;
        if (host != null)
            host.WindowState = WindowState.Minimized;
        await Task.Delay(100);
        try
        {
            return await App.Bridge.RequestAsync(method, parameters, Timeout.InfiniteTimeSpan);
        }
        catch (Exception e)
        {
            Log.Error($"{method} failed", e);
            throw;
        }
        finally
        {
            if (host != null)
                WindowTools.BringToFront(host);
        }
    }

    // Login and the owned filter ---------------------------------------------------------------------------------------------

    private async void OnLogin(object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;
        _busy = true;
        try
        {
            var result = await App.Bridge.RequestAsync("account.sign_in", null, Timeout.InfiniteTimeSpan);
            if (Host is { } host && WindowTools.ForegroundIsFa11y(App.CoreProcessId))
                WindowTools.BringToFront(host);
            if (result.Bool("authenticated"))
                Say($"Logged in as {result.Str("name")}");
        }
        catch (Exception ex)
        {
            Log.Error("account.sign_in failed", ex);
            Say("Error during login");
        }
        finally
        {
            _busy = false;
        }
    }

    private async void OnOwnedChanged(object sender, RoutedEventArgs e)
    {
        if (_updating || !IsLoaded || _busy)
            return;
        _busy = true;
        var loginAgain = false;
        try
        {
            var result = await App.Bridge.RequestAsync("locker.set_owned_only",
                new { value = OwnedCheck.IsChecked == true }, TimeSpan.FromSeconds(90));
            var messages = result.GetProperty("messages").EnumerateArray().Select(m => m.GetString() ?? "");
            Say(string.Join(". ", messages));
            _updating = true;
            OwnedCheck.IsChecked = result.Bool("owned_only");
            _updating = false;

            if (result.Bool("expired"))
            {
                loginAgain = Dialogs.Confirm(Host, "Login Expired",
                    "Your Epic Games login has expired.\n\nWould you like to log in again?");
            }
            else if (result.NullableStr("error") is { } error)
            {
                Prompts.Message(Host, "Error", error);
            }
        }
        catch (Exception ex)
        {
            Log.Error("locker.set_owned_only failed", ex);
            Say("Error toggling owned filter");
            _updating = true;
            OwnedCheck.IsChecked = !(OwnedCheck.IsChecked == true);
            _updating = false;
        }
        finally
        {
            _busy = false;
        }
        if (loginAgain)
            OnLogin(this, new RoutedEventArgs());
    }

    // Passes ---------------------------------------------------------------------------------------------------------------------

    private async void OnPasses(object sender, RoutedEventArgs e)
    {
        try
        {
            await App.Bridge.RequestAsync("locker.open_passes", null, Timeout.InfiniteTimeSpan);
            if (Host is { } host && WindowTools.ForegroundIsFa11y(App.CoreProcessId))
                WindowTools.BringToFront(host);
        }
        catch (Exception ex)
        {
            Log.Error("locker.open_passes failed", ex);
        }
    }

    // Equipped --------------------------------------------------------------------------------------------------------------------

    private async void OnViewEquipped(object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;
        _busy = true;
        try
        {
            Say("Fetching equipped cosmetics");
            var result = await App.Bridge.RequestAsync("locker.equipped", null, TimeSpan.FromSeconds(90));
            if (result.Bool("login"))
            {
                Say("Please log in first");
                return;
            }
            var text = result.NullableStr("text");
            if (text == null)
            {
                Say("Failed to fetch equipped cosmetics");
                Prompts.Message(Host, "Error", "Could not retrieve equipped cosmetics from Epic Games.");
                return;
            }
            Say("Equipped cosmetics loaded");
            EquippedBox.Text = text;
            ShowView(View.Equipped);
            _ = Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
            {
                EquippedBox.Focus();
                EquippedBox.CaretIndex = 0;
            });
        }
        catch (Exception ex)
        {
            Log.Error("locker.equipped failed", ex);
            Say("Error viewing equipped cosmetics");
            Prompts.Message(Host, "Error", $"Error: {ex.Message}");
        }
        finally
        {
            _busy = false;
        }
    }

    // Loadouts ------------------------------------------------------------------------------------------------------------------------

    private async void OnViewLoadouts(object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;
        _busy = true;
        try
        {
            Say("Fetching saved loadouts");
            var result = await App.Bridge.RequestAsync("locker.loadouts", new { fetch = true, filter = "All" },
                TimeSpan.FromSeconds(90));
            switch (result.Str("status"))
            {
                case "login":
                    Say("Please log in first");
                    return;
                case "failed":
                    Say("Failed to fetch loadouts");
                    Prompts.Message(Host, "Error", "Could not retrieve loadout presets from Epic Games.");
                    return;
                case "none":
                    Say("No saved loadouts found");
                    Prompts.Message(Host, "Loadouts", "You have no saved loadout presets.");
                    return;
            }
            Say($"Found {result.GetProperty("total").GetInt32()} loadouts");
            _loadoutsLoading = true;
            LoadoutFilter.ItemsSource = result.GetProperty("filters").EnumerateArray().Select(f => f.GetString() ?? "").ToList();
            LoadoutFilter.SelectedIndex = 0;
            _loadoutsLoading = false;
            ShowLoadouts(result);
            ShowView(View.Loadouts);
            _ = Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
            {
                if (LoadoutsList.Items.Count > 0)
                    FocusRow(LoadoutsList, 0);
                else
                    LoadoutFilter.Focus();
            });
        }
        catch (Exception ex)
        {
            Log.Error("locker.loadouts failed", ex);
            Say("Error viewing loadouts");
            Prompts.Message(Host, "Error", $"Error: {ex.Message}");
        }
        finally
        {
            _busy = false;
        }
    }

    private void ShowLoadouts(JsonElement result)
    {
        var rows = result.GetProperty("records").EnumerateArray()
            .Select(r => new LoadoutRow(r.GetProperty("id").GetInt32(), r.Str("label"), r.Str("name"), r.Bool("local"),
                r.Str("detail")))
            .ToList();
        LoadoutsList.ItemsSource = rows;
        LoadoutsList.SelectedIndex = rows.Count > 0 ? 0 : -1;
        LoadoutDetails.Text = rows.Count > 0 ? rows[0].Detail : "";
        Heading.Text = $"Loadouts ({result.GetProperty("total").GetInt32()})";
    }

    private async void OnLoadoutFilterChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_loadoutsLoading || LoadoutFilter.SelectedItem is not string filter)
            return;
        try
        {
            var result = await App.Bridge.RequestAsync("locker.loadouts", new { fetch = false, filter }, TimeSpan.FromSeconds(30));
            if (result.Str("status") != "ok")
                return;
            ShowLoadouts(result);
            Say($"Showing {LoadoutsList.Items.Count} loadouts");
        }
        catch (Exception ex)
        {
            Log.Error("locker.loadouts failed", ex);
        }
    }

    private void OnLoadoutSelected(object sender, SelectionChangedEventArgs e)
    {
        LoadoutDetails.Text = (LoadoutsList.SelectedItem as LoadoutRow)?.Detail ?? "";
    }

    private LoadoutRow? SelectedLoadout()
    {
        if (LoadoutsList.SelectedItem is LoadoutRow row)
            return row;
        Say("No loadout selected");
        return null;
    }

    private async void OnLoadoutApi(object sender, RoutedEventArgs e)
    {
        if (_busy || SelectedLoadout() is not { } row)
            return;
        _busy = true;
        try
        {
            var prompt = await App.Bridge.RequestAsync("locker.loadout_api_prompt", new { id = row.Id });
            if (!Dialogs.Confirm(Host, "Equip via API", prompt.Str("prompt")))
                return;
            var result = await App.Bridge.RequestAsync("locker.loadout_equip_api", new { id = row.Id }, TimeSpan.FromSeconds(90));
            if (!result.Bool("ok"))
                Prompts.Message(Host, "Error", $"Failed to equip '{result.Str("name")}' via API.");
        }
        catch (Exception ex)
        {
            Log.Error("locker.loadout_equip_api failed", ex);
        }
        finally
        {
            _busy = false;
        }
    }

    private async void OnLoadoutGame(object sender, RoutedEventArgs e)
    {
        if (_busy || SelectedLoadout() is not { } row)
            return;
        _busy = true;
        try
        {
            var plan = await App.Bridge.RequestAsync("locker.loadout_ui_plan", new { id = row.Id });
            if (plan.GetProperty("count").GetInt32() == 0)
            {
                Say("No equippable items in this loadout");
                return;
            }
            if (!Dialogs.Confirm(Host, "Equip in Game", plan.Str("prompt")))
                return;
            await RunInGame("locker.loadout_equip_ui", new { id = row.Id });
        }
        catch (Exception ex)
        {
            Log.Error("locker.loadout_equip_ui failed", ex);
        }
        finally
        {
            _busy = false;
        }
    }

    private async void OnLoadoutDelete(object sender, RoutedEventArgs e)
    {
        if (_busy || SelectedLoadout() is not { } row)
            return;
        _busy = true;
        try
        {
            if (row.Local && !Dialogs.Confirm(Host, "Delete Loadout", $"Delete local loadout '{row.BareName}'?"))
                return;
            var result = await App.Bridge.RequestAsync("locker.loadout_delete", new { id = row.Id });
            var message = result.Str("message");
            if (message.Length > 0)
            {
                Say("Can only delete locally saved loadouts");
                Prompts.Message(Host, "Cannot Delete", message);
                return;
            }
            if (!result.Bool("ok"))
                return;
            var filter = LoadoutFilter.SelectedItem as string ?? "All";
            var list = await App.Bridge.RequestAsync("locker.loadouts", new { fetch = false, filter });
            if (list.Str("status") == "ok")
                ShowLoadouts(list);
            else
                GoBack();
        }
        catch (Exception ex)
        {
            Log.Error("locker.loadout_delete failed", ex);
        }
        finally
        {
            _busy = false;
        }
    }

    // Saving a loadout ---------------------------------------------------------------------------------------------------------------------

    private async void OnSaveLoadout(object sender, RoutedEventArgs e)
    {
        if (_busy)
            return;
        _busy = true;
        try
        {
            var choices = await App.Bridge.RequestAsync("locker.save_choices");
            if (choices.Bool("login"))
            {
                Say("Please log in first");
                return;
            }
            var names = choices.GetProperty("choices").EnumerateArray().Select(c => c.GetString() ?? "").ToList();
            var index = Prompts.Choose(Host, "Save Loadout",
                "Which loadout type do you want to save?\n\nSelect 'All Categories' to save everything at once.", names);
            if (index < 0)
                return;
            var name = Prompts.Ask(Host, "Loadout Name", "Enter a name for this loadout:", $"My {names[index]} Loadout");
            if (name == null)
                return;
            name = name.Trim();
            if (name.Length == 0)
            {
                Say("No name entered, cancelled");
                return;
            }

            var result = await App.Bridge.RequestAsync("locker.save_loadout", new { choice = index, name }, TimeSpan.FromSeconds(90));
            if (result.Bool("exists"))
            {
                if (!Dialogs.Confirm(Host, "Loadout Exists",
                        $"A loadout named '{name}' already exists.\n\nDo you want to overwrite it?"))
                {
                    Say("Cancelled. Choose a different name.");
                    return;
                }
                result = await App.Bridge.RequestAsync("locker.save_loadout",
                    new { choice = index, name, overwrite = true }, TimeSpan.FromSeconds(90));
            }
            if (result.Bool("ok"))
                Prompts.Message(Host, "Loadout Saved", result.Str("message"));
        }
        catch (Exception ex)
        {
            Log.Error("locker.save_loadout failed", ex);
            Say("Error saving loadout");
            Prompts.Message(Host, "Error", $"Error: {ex.Message}");
        }
        finally
        {
            _busy = false;
            SaveButton.Focus();
        }
    }
}
