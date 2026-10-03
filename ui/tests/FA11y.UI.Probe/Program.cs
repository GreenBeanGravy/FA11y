using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.RegularExpressions;
using System.Windows.Automation;

namespace FA11y.UI.Probe;

/// <summary>
/// Walks the FA11y window the way a screen reader does, through UI Automation, and checks the rules
/// the window has to keep:
///   * arrowing through the sidebar changes the page and leaves focus on the sidebar item;
///   * every focusable element on every page has a name, and read-only text and cards read in full;
///   * keys: Enter and Tab go into the page, F6, Ctrl+Tab, Escape.
/// It starts the window through ui/tests/fake_core.py and types real keys, so don't touch the
/// keyboard while it runs. Exit code 0 when everything passed.
///
///   FA11y.UI.Probe --python PATH_TO_PYTHON [--fake-core PATH] [--root DIR] [--static | --no-keys]
///   FA11y.UI.Probe --python PATH --tree social,locker [--shots DIR]
///
/// With --tree it types nothing and needs no foreground rights: it shows each listed page (and the
/// extra views the page-specific checks open) and checks what a screen reader would find there.
/// </summary>
internal static partial class Program
{
    private static int _failures;
    private static readonly List<string> Report = new();
    private static AutomationElement _window = null!;
    private static AutomationElement _pagesList = null!;
    private static string _root = "";
    private static bool _synthetic;
    private static Process _core = null!;
    private static int _uiPid;

    // False with --static: no keys are typed (for a session with no foreground window), and focus
    // behavior is left unchecked. Tab order is taken from the tree instead.
    private static bool _keys = true;

    private static readonly (string Key, string Title, string Group)[] Pages =
    {
        ("home", "Home", ""),
        ("fortnite", "Fortnite", "Play"),
        ("discover", "Discover", "Play"),
        ("account", "Epic account", "Account"),
        ("locker", "Locker", "Account"),
        ("social", "Social", "Account"),
        ("quests", "Quests and passes", "Account"),
        ("settings", "Settings", "FA11y"),
        ("keybinds", "Keybinds", "FA11y"),
        ("about", "About and updates", "FA11y"),
    };

    private static int Main(string[] args)
    {
        string python = "python";
        string? fakeCore = null;
        var noKeys = args.Contains("--no-keys");
        string[]? treeKeys = null;
        string? shotsDir = null;
        string root = Path.Combine(Path.GetTempPath(), "fa11y-probe-root");
        for (var i = 0; i < args.Length - 1; i++)
        {
            if (args[i] == "--tree") treeKeys = args[i + 1].Split(',');
            if (args[i] == "--shots") shotsDir = args[i + 1];
            if (args[i] == "--python") python = args[i + 1];
            if (args[i] == "--fake-core") fakeCore = args[i + 1];
            if (args[i] == "--root") root = args[i + 1];
        }
        _keys = !args.Contains("--static");
        fakeCore ??= FindFakeCore();
        _root = root;
        Directory.CreateDirectory(root);

        var core = new Process
        {
            StartInfo = new ProcessStartInfo(python, $"\"{fakeCore}\" --root \"{root}\" --log \"{Path.Combine(root, "fake-core.log")}\"")
            {
                RedirectStandardInput = true,
                RedirectStandardOutput = true,
                UseShellExecute = false,
                CreateNoWindow = true,
            },
        };
        core.Start();
        var lines = new System.Collections.Concurrent.BlockingCollection<string>();
        new Thread(() =>
        {
            string? line;
            while ((line = core.StandardOutput.ReadLine()) != null)
                lines.Add(line);
        }) { IsBackground = true }.Start();

        int uiPid;
        try
        {
            if (!lines.TryTake(out var started, 15000) || !started.StartsWith("STARTED "))
                return Fail("The test core did not start the window.");
            uiPid = int.Parse(started.Split(' ')[1]);
            _uiPid = uiPid;

            var startSw = Stopwatch.StartNew();
            AutomationElement? window = null;
            while (startSw.ElapsedMilliseconds < 15000 && window == null)
            {
                window = FindWindow(uiPid);
                if (window != null && window.Current.IsOffscreen)
                    window = null;
                if (window == null)
                    Thread.Sleep(5);
            }
            if (window == null)
                return Fail("The window never appeared.");
            _window = window;
            var ui = Process.GetProcessById(uiPid);
            var sinceProcessStart = (DateTime.Now - ui.StartTime).TotalMilliseconds;
            Info($"Startup: window visible {sinceProcessStart:F0} ms after the UI process started "
                 + $"({startSw.ElapsedMilliseconds} ms after the core reported it started)");

            if (!lines.TryTake(out var ready, 15000) || !ready.StartsWith("READY "))
                Check(false, "ui.ready arrived");
            Thread.Sleep(1200); // let the pages fill in, as a user would wait

            if (treeKeys != null)
                RunTree(core, treeKeys, shotsDir);
            else if (noKeys)
                StaticRun(core);
            else if (_keys)
                Run(core, uiPid);
            else
                RunStatic(core);

            ui.Refresh();
            Info($"UI process working set: {ui.WorkingSet64 / (1024 * 1024)} MB, private {ui.PrivateMemorySize64 / (1024 * 1024)} MB");
        }
        catch (Exception e)
        {
            Check(false, $"probe crashed: {e}");
        }
        finally
        {
            try { core.StandardInput.WriteLine("quit"); } catch { /* already gone */ }
            if (!core.WaitForExit(5000))
                core.Kill(true);
        }

        if (treeKeys == null && !noKeys && !_synthetic) // setup needs real keys; --static covers it otherwise
        try
        {
            RunSetupSession(python, fakeCore, root);
        }
        catch (Exception e)
        {
            Check(false, $"setup probe crashed: {e}");
        }

        Console.WriteLine();
        Console.WriteLine(_failures == 0 ? "PROBE PASSED" : $"PROBE FAILED: {_failures} problem(s)");
        return _failures == 0 ? 0 : 1;
    }

    private static string FindFakeCore()
    {
        var dir = AppContext.BaseDirectory;
        while (dir != null && !File.Exists(Path.Combine(dir, "tests", "fake_core.py")))
            dir = Path.GetDirectoryName(dir);
        if (dir == null)
            throw new FileNotFoundException("fake_core.py not found; pass --fake-core.");
        return Path.Combine(dir, "tests", "fake_core.py");
    }

