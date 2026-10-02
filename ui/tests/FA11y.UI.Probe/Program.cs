using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
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
///   FA11y.UI.Probe --python PATH_TO_PYTHON [--fake-core PATH] [--root DIR] [--static]
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

        if (treeKeys == null)
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

        Console.WriteLine("\n== Escape and the tray");
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
        var stray = _window.FindAll(TreeScope.Descendants, Condition.TrueCondition).Cast<AutomationElement>()
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

    // One page --------------------------------------------------------------------

    private static void WalkPage(int index)
    {
        var page = Pages[index];
        Console.WriteLine($"\n-- {page.Title}");

        if (page.Key == "fortnite")
            Thread.Sleep(500); // the page asks the core for its state when it is shown
        // Tab from the sidebar through every stop on the page, until focus wraps back to the sidebar.
        var seen = new List<AutomationElement>();
        for (var n = 0; n < 40; n++)
        {
            Key(Vk.Tab);
            Thread.Sleep(60);
            var el = AutomationElement.FocusedElement;
            if (InSidebar(el) || seen.Any(s => Same(s, el)))
                break;
            seen.Add(el);
        }
        Check(seen.Count > 0, "Tab reaches something on the page");
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
        var stray = _window.FindAll(TreeScope.Descendants, Condition.TrueCondition).Cast<AutomationElement>()
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
        if (page.Key == "fortnite")
            CheckFortnitePage(seen, names);
        if (page.Key == "account")
            Check(seen.Any(e => e.Current.Name == "TestPlayer. Signed in." && e.Current.ControlType == ControlType.Text),
                "the account text reads \"TestPlayer. Signed in.\" as Text");
        if (page.Key == "about")
        {
            Check(names.Contains("FA11y 1.2.3"), "the version text is reachable");
            Check(seen.Any(e => e.Current.Name == "Changelog" && e.Current.ControlType == ControlType.Edit), "Changelog is a named edit box");
        }

        // Enter from the sidebar lands on the page's first control; Escape comes back.
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
            Key(Vk.Escape);
            Thread.Sleep(150);
            var back = AutomationElement.FocusedElement;
            Check(InSidebar(back) && back.Current.Name == page.Title, $"Escape returns to the sidebar item {page.Title} (is \"{Safe(back)}\")");
        }
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
        Tab = 0x09, Enter = 0x0D, Shift = 0x10, Control = 0x11, Escape = 0x1B,
        End = 0x23, Home = 0x24, Up = 0x26, Down = 0x28, F6 = 0x75,
    }

    private static void TypeLetter(char c) => Key((Vk)char.ToUpperInvariant(c));

    private static void Key(Vk key) => KeyWith(key);

    private static void KeyWith(Vk key, params Vk[] modifiers)
    {
        if (Foreground() != Handle(_window))
            throw new InvalidOperationException("The FA11y window lost the foreground; refusing to type into another program.");
        foreach (var m in modifiers) Send(m, false);
        Send(key, false);
        Send(key, true);
        foreach (var m in modifiers.Reverse()) Send(m, true);
    }

    private static void Send(Vk key, bool up)
    {
        var extended = key is Vk.Down or Vk.Up or Vk.End or Vk.Home;
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