    private static void Run(Process core, int uiPid)
    {
        Console.WriteLine("\n== Sidebar structure");
        _pagesList = _window.FindFirst(TreeScope.Descendants, new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.List),
            new PropertyCondition(AutomationElement.NameProperty, "Pages")))!;
        if (!Check(_pagesList != null, "a list named \"Pages\" exists"))
            return;
        var items = Items();
        Check(items.Count == Pages.Length, $"the sidebar has {Pages.Length} items (found {items.Count})");
        for (var i = 0; i < Math.Min(items.Count, Pages.Length); i++)
        {
            var name = items[i].Current.Name;
            var help = items[i].Current.HelpText;
            Check(name == Pages[i].Title, $"item {i + 1} is named \"{Pages[i].Title}\" (got \"{name}\")");
            Check(help == Pages[i].Group, $"item \"{name}\" is described as \"{Pages[i].Group}\" (got \"{help}\")");
        }
        Check(_window.Current.Name == "FA11y - Home", $"window title is \"FA11y - Home\" (got \"{_window.Current.Name}\")");
        Check(!_window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.NameProperty, "FA11y"))
                .Cast<AutomationElement>().Any(),
            "the brand text and logo are hidden from screen readers");

        Console.WriteLine("\n== Foreground and focus at startup");
        var startedInFront = Foreground() == Handle(_window);
        Info(startedInFront ? "The window came up in front by itself."
                            : "The window did not start in front (this probe has no foreground rights); asking it to summon itself.");
        if (!startedInFront)
        {
            core.StandardInput.WriteLine("summon");
            WaitFor(() => Foreground() == Handle(_window), 3000);
            Thread.Sleep(300);
        }
        _core = core;
        _synthetic = Foreground() != Handle(_window);
        if (_synthetic)
        {
            Info("Windows won't give this window the foreground (nothing has had real input for a long time), so keys can't be typed.");
            Info("Pages are shown by the test core, every focusable element is read from the tree, and keys are sent to the focused");
            Info("control through the test core. Tab order, arrow navigation between tabs, Ctrl+Tab and F6 are NOT checked in this run.");
            RunWithoutForeground();
            return;
        }
        Check(Foreground() == Handle(_window), "the window is the foreground window");
        var focused = AutomationElement.FocusedElement;
        Check(InSidebar(focused) && focused.Current.Name == "Home", $"focus starts on the sidebar item Home (is \"{Safe(focused)}\")");

        Console.WriteLine("\n== Arrowing through the sidebar");
        var times = new List<double>();
        for (var i = 1; i < Pages.Length; i++)
        {
            var sw = Stopwatch.StartNew();
            Key(Vk.Down);
            var changed = WaitFor(() => _window.Current.Name == $"FA11y - {Pages[i].Title}", 2000);
            var elapsed = sw.Elapsed.TotalMilliseconds;
            times.Add(elapsed);
            focused = AutomationElement.FocusedElement;
            Check(changed, $"Down arrow shows the page {Pages[i].Title} ({elapsed:F0} ms)");
            Check(InSidebar(focused) && focused.Current.Name == Pages[i].Title,
                $"focus stays on the sidebar item {Pages[i].Title} (is \"{Safe(focused)}\")");
            Check(PageContentIsFor(Pages[i].Key), $"only {Pages[i].Title}'s content is in the accessibility tree");
        }
        Info($"Page switch (key press to new title, includes UI Automation round trips): "
             + $"avg {times.Average():F0} ms, max {times.Max():F0} ms");
        Key(Vk.Home);
        Check(WaitFor(() => _window.Current.Name == "FA11y - Home", 2000), "Home key goes to the first page");
        Key(Vk.End);
        Check(WaitFor(() => _window.Current.Name == "FA11y - About and updates", 2000), "End key goes to the last page");
        TypeLetter('L');
        Check(WaitFor(() => _window.Current.Name == "FA11y - Locker", 2000), "typing L goes to Locker");
        Key(Vk.Home);
        WaitFor(() => _window.Current.Name == "FA11y - Home", 2000);

        Console.WriteLine("\n== Ctrl+Tab and F6");
        KeyWith(Vk.Tab, Vk.Control);
        Check(WaitFor(() => _window.Current.Name == "FA11y - Fortnite", 2000) && InSidebar(AutomationElement.FocusedElement),
            "Ctrl+Tab goes to the next page and keeps focus on the sidebar");
        KeyWith(Vk.Tab, Vk.Control, Vk.Shift);
        Check(WaitFor(() => _window.Current.Name == "FA11y - Home", 2000) && InSidebar(AutomationElement.FocusedElement),
            "Ctrl+Shift+Tab goes back");
        Key(Vk.F6);
        Thread.Sleep(150);
        Check(!InSidebar(AutomationElement.FocusedElement), "F6 moves focus into the page");
        Key(Vk.F6);
        Thread.Sleep(150);
        Check(InSidebar(AutomationElement.FocusedElement), "F6 again moves focus back to the sidebar");

        Console.WriteLine("\n== Tabbing through each page");
        for (var i = 0; i < Pages.Length; i++)
        {
            WalkPage(i);
            if (i < Pages.Length - 1)
                Key(Vk.Down);
            WaitFor(() => i == Pages.Length - 1 || _window.Current.Name == $"FA11y - {Pages[i + 1].Title}", 2000);
        }

        RunFortnite();
        Console.WriteLine("\n== Settings and Keybinds editor");
        EditorChecks();

        Console.WriteLine("\n== Escape and the tray");
        if (!InSidebar(AutomationElement.FocusedElement))
            Key(Vk.F6);
        Key(Vk.Home);
        WaitFor(() => _window.Current.Name == "FA11y - Home", 2000);
        Key(Vk.Escape);
        Check(WaitFor(() => !IsVisible(uiPid), 2000), "Escape on the sidebar hides the window");
        core.StandardInput.WriteLine("summon");
        Check(WaitFor(() => IsVisible(uiPid), 3000), "summon shows the window again");
        Thread.Sleep(400);
        Check(Foreground() == Handle(_window), "the summoned window is in front");
        var f = AutomationElement.FocusedElement;
        Check(InSidebar(f), $"summon puts focus on the sidebar (is \"{Safe(f)}\")");
    }

    // Without the keyboard (--no-keys) ---------------------------------------------------------
    // For machines where the probe can't get the foreground. The core shows each page, then the
    // probe reads the accessibility tree: every keyboard-focusable element, in tree order, must
    // have a name and a real role, and the pages with tabs are checked tab by tab.

    private static readonly Dictionary<string, string[]> StaticExpectations = new()
    {
        ["discover"] = new[]
        {
            "Epic gamemodes", "Epic Games - Official Gamemodes", "Zone Wars (2210 playing)", "Copy code", "Launch gamemode",
            "Refresh", "Browse", "Search", "By creator", "By code",
        },
        ["quests"] = new[]
        {
            "Quests", "Battle Royale Pass", "Game mode", "Quest category", "Search quests", "Quest status", "Include expired quests",
            "Quests", "Quest details", "Refresh", "Close",
        },
    };

    private static void StaticRun(Process core)
    {
        Console.WriteLine("\n== Pages without the keyboard");
        _pagesList = _window.FindFirst(TreeScope.Descendants, new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.List),
            new PropertyCondition(AutomationElement.NameProperty, "Pages")))!;
        foreach (var key in new[] { "discover", "quests" })
        {
            var title = Pages.First(p => p.Key == key).Title;
            core.StandardInput.WriteLine($"show-page {key}");
            if (!Check(WaitFor(() => _window.Current.Name == $"FA11y - {title}", 3000), $"{title} is shown"))
                continue;
            Thread.Sleep(1500); // data arrives
            Console.WriteLine($"\n-- {title}");
            var seen = new HashSet<string>();
            DumpFocusable(seen);
            var tabs = _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.TabItem))
                .Cast<AutomationElement>().ToList();
            Check(tabs.Count > 0, $"{title} has tabs");
            foreach (var tab in tabs)
            {
                var name = tab.Current.Name;
                Console.WriteLine($"   [tab] {name}");
                Check(name.Trim().Length > 0, "a tab has a name");
                if (tab.TryGetCurrentPattern(SelectionItemPattern.Pattern, out var pattern))
                {
                    ((SelectionItemPattern)pattern).Select();
                    Thread.Sleep(900);
                    DumpFocusable(seen);
                }
            }
            foreach (var expected in StaticExpectations[key])
                Check(seen.Contains(expected) || tabs.Any(t => t.Current.Name == expected), $"\"{expected}\" is reachable on {title}");
        }
    }

    private static void DumpFocusable(HashSet<string> seen)
    {
        var elements = _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.IsKeyboardFocusableProperty, true))
            .Cast<AutomationElement>().ToList();
        foreach (var el in elements)
        {
            var c = el.Current;
            if (c.IsOffscreen)
                continue;
            if (!seen.Add(c.Name) && c.ControlType != ControlType.ListItem)
                continue;
            if (c.ControlType == ControlType.ListItem && InSidebar(el))
                continue;
            Console.WriteLine($"   {Short(c.ControlType),-9} \"{Clip(c.Name)}\"" + (c.HelpText.Length > 0 ? $"  [help: {Clip(c.HelpText)}]" : "")
                              + (c.AccessKey.Length > 0 ? $"  [key: {c.AccessKey}]" : ""));
            Check(c.Name.Trim().Length > 0, $"focusable {Short(c.ControlType)} has a name");
            Check(c.ControlType != ControlType.Pane && c.ControlType != ControlType.Custom && c.ControlType != ControlType.Group,
                $"\"{Clip(c.Name)}\" has a real role (is {Short(c.ControlType)})");
        }
        var stray = _window.FindAll(TreeScope.Descendants, Automation.ControlViewCondition).Cast<AutomationElement>()
            .Where(e => { try { return e.Current.Name.Contains('_') || (e.Current.ControlType == ControlType.Button && e.FindFirst(TreeScope.Children, Condition.TrueCondition) != null); } catch { return false; } })
            .Select(e => e.Current.Name).ToList();
        Check(stray.Count == 0, $"no access key underscores or label fragments inside controls ({string.Join(", ", stray)})");
    }

    // Tree mode: no keys, no foreground ----------------------------------------------------

    private static void RunTree(Process core, string[] keys, string? shotsDir)
    {
        if (shotsDir != null)
            Directory.CreateDirectory(shotsDir);
        _pagesList = _window.FindFirst(TreeScope.Descendants, new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.List),
            new PropertyCondition(AutomationElement.NameProperty, "Pages")))!;
        foreach (var key in keys)
        {
            var page = Pages.First(p => p.Key == key);
            Console.WriteLine($"\n== {page.Title}");
            Command(core, $"show-page {key}");
            Check(WaitFor(() => _window.Current.Name == $"FA11y - {page.Title}", 3000), $"the window shows {page.Title}");
            Thread.Sleep(1500); // the page loads its data

            if (key == "social")
                SocialChecks(core, shotsDir);
            else if (key == "locker")
                LockerChecks(core, shotsDir);
            else
                CheckFocusable($"{page.Title}");
        }
    }

    private static void Command(Process core, string line) => core.StandardInput.WriteLine(line);

    private static void Shot(Process core, string? dir, string name)
    {
        if (dir == null)
            return;
        var path = Path.Combine(dir, name + ".png");
        if (File.Exists(path))
            File.Delete(path);
        Command(core, $"screenshot {path}");
        WaitFor(() => File.Exists(path), 3000);
        Info($"screenshot: {path}");
    }

    /// <summary>Everything a screen reader can land on in the visible page: named, with a real role.</summary>
    private static List<AutomationElement> CheckFocusable(string what)
    {
        var all = _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.IsKeyboardFocusableProperty, true))
            .Cast<AutomationElement>()
            .Where(e => { try { return !e.Current.IsOffscreen && !InSidebar(e) && e.Current.ControlType != ControlType.MenuBar
                                       && e.Current.ControlType != ControlType.MenuItem && !Same(e, _pagesList); } catch { return false; } })
            .ToList();
        Console.WriteLine($"   focusable in {what}:");
        foreach (var el in all)
        {
            var c = el.Current;
            Console.WriteLine($"   {Short(c.ControlType),-9} \"{Clip(c.Name)}\"" + (c.HelpText.Length > 0 ? $"  [help: {Clip(c.HelpText)}]" : ""));
            Check(c.Name.Trim().Length > 0, $"focusable {Short(c.ControlType)} has a name");
            Check(c.ControlType != ControlType.Pane && c.ControlType != ControlType.Custom && c.ControlType != ControlType.Group,
                $"\"{Clip(c.Name)}\" has a real role (is {Short(c.ControlType)})");
        }
        var stray = _window.FindAll(TreeScope.Descendants, Automation.ControlViewCondition).Cast<AutomationElement>()
            .Where(e => { try { return e.Current.Name.Contains('_') || (e.Current.ControlType == ControlType.Button && e.FindFirst(TreeScope.Children, Condition.TrueCondition) != null); } catch { return false; } })
            .Select(e => e.Current.Name).ToList();
        Check(stray.Count == 0, $"no access key underscores or label fragments inside buttons ({string.Join(", ", stray)})");
        return all;
    }

    private static AutomationElement? Named(IEnumerable<AutomationElement> elements, string name, ControlType? type = null) =>
        elements.FirstOrDefault(e => e.Current.Name == name && (type == null || e.Current.ControlType == type));

    private static List<string> ItemNames(AutomationElement list) =>
        list.FindAll(TreeScope.Children, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.ListItem))
            .Cast<AutomationElement>().Select(e => e.Current.Name).ToList();

    private static void SocialChecks(Process core, string? shots)
    {
        var focusable = CheckFocusable("Friends");
        var friends = Named(focusable, "Friends", ControlType.List);
        if (Check(friends != null, "the friends list is a List named Friends"))
        {
            var items = ItemNames(friends!);
            Info("items: " + string.Join(" | ", items));
            Check(items.SequenceEqual(new[] { "Bob, favorite", "amy", "Cy", "Dana", "Zed" }),
                "friends: the favorite first, then by name, each item named for what it is");
        }
        foreach (var tab in new[] { "Friends", "Friend Requests", "Party", "Me" })
            Check(_window.FindFirst(TreeScope.Descendants, new AndCondition(
                    new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.TabItem),
                    new PropertyCondition(AutomationElement.NameProperty, tab))) != null, $"a tab named {tab}");
        foreach (var name in new[] { "All Friends", "Favorites", "Search", "Add Friend", "Invite to Party", "Request to Join", "Remove Friend" })
            Check(Named(focusable, name) != null, $"{name} is focusable and named");
        Check(Named(focusable, "All Friends", ControlType.RadioButton) != null, "All Friends is a radio button");
        Shot(core, shots, "social-friends");

        Command(core, "social-tab Friend Requests");
        Thread.Sleep(900);
        focusable = CheckFocusable("Friend Requests");
        var requests = Named(focusable, "Friend requests", ControlType.List);
        if (Check(requests != null, "the requests list is a List named Friend requests"))
            Check(ItemNames(requests!).SequenceEqual(new[] { "Request from Ann", "Request from Ben" }),
                "requests read \"Request from Ann\"");
        foreach (var name in new[] { "Incoming", "Outgoing", "Accept", "Decline" })
            Check(Named(focusable, name) != null, $"{name} is focusable and named");

        Command(core, "social-tab Party");
        Thread.Sleep(900);
        focusable = CheckFocusable("Party");
        var party = Named(focusable, "Party members", ControlType.List);
        if (Check(party != null, "the party list is a List named Party members"))
            Check(ItemNames(party!).SequenceEqual(new[] { "TestPlayer (Leader)", "Pal" }), "party members read with (Leader)");
        foreach (var name in new[] { "Promote to Leader", "Kick Member", "Leave Party" })
            Check(Named(focusable, name) != null, $"{name} is focusable and named");
        Shot(core, shots, "social-party");

        Command(core, "social-tab Me");
        Thread.Sleep(1200);
        focusable = CheckFocusable("Me");
        foreach (var name in new[] { "Epic Account Stats", "Fortnite Stats", "Fortnite Ranked Stats" })
            Check(Named(focusable, name, ControlType.Edit) != null, $"{name} is a named read-only edit box");
        Check(Named(focusable, "Refresh Account Information") != null, "Refresh Account Information is focusable and named");
        Shot(core, shots, "social-me");
    }

    private static void LockerChecks(Process core, string? shots)
    {
        var focusable = CheckFocusable("the locker menu");
        Check(Named(focusable, "Logged in as: TestPlayer", ControlType.Text) != null, "the login status is readable text");
        Check(Named(focusable, "Show Only My Cosmetics", ControlType.CheckBox) != null, "Show Only My Cosmetics is a check box");
        var categories = Named(focusable, "Select a category", ControlType.List);
        if (Check(categories != null, "the categories are a List named Select a category"))
        {
            var items = ItemNames(categories!);
            Check(items.Count > 5 && items[0] == "All Cosmetics" && items[1] == "Outfit", "categories start with All Cosmetics, Outfit");
        }
        foreach (var name in new[] { "View Equipped", "Saved Loadouts", "Save Current as Loadout", "Battle Passes" })
            Check(Named(focusable, name) != null, $"{name} is focusable and named");
        Check(_window.FindFirst(TreeScope.Descendants, new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Text),
                new PropertyCondition(AutomationElement.NameProperty, "Locker"))) != null, "the page heading Locker is in the tree");
        Shot(core, shots, "locker-menu");

        Command(core, "locker-category Outfit");
        Thread.Sleep(1200);
        focusable = CheckFocusable("the Outfit list");
        var list = Named(focusable, "Cosmetics", ControlType.List);
        if (Check(list != null, "the cosmetics are a List named Cosmetics"))
        {
            var items = ItemNames(list!);
            Info("first items: " + string.Join(" | ", items.Take(4)));
            Check(items.Count > 0 && items[0] == "Random, Special, -", $"the first row is Random (is \"{items.FirstOrDefault()}\")");
            Check(items.Count > 1 && items[1].StartsWith("Unequip (Default)"), "the second row is Unequip (Default)");
            Check(items.Count > 2 && items[2].Contains("Marvel series, "), "cosmetic rows read name, rarity and season");
            Check(items.Count < 80, $"the list is virtualized ({items.Count} rows exist for {500} cosmetics)");
        }
        Check(Named(focusable, "Cosmetic Details", ControlType.Edit) != null, "Cosmetic Details is a named edit box");
        foreach (var name in new[] { "Favorites Only", "Sort Favorites First", "Search", "Equip Selected", "Back to Categories" })
            Check(Named(focusable, name) != null, $"{name} is focusable and named");
        Shot(core, shots, "locker-category");

        Command(core, "locker-category All Cosmetics");
        Thread.Sleep(2000);
        focusable = CheckFocusable("the All Cosmetics list");
        list = Named(focusable, "Cosmetics", ControlType.List);
        if (list != null)
        {
            var items = ItemNames(list);
            Check(items.Count < 80, $"3000 cosmetics: only {items.Count} rows exist in the tree");
            Check(items.Count > 0 && items[0].Contains(", Outfit, ") || items.Count > 0 && items[0].Split(',').Length >= 4,
                "All Cosmetics rows include the type");
        }
        Shot(core, shots, "locker-all");
    }

    // Without the foreground ---------------------------------------------------------------------

    /// <summary>The focusable elements of the page on screen, in tree order (the Tab order's stand-in).</summary>
    private static List<AutomationElement> FocusableOnPage() =>
        _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.IsKeyboardFocusableProperty, true))
            .Cast<AutomationElement>()
            .Where(e => !InSidebar(e) && e.Current.ControlType != ControlType.MenuBar && e.Current.ControlType != ControlType.MenuItem
                        && e.Current.ControlType != ControlType.Tab && !(e.Current.ControlType == ControlType.List && e.Current.Name == "Pages"))
            .ToList();

    private static void RunWithoutForeground()
    {
        Console.WriteLine("\n== Each page, shown by the test core");
        var times = new List<double>();
        foreach (var page in Pages)
        {
            Console.WriteLine($"\n-- {page.Title}");
            var sw = Stopwatch.StartNew();
            _core.StandardInput.WriteLine($"show-page {page.Key}");
            var shown = WaitFor(() => _window.Current.Name == $"FA11y - {page.Title}", 3000);
            Check(shown, $"the page {page.Title} is shown ({sw.Elapsed.TotalMilliseconds:F0} ms)");
            if (page.Key is "settings" or "keybinds")
                WaitFor(() => FocusableOnPage().Count > 2, 5000);
            Thread.Sleep(300);
            times.Add(sw.Elapsed.TotalMilliseconds);
            Check(PageContentIsFor(page.Key), $"only {page.Title}'s content is in the accessibility tree");
            AuditPage(page, FocusableOnPage());
        }

        Console.WriteLine("\n== Settings and Keybinds editor");
        EditorChecks();
        Console.WriteLine("\n== Timings from the window's own log");
        foreach (var line in ReadShared(Path.Combine(_root, "logs", "ui.log")).Split('\n').Where(l => l.Contains(" PERF ")).TakeLast(40))
            Info(line.Trim());
    }

    // One page --------------------------------------------------------------------

    private static void WalkPage(int index)
    {
        var page = Pages[index];
        Console.WriteLine($"\n-- {page.Title}");

        if (page.Key == "fortnite")
            Thread.Sleep(500); // the page asks the core for its state when it is shown
        // Tab from the sidebar through every stop on the page, until focus wraps back to the sidebar.
        var seen = new List<AutomationElement>();
        for (var n = 0; n < 80; n++)
        {
            Key(Vk.Tab);
            Thread.Sleep(60);
            var el = AutomationElement.FocusedElement;
            if (InSidebar(el) || seen.Any(s => Same(s, el)))
                break;
            seen.Add(el);
        }
        AuditPage(page, seen);

        // Enter from the sidebar lands on the page's first control; Escape comes back.
        WalkEnter(page);
    }

    /// <summary>Everything the screen reader sees on a page: names, roles, and what each page has to say.</summary>
    private static void AuditPage((string Key, string Title, string Group) page, List<AutomationElement> seen)
    {
        Check(seen.Count > 0, "something on the page can be reached");
        foreach (var el in seen)
        {
            var c = el.Current;
            Console.WriteLine($"   {Short(c.ControlType),-9} \"{Clip(c.Name)}\"" + (c.HelpText.Length > 0 ? $"  [help: {Clip(c.HelpText)}]" : "")
                              + (c.AccessKey.Length > 0 ? $"  [key: {c.AccessKey}]" : ""));
            Check(c.Name.Trim().Length > 0, $"focusable {Short(c.ControlType)} has a name");
            Check(c.ControlType != ControlType.Pane && c.ControlType != ControlType.Custom && c.ControlType != ControlType.Group,
                $"\"{Clip(c.Name)}\" has a real role (is {Short(c.ControlType)})");
        }
        var names = seen.Select(e => e.Current.Name).ToList();
        var stray = _window.FindAll(TreeScope.Descendants, Automation.ControlViewCondition).Cast<AutomationElement>()
            .Where(e => { try { return e.Current.Name.Contains('_') || (e.Current.ControlType == ControlType.Button && e.FindFirst(TreeScope.Children, Condition.TrueCondition) != null); } catch { return false; } })
            .Select(e => e.Current.Name).ToList();
        Check(stray.Count == 0, $"no access key underscores or label fragments inside buttons ({string.Join(", ", stray)})");
        if (page.Key == "home")
        {
            Check(names.Contains("Fortnite, 31.10, Ready"), "the Fortnite card reads \"Fortnite, 31.10, Ready\"");
            Check(names.Contains("Epic account, Signed in, TestPlayer"), "the account card reads in full");
            Check(names.Contains("FA11y, 1.2.3, Update available: 99.0.0"), "the FA11y card reads in full");
            Check(names.Any(n => n.StartsWith("FA11y's keybinds turn on when Fortnite starts.")), "the keybinds hint is reachable");
            Check(seen.Any(e => e.Current.Name == "What's new" && e.Current.ControlType == ControlType.Edit), "What's new is a named edit box");
            Check(names.IndexOf("Play Fortnite") < names.IndexOf("Fortnite, 31.10, Ready"), "Tab order follows the screen: Play, then the cards");
        }
        // Without real keys every radio option is in the tree, not only the chosen one: --static checks this page.
        if (page.Key == "fortnite" && !_synthetic)
            CheckFortnitePage(seen, names);
        if (page.Key == "account")
            Check(seen.Any(e => e.Current.Name == "TestPlayer. Signed in." && e.Current.ControlType == ControlType.Text),
                "the account text reads \"TestPlayer. Signed in.\" as Text");
        if (page.Key == "settings")
        {
            Check(seen[0].Current.ControlType == ControlType.TabItem && seen[0].Current.Name == "General",
                "Tab goes first to the General tab");
            Check(seen.Any(e => e.Current.Name == "Start Fortnite when FA11y opens" && e.Current.ControlType == ControlType.CheckBox),
                "a toggle is a check box named by its label");
            Check(seen.Any(e => e.Current.Name == "When I close the FA11y window" && e.Current.ControlType == ControlType.ComboBox),
                "a choice is a combo box named by its label");
            var group = _window.FindFirst(TreeScope.Descendants, new AndCondition(
                new PropertyCondition(AutomationElement.NameProperty, "Startup and updates"),
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Group)));
            Check(group != null, "groups are named, so focus entering one is announced");
            var help = seen.FirstOrDefault(e => e.Current.Name == "Start Fortnite when FA11y opens")?.Current.HelpText ?? "";
            Check(help.StartsWith("Starts Fortnite automatically"), $"a setting's description is its help text (\"{Clip(help)}\")");
        }
        if (page.Key == "keybinds")
        {
            Check(seen.Count > 0 && seen[0].Current.Name.StartsWith("Toggle Keybinds: "), "the first stop is the first keybind");
            Check(seen.Any(e => e.Current.Name == "Fire: Left Control" && e.Current.ControlType == ControlType.Button),
                "a keybind is a button named \"Fire: Left Control\"");
        }
        if (page.Key == "about")
        {
            Check(names.Contains("FA11y 1.2.3"), "the version text is reachable");
            Check(seen.Any(e => e.Current.Name == "Changelog" && e.Current.ControlType == ControlType.Edit), "Changelog is a named edit box");
        }

    }

    private static void WalkEnter((string Key, string Title, string Group) page)
    {
        Key(Vk.Enter);
        Thread.Sleep(120);
        var first = AutomationElement.FocusedElement;
        if (Check(!InSidebar(first), $"Enter moves into the page (first stop: \"{Safe(first)}\")"))
        {
            if (page.Key == "home")
                Check(Safe(first) == "Restart to update FA11y", "Enter on Home lands on the update button when there is one");
            if (page.Key == "fortnite")
                Check(Safe(first) == "Play", "Enter on Fortnite lands on Play");
            if (page.Key == "account")
                Check(Safe(first) == "TestPlayer. Signed in.", "Enter on the account page lands on who is signed in");
            if (page.Key == "about")
                Check(Safe(first) == "FA11y 1.2.3", "Enter on About lands on the version");
            if (page.Key == "settings")
                Check(Safe(first) == "Start Fortnite when FA11y opens", "Enter on Settings lands on the first setting");
            if (page.Key == "keybinds")
                Check(Safe(first).StartsWith("Toggle Keybinds: "), "Enter on Keybinds lands on the first keybind");
            Key(Vk.Escape);
            Thread.Sleep(150);
            var back = AutomationElement.FocusedElement;
            Check(InSidebar(back) && back.Current.Name == page.Title, $"Escape returns to the sidebar item {page.Title} (is \"{Safe(back)}\")");
        }
    }

    // The editor, checked against the config file the test core writes ----------------------------------
    // With the foreground, keys are real key presses. Without it (see RunWithoutForeground), they are sent to the
    // focused control through the test core, and the UI Automation patterns do the rest.

    private static string ReadShared(string path)
    {
        try
        {
            using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            using var reader = new StreamReader(stream);
            return reader.ReadToEnd();
        }
        catch (IOException)
        {
            return "";
        }
    }

    private static string Config() => ReadShared(Path.Combine(_root, "config.txt"));
    private static string Log() => ReadShared(Path.Combine(_root, "fake-core.log"));

    private static string WpfKeyName(Vk key) => key switch
    {
        Vk.RControl => "RightCtrl",
        Vk.LShift => "LeftShift",
        _ => key.ToString(),
    };

    /// <summary>Press a key. mods are held while it goes down (Control, Shift); held are other keys to count as held (LeftShift).</summary>
    private static void Press(Vk key, string mods = "", string held = "")
    {
        if (_synthetic)
        {
            var heldNames = string.Join(',', held.Split(',', StringSplitOptions.RemoveEmptyEntries).Select(h => WpfKeyName(Enum.Parse<Vk>(h))));
            _core.StandardInput.WriteLine($"key {WpfKeyName(key)}" + (mods.Length > 0 ? $" mods={mods}" : "")
                                          + (heldNames.Length > 0 ? $" held={heldNames}" : ""));
            Thread.Sleep(150);
            return;
        }
        var modifiers = mods.Split(',', StringSplitOptions.RemoveEmptyEntries)
            .Select(m => m == "Control" ? Vk.Control : Vk.Shift).ToArray();
        var holds = held.Split(',', StringSplitOptions.RemoveEmptyEntries).Select(h => Enum.Parse<Vk>(h)).ToArray();
        foreach (var h in holds) Send(h, false);
        KeyWith(key, modifiers);
        foreach (var h in holds.Reverse()) Send(h, true);
    }

    /// <summary>Every element of the FA11y window and its popups with this name (and type).</summary>
    private static AutomationElement? Find(string name, ControlType? type = null)
    {
        var condition = type == null
            ? new PropertyCondition(AutomationElement.NameProperty, name)
            : (Condition)new AndCondition(new PropertyCondition(AutomationElement.NameProperty, name),
                new PropertyCondition(AutomationElement.ControlTypeProperty, type));
        foreach (AutomationElement window in AutomationElement.RootElement.FindAll(TreeScope.Children,
                     new PropertyCondition(AutomationElement.ProcessIdProperty, _uiPid)))
        {
            var found = window.FindFirst(TreeScope.Descendants, condition);
            if (found != null)
                return found;
        }
        return null;
    }

    /// <summary>Give an element focus the way a screen reader does.</summary>
    private static bool FocusElement(string name, ControlType? type = null)
    {
        if (!WaitFor(() => Find(name, type) != null, 4000))
            return false;
        Find(name, type)!.SetFocus();
        return true;
    }

    private static string FocusedName() => FocusedInfo().Name;

    private static (string Name, string Type) FocusedInfo()
    {
        if (!_synthetic)
        {
            var f = AutomationElement.FocusedElement;
            return (f.Current.Name, Short(f.Current.ControlType));
        }
        var before = Regex.Matches(Log(), "test\\.focused").Count;
        _core.StandardInput.WriteLine("where");
        WaitFor(() => Regex.Matches(Log(), "test\\.focused").Count > before, 2000);
        var last = Regex.Matches(Log(), "test\\.focused \\{'name': (?:'|\")(.*?)(?:'|\"), 'type': '(.*?)'\\}").LastOrDefault();
        return last == null ? ("", "") : (last.Groups[1].Value, last.Groups[2].Value);
    }

    private static string FocusedText()
    {
        var (name, type) = FocusedInfo();
        return $"{type} \"{name}\"";
    }

    private static bool FocusIs(string name)
    {
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < 3000)
        {
            try { if (FocusedName() == name) return true; } catch { /* the tree is changing */ }
            Thread.Sleep(80);
        }
        return false;
    }

    private static void GoToPage(string title, string key)
    {
        if (_synthetic)
        {
            _core.StandardInput.WriteLine($"show-page {key}");
            WaitFor(() => _window.Current.Name == $"FA11y - {title}", 3000);
            Thread.Sleep(300);
            WaitFor(() => FocusableOnPage().Count > 0, 3000);
            FocusableOnPage().FirstOrDefault()?.SetFocus();
            Thread.Sleep(100);
            return;
        }
        if (!InSidebar(AutomationElement.FocusedElement))
            Key(Vk.F6);
        Key(Vk.Home);
        for (var i = 0; i < 12 && _window.Current.Name != $"FA11y - {title}"; i++)
        {
            Key(Vk.Down);
            Thread.Sleep(40);
        }
        WaitFor(() => _window.Current.Name == $"FA11y - {title}", 2000);
        Thread.Sleep(300);
        Key(Vk.Enter); // into the page, as the synthetic path does
        Thread.Sleep(200);
    }

    private static void SelectTab(string name)
    {
        var tab = Find(name, ControlType.TabItem);
        if (tab != null)
            ((SelectionItemPattern)tab.GetCurrentPattern(SelectionItemPattern.Pattern)).Select();
    }

    private static string SelectedTab()
    {
        foreach (AutomationElement tab in _window.FindAll(TreeScope.Descendants,
                     new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.TabItem)))
        {
            if (((SelectionItemPattern)tab.GetCurrentPattern(SelectionItemPattern.Pattern)).Current.IsSelected)
                return tab.Current.Name;
        }
        return "";
    }

    private static void SetText(AutomationElement edit, string text) =>
        ((ValuePattern)edit.GetCurrentPattern(ValuePattern.Pattern)).SetValue(text);

    private static string TextOf(AutomationElement edit) =>
        ((ValuePattern)edit.GetCurrentPattern(ValuePattern.Pattern)).Current.Value;

    private static AutomationElement? SearchWindowElement()
    {
        // An owned window is a top-level window, but UI Automation may list it under its owner.
        var condition = new AndCondition(
            new PropertyCondition(AutomationElement.NameProperty, "Search settings"),
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Window));
        return AutomationElement.RootElement.FindFirst(TreeScope.Children, new AndCondition(
                   new PropertyCondition(AutomationElement.ProcessIdProperty, _uiPid), condition))
               ?? _window.FindFirst(TreeScope.Children, condition);
    }

    private static void TypeText(string text)
    {
        foreach (var c in text)
        {
            Key(c == ' ' ? Vk.Space : (Vk)char.ToUpperInvariant(c));
            Thread.Sleep(15);
        }
    }

    /// <summary>Ctrl+F, the words, the first result's text, Enter. Then the setting should have focus.</summary>
    private static void SearchAndJump(string query, string firstResult, string focusedName)
    {
        Press(Vk.F, mods: "Control");
        var opened = WaitFor(() => SearchWindowElement() != null, 3000);
        Check(opened, $"Ctrl+F opens the search popup ({query})");
        if (!opened)
        {
            foreach (AutomationElement w in _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Window)))
                Info($"window of the FA11y process: \"{w.Current.Name}\" ({Short(w.Current.ControlType)}, offscreen {w.Current.IsOffscreen})");
            return;
        }
        Thread.Sleep(250);
        var box = SearchWindowElement()!.FindFirst(TreeScope.Descendants, new AndCondition(
            new PropertyCondition(AutomationElement.NameProperty, "Search settings"),
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Edit)));
        if (_synthetic)
        {
            box!.SetFocus();
            SetText(box, query);
        }
        else
        {
            TypeText(query);
        }
        Thread.Sleep(250);
        var results = SearchWindowElement()!.FindFirst(TreeScope.Descendants, new PropertyCondition(AutomationElement.NameProperty, "Results"));
        var first = results?.FindFirst(TreeScope.Children, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.ListItem));
        var firstName = first?.Current.Name ?? "";
        Check(firstResult.EndsWith('*') ? firstName.StartsWith(firstResult[..^1]) : firstName == firstResult,
            $"the first match for \"{query}\" reads \"{firstResult}\" (is \"{firstName}\")");
        Press(Vk.Enter);
        Check(WaitFor(() => SearchWindowElement() == null, 2000), "Enter closes the popup");
        Check(FocusIs(focusedName), $"the setting \"{focusedName}\" has focus (is {FocusedText()})");
    }

    private static void EditorChecks()
    {
        var sw = new Stopwatch();

        // Settings: toggles, tabs, search, numbers ------------------------------------------------------
        GoToPage("Settings", "settings");
        Check(FocusElement("Start Fortnite when FA11y opens", ControlType.CheckBox), "the first toggle is on the General tab");
        var toggle = Find("Start Fortnite when FA11y opens", ControlType.CheckBox)!;
        ((TogglePattern)toggle.GetCurrentPattern(TogglePattern.Pattern)).Toggle();
        Check(WaitFor(() => Regex.IsMatch(Config(), @"StartFortniteOnLaunch = true"), 3000), "toggling a setting saves it to config.txt");
        Press(Vk.R);
        Check(WaitFor(() => Regex.IsMatch(Config(), @"StartFortniteOnLaunch = false"), 3000), "R resets the focused setting to its default");
        Check(FocusIs("Start Fortnite when FA11y opens"), "focus stays on the setting after R");
        Check(WaitFor(() => ((TogglePattern)Find("Start Fortnite when FA11y opens", ControlType.CheckBox)!
                .GetCurrentPattern(TogglePattern.Pattern)).Current.ToggleState == ToggleState.Off, 2000), "the check box shows the default");

        foreach (var tab in new[] { "Toggles", "Values", "Audio", "GameObjects", "Advanced", "General" })
        {
            sw.Restart();
            SelectTab(tab);
            var shown = WaitFor(() => SelectedTab() == tab && FocusableOnPage().Count > 2, 3000);
            Check(shown, $"the {tab} tab shows its settings");
        }
        Check(_window.Current.Name == "FA11y - Settings", "switching tabs doesn't change the page");

        if (!_synthetic)
        {
            FocusElement("General", ControlType.TabItem);
            Key(Vk.Right);
            Check(FocusIs("Toggles"), "Right arrow moves to the next tab and focus stays on the tabs");
            KeyWith(Vk.Tab, Vk.Control);
            Check(FocusIs("Values") && _window.Current.Name == "FA11y - Settings", "Ctrl+Tab inside the tabs goes to the next tab, not the next page");
            KeyWith(Vk.Tab, Vk.Control, Vk.Shift);
            Check(FocusIs("Toggles"), "Ctrl+Shift+Tab goes back a tab");
            Key(Vk.Tab);
            Check(FocusIs("Mouse keys (look around, click, and aim with the keyboard)"), "Tab from a tab goes to the tab's first setting");
        }

        SearchAndJump("turn sens", "Turn sensitivity, Values", "Turn sensitivity");
        Check(SelectedTab() == "Values", "the search switched to the Values tab");
        Press(Vk.Up);
        Check(WaitFor(() => Regex.IsMatch(Config(), @"TurnSensitivity = 76"), 4000), "Up arrow steps a number and saves it");
        Check(TextOf(Find("Turn sensitivity", ControlType.Edit)!) == "76", "the number box shows 76");
        Press(Vk.Down);
        Press(Vk.Down);
        Check(WaitFor(() => Regex.IsMatch(Config(), @"TurnSensitivity = 74"), 4000), "quick arrow presses save the last value");
        SetText(Find("Turn sensitivity", ControlType.Edit)!, "120");
        Check(WaitFor(() => Regex.IsMatch(Config(), @"TurnSensitivity = 120"), 4000), "typing a number saves it after a moment");
        SetText(Find("Turn sensitivity", ControlType.Edit)!, "999999");
        Check(WaitFor(() => Regex.IsMatch(Config(), @"TurnSensitivity = 50000"), 4000), "a number above the range is held to the range");
        Check(WaitFor(() => TextOf(Find("Turn sensitivity", ControlType.Edit)!) == "50000", 3000), "and the box shows what was saved");
        FocusElement("Turn sensitivity", ControlType.Edit);
        Press(Vk.R);
        Check(WaitFor(() => Regex.IsMatch(Config(), @"TurnSensitivity = 75"), 3000), "R on a number box resets it");
        Check(WaitFor(() => TextOf(Find("Turn sensitivity", ControlType.Edit)!) == "75", 3000), "the number box shows the default again");

        SelectTab("Advanced");
        WaitFor(() => Find("Recenter delay", ControlType.Edit) != null, 3000);
        FocusElement("Recenter delay", ControlType.Edit);
        Press(Vk.Up);
        Check(WaitFor(() => Regex.IsMatch(Config(), @"RecenterDelay = 0\.02"), 4000), "a decimal setting steps by its last digit and keeps its format");

        SearchAndJump("master", "Master volume, Audio", "Master volume");
        Press(Vk.Down);
        Check(WaitFor(() => Regex.IsMatch(Config(), @"MasterVolume = 0\.99"), 4000), "a volume steps by one percent and is saved as a fraction");
        Press(Vk.T);
        Check(WaitFor(() => Log().Contains("settings.test_volume"), 3000), "T asks the core to play the volume's test sound");
        Check(Find("Test Master volume", ControlType.Button) != null, "a volume has a Test button named for it");
        Press(Vk.R);
        Check(WaitFor(() => Regex.IsMatch(Config(), @"MasterVolume = 1\.0"), 3000), "R on a volume resets it");

        // Choices
        SelectTab("General");
        FocusElement("When I close the FA11y window", ControlType.ComboBox);
        Press(Vk.Down);
        Check(WaitFor(() => Regex.IsMatch(Config(), @"CloseAction = tray"), 3000), "arrowing through a choice saves the new value");
        Check(FocusIs("When I close the FA11y window"), "focus stays on the choice");
        Press(Vk.R);
        Check(WaitFor(() => Regex.IsMatch(Config(), @"CloseAction = ask"), 3000), "R on a choice resets it");

        // The GameObjects tab: universal settings, a map picker, then the picked map's settings.
        SearchAndJump("visit distance", "Visit distance (meters), GameObjects (*", "Visit distance (meters)");
        Check(SelectedTab() == "GameObjects", "the search switched to the GameObjects tab and its map");
        Check(Find("Map", ControlType.ComboBox) != null, "the Map picker is a combo box named Map");
        Check(Find("Chests", ControlType.Group) != null, "a map's objects are groups named for the object");

        // Keybinds: capture, cancel, unbind, swap -----------------------------------------------------------
        GoToPage("Keybinds", "keybinds");
        SearchAndJump("recenter", "Recenter, Keybinds", "Recenter: Numpad 5");
        Press(Vk.Enter);
        Check(FocusIs("Recenter: Press any key"), "Enter on a keybind waits for a key");
        Check(WaitFor(() => Log().Contains("keybinds.capture {'active': True}"), 3000), "the core is told to silence its own keybinds");
        Press(Vk.F9);
        Check(FocusIs("Recenter: F9"), "the pressed key becomes the binding");
        Check(WaitFor(() => Regex.IsMatch(Config(), @"Recenter = f9"), 3000), "the binding is saved as f9");
        Check(WaitFor(() => Log().Contains("keybinds.capture {'active': False}"), 3000), "the core is told capture ended");

        Press(Vk.Enter);
        Check(FocusIs("Recenter: Press any key"), "capturing again");
        Press(Vk.Escape);
        Check(FocusIs("Recenter: F9"), "Escape cancels and restores the key");
        Check(IsVisible(_uiPid), "Escape while capturing doesn't hide the window");
        Press(Vk.Delete);
        Check(FocusIs("Recenter: Unbound"), "Delete unbinds the focused keybind");
        Check(WaitFor(() => !Regex.IsMatch(Config(), @"Recenter = f9"), 3000), "the unbinding is saved");
        Press(Vk.R);
        Check(FocusIs("Recenter: Numpad 5"), "R puts the default key back");
        Check(WaitFor(() => Regex.IsMatch(Config(), @"Recenter = num 5"), 3000), "the default is saved");

        Press(Vk.Enter);
        Press(Vk.F8, held: "LShift");
        Check(FocusIs("Recenter: Left Shift + F8"), "a modifier held with a key is part of the binding");
        Check(WaitFor(() => Regex.IsMatch(Config(), @"Recenter = lshift\+f8"), 3000), "it is saved as lshift+f8");
        Press(Vk.R);
        Check(FocusIs("Recenter: Numpad 5"), "R restores it");

        Press(Vk.Enter);
        Press(Vk.Space);
        Check(FocusIs("Recenter: Space"), "Space can be bound");
        Press(Vk.R);
        Check(FocusIs("Recenter: Numpad 5"), "R restores it again");

        SearchAndJump("fire", "Fire, Keybinds", "Fire: Left Control");
        Press(Vk.Enter);
        Press(Vk.RControl);
        Check(FocusIs("Fire: Right Control"), "binding a key another action has takes it");
        Check(WaitFor(() => Find("Target: Left Control", ControlType.Button) != null, 3000), "the other action got this action's old key (swap)");
        Press(Vk.R);
        Check(FocusIs("Fire: Left Control"), "R brings the default back, swapping again");
        Check(WaitFor(() => Find("Target: Right Control", ControlType.Button) != null, 3000), "and the other action has its key back");
        Check(Regex.Matches(Log(), Regex.Escape("keybinds.capture {'active': True}")).Count ==
              Regex.Matches(Log(), Regex.Escape("keybinds.capture {'active': False}")).Count,
            "every capture start has a matching end");
    }

    // UI Automation helpers ------------------------------------------------------------

    private static AutomationElement? FindWindow(int pid) =>
        AutomationElement.RootElement.FindFirst(TreeScope.Children, new AndCondition(
            new PropertyCondition(AutomationElement.ProcessIdProperty, pid),
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Window)));

    private static bool IsVisible(int pid)
    {
        var w = FindWindow(pid);
        return w != null && !w.Current.IsOffscreen;
    }

    private static List<AutomationElement> Items() =>
        _pagesList.FindAll(TreeScope.Children, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.ListItem))
            .Cast<AutomationElement>().ToList();

    private static bool InSidebar(AutomationElement? el)
    {
        try
        {
            return el != null && el.Current.ControlType == ControlType.ListItem
                   && Items().Any(i => Same(i, el));
        }
        catch
        {
            return false;
        }
    }

    private static bool Same(AutomationElement a, AutomationElement b) => Automation.Compare(a, b);

    private static bool PageContentIsFor(string key)
    {
        // The page heading of the current page is in the tree; the previous page's is not.
        var title = Pages.First(p => p.Key == key).Title;
        var headings = _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Text))
            .Cast<AutomationElement>().Select(e => e.Current.Name).ToList();
        if (key == "home")
            return headings.Any(h => h.StartsWith("Welcome"));
        var others = Pages.Where(p => p.Key != key && p.Key != "home").Select(p => p.Title);
        return headings.Contains(title) && !headings.Any(h => others.Contains(h));
    }

    private static string Safe(AutomationElement? e)
    {
        try { return e?.Current.Name ?? "nothing"; } catch { return "gone"; }
    }

    private static string Short(ControlType t) => t.ProgrammaticName.Replace("ControlType.", "");
    private static string Clip(string s) => s.Length > 70 ? s[..70] + "..." : s;

    private static bool WaitFor(Func<bool> condition, int timeoutMs)
    {
        var sw = Stopwatch.StartNew();
        while (sw.ElapsedMilliseconds < timeoutMs)
        {
            try { if (condition()) return true; } catch { /* the tree is changing */ }
            Thread.Sleep(1);
        }
        return false;
    }

    private static IntPtr Handle(AutomationElement e) => new(e.Current.NativeWindowHandle);

    // Results ---------------------------------------------------------------------------

    private static bool Check(bool ok, string what)
    {
        if (!ok)
        {
            _failures++;
            Console.WriteLine($"   FAIL: {what}");
        }
        else if (what.Length > 0 && !what.StartsWith("focusable") && !what.Contains("has a real role"))
        {
            Console.WriteLine($"   ok: {what}");
        }
        return ok;
    }

    private static void Info(string message) => Console.WriteLine($"   {message}");

    private static int Fail(string message)
    {
        Console.WriteLine($"FAIL: {message}");
        return 1;
    }

    // Keyboard ---------------------------------------------------------------------------

    private enum Vk : ushort
    {
        Tab = 0x09, Enter = 0x0D, Shift = 0x10, Control = 0x11, Escape = 0x1B, Space = 0x20,
        PageUp = 0x21, PageDown = 0x22, End = 0x23, Home = 0x24, Left = 0x25, Up = 0x26, Right = 0x27, Down = 0x28,
        Delete = 0x2E, F = 0x46, R = 0x52, T = 0x54, F6 = 0x75, F8 = 0x77, F9 = 0x78, LShift = 0xA0, RControl = 0xA3,
    }

    private static void TypeLetter(char c) => Key((Vk)char.ToUpperInvariant(c));

    private static void Key(Vk key) => KeyWith(key);

    private static void KeyWith(Vk key, params Vk[] modifiers)
    {
        if (!ForegroundIsOurs())
            throw new InvalidOperationException("The FA11y window lost the foreground; refusing to type into another program.");
        foreach (var m in modifiers) Send(m, false);
        Send(key, false);
        Send(key, true);
        foreach (var m in modifiers.Reverse()) Send(m, true);
    }

    private static void Send(Vk key, bool up)
    {
        var extended = key is Vk.Down or Vk.End or Vk.Home or Vk.Up or Vk.Left or Vk.Right or Vk.Delete
            or Vk.PageUp or Vk.PageDown or Vk.RControl;
        var input = new INPUT
        {
            type = 1,
            u = new InputUnion
            {
                ki = new KEYBDINPUT
                {
                    wVk = (ushort)key,
                    wScan = (ushort)MapVirtualKey((uint)key, 0),
                    dwFlags = (extended ? 1u : 0u) | (up ? 2u : 0u),
                },
            },
        };
        SendInput(1, new[] { input }, Marshal.SizeOf<INPUT>());
    }

    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint MapVirtualKey(uint code, uint mapType);
    [DllImport("user32.dll", SetLastError = true)] private static extern uint SendInput(uint count, INPUT[] inputs, int size);

    private static IntPtr Foreground() => GetForegroundWindow();

    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);

    /// <summary>The foreground window belongs to the FA11y window process (the main window or one of its popups).</summary>
    private static bool ForegroundIsOurs()
    {
        GetWindowThreadProcessId(Foreground(), out var pid);
        return pid == _uiPid;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct KEYBDINPUT
    {
        public ushort wVk;
        public ushort wScan;
        public uint dwFlags;
        public uint time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct MOUSEINPUT
    {
        public int dx, dy;
        public uint mouseData, dwFlags, time;
        public IntPtr dwExtraInfo;
    }

    [StructLayout(LayoutKind.Explicit)]
    private struct InputUnion
    {
        [FieldOffset(0)] public MOUSEINPUT mi;
        [FieldOffset(0)] public KEYBDINPUT ki;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct INPUT
    {
        public uint type;
        public InputUnion u;
    }
}
