using System.Diagnostics;
using System.IO;
using System.Windows.Automation;

namespace FA11y.UI.Probe;

/// <summary>The Fortnite page's operations and first-run setup, walked through UI Automation.</summary>
internal static partial class Program
{
    private static string FocusedNow() => Safe(AutomationElement.FocusedElement);

    private static bool TabTo(string name, int max = 20)
    {
        for (var i = 0; i < max; i++)
        {
            if (FocusedNow() == name)
                return true;
            Key(Vk.Tab);
            Thread.Sleep(60);
        }
        return FocusedNow() == name;
    }

    /// <summary>Every stop from the current focus until Tab comes back to it.</summary>
    private static List<AutomationElement> TabStops(int max = 15)
    {
        var first = AutomationElement.FocusedElement;
        var stops = new List<AutomationElement> { first };
        for (var i = 0; i < max; i++)
        {
            Key(Vk.Tab);
            Thread.Sleep(60);
            var el = AutomationElement.FocusedElement;
            if (Same(el, first))
                break;
            stops.Add(el);
        }
        return stops;
    }

    private static string Names(IEnumerable<AutomationElement> els) =>
        string.Join(" | ", els.Select(e => Clip(e.Current.Name)));

    private static bool IsSelected(AutomationElement el) =>
        el.TryGetCurrentPattern(SelectionItemPattern.Pattern, out var p) && ((SelectionItemPattern)p).Current.IsSelected;

    // The Fortnite page -------------------------------------------------------------------

    private static void CheckFortnitePage(List<AutomationElement> seen, List<string> names)
    {
        var expected = new[]
        {
            "Play", "31.10 · managed by FA11y · D:\\Fortnite · 60 GB", "Check for updates", "Verify and repair",
            "Move install", "Open folder", "Uninstall", "DirectX 12", "Skip the splash screen", "Extra arguments",
            "Window mode: Windowed. Problem.", "Game resolution: 1920 by 1080. OK.", "Screen resolution: 1920 by 1080. OK.",
            "FakerInput driver: Connected. OK.", "Check again",
            "No mouse selected for passthrough.", "Passthrough lets you", "Detect mouse",
        };
        Check(names.Count == expected.Length, $"the Fortnite page has {expected.Length} tab stops (found {names.Count}: {string.Join(" | ", names.Select(Clip))})");
        for (var i = 0; i < Math.Min(names.Count, expected.Length); i++)
            Check(names[i].StartsWith(expected[i]), $"Fortnite tab stop {i + 1} is \"{expected[i]}\" (got \"{Clip(names[i])}\")");
        var radio = seen.FirstOrDefault(e => e.Current.Name == "DirectX 12");
        Check(radio != null && radio.Current.ControlType == ControlType.RadioButton && IsSelected(radio),
            "only the chosen Graphics option is a tab stop, and it is a selected radio button");
        var extra = seen.FirstOrDefault(e => e.Current.Name == "Extra arguments");
        Check(extra != null && extra.Current.ControlType == ControlType.Edit
              && extra.TryGetCurrentPattern(ValuePattern.Pattern, out var v) && ((ValuePattern)v).Current.Value == "-nosound",
            "Extra arguments is an edit box holding the saved text");
        Check(seen.Any(e => e.Current.Name == "Skip the splash screen" && e.Current.ControlType == ControlType.CheckBox && ToggleOn(e)),
            "Skip the splash screen is a checked check box");
        var group = _window.FindFirst(TreeScope.Descendants, new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Group),
            new PropertyCondition(AutomationElement.NameProperty, "Graphics")));
        Check(group != null, "the Graphics radio buttons are in a group named \"Graphics\"");
        Check(_window.FindFirst(TreeScope.Descendants, new PropertyCondition(AutomationElement.NameProperty, "Progress")) == null,
            "no progress bar is in the tree while nothing runs");
    }

    private static bool ToggleOn(AutomationElement el) =>
        el.TryGetCurrentPattern(TogglePattern.Pattern, out var p) && ((TogglePattern)p).Current.ToggleState == ToggleState.On;

    private static void RunFortnite()
    {
        Console.WriteLine("\n== Fortnite operations");
        Key(Vk.Home);
        WaitFor(() => _window.Current.Name == "FA11y - Home", 2000);
        Key(Vk.Down);
        WaitFor(() => _window.Current.Name == "FA11y - Fortnite", 2000);
        Thread.Sleep(500);
        Key(Vk.Enter);
        Thread.Sleep(150);
        if (!Check(FocusedNow() == "Play", "Enter on the Fortnite page lands on Play"))
            return;

        for (var round = 1; round <= 2; round++)
        {
            Check(TabTo("Verify and repair"), "Tab reaches Verify and repair");
            var sw = Stopwatch.StartNew();
            Key(Vk.Enter);
            Check(WaitFor(() => FocusedNow() == "Cancel", 3000), "starting an operation puts focus on Cancel");
            var bar = _window.FindFirst(TreeScope.Descendants, new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.ProgressBar),
                new PropertyCondition(AutomationElement.NameProperty, "Progress")));
            Check(bar != null, "a progress bar named \"Progress\" is shown");
            if (bar != null && round == 1)
            {
                Check(WaitFor(() => bar.TryGetCurrentPattern(RangeValuePattern.Pattern, out var p)
                                     && ((RangeValuePattern)p).Current.Value >= 25, 3000),
                    "the progress bar's value follows the core's progress");
                var text = _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Text))
                    .Cast<AutomationElement>().Select(e => e.Current.Name).ToList();
                Check(text.Any(t => t.StartsWith("Verifying files")), "the progress message is readable text");
            }
            if (round == 1)
            {
                Check(WaitFor(() => FocusedNow() == "Play", 8000), "when the operation finishes focus lands on Play");
                Check(_window.FindFirst(TreeScope.Descendants, new PropertyCondition(AutomationElement.NameProperty, "Progress")) == null,
                    "the progress bar is gone afterwards");
            }
            else
            {
                Thread.Sleep(700);
                Key(Vk.Enter); // Cancel
                Check(WaitFor(() => FocusedNow() == "Play", 3000) && sw.ElapsedMilliseconds < 2400,
                    $"Cancel ends the operation early and focus lands on Play ({sw.ElapsedMilliseconds} ms)");
            }
        }

        Key(Vk.Escape);
        Thread.Sleep(150);
        Check(InSidebar(AutomationElement.FocusedElement), "Escape on the Fortnite page returns to the sidebar");
        Key(Vk.Home);
        WaitFor(() => _window.Current.Name == "FA11y - Home", 2000);
    }

    // First-run setup -----------------------------------------------------------------------

    private static void RunSetupSession(string python, string? fakeCore, string root)
    {
        Console.WriteLine("\n== First-run setup");
        fakeCore ??= FindFakeCore();
        var log = Path.Combine(root, "fake-core-setup.log");
        var core = new Process
        {
            StartInfo = new ProcessStartInfo(python, $"\"{fakeCore}\" --root \"{root}\" --log \"{log}\" --first-run --fortnite egl")
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
        try
        {
            if (!lines.TryTake(out var started, 15000) || !started.StartsWith("STARTED "))
            {
                Check(false, "the test core started the window for setup");
                return;
            }
            var uiPid = int.Parse(started.Split(' ')[1]);
            _uiPid = uiPid;
            AutomationElement? window = null;
            var sw = Stopwatch.StartNew();
            while (sw.ElapsedMilliseconds < 15000 && (window == null || window.Current.IsOffscreen))
            {
                window = FindWindow(uiPid);
                Thread.Sleep(20);
            }
            if (!Check(window != null, "the setup window appeared"))
                return;
            _window = window!;
            lines.TryTake(out _, 15000); // READY
            Thread.Sleep(1500);
            if (!_keys)
            {
                WalkSetupStatic(log);
                return;
            }
            if (Foreground() != Handle(_window))
            {
                core.StandardInput.WriteLine("summon");
                WaitFor(() => Foreground() == Handle(_window), 3000);
                Thread.Sleep(300);
            }
            WalkSetup(root, log);
        }
        finally
        {
            try { core.StandardInput.WriteLine("quit"); } catch { /* gone */ }
            if (!core.WaitForExit(5000))
                core.Kill(true);
        }
    }

    private static void WalkSetup(string root, string log)
    {
        Check(_window.Current.Name == "FA11y setup", $"the window is titled \"FA11y setup\" (is \"{_window.Current.Name}\")");
        Check(_window.FindFirst(TreeScope.Descendants, new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.List),
                new PropertyCondition(AutomationElement.NameProperty, "Pages"))) == null,
            "the sidebar is not in the tree during setup");

        var intro = AutomationElement.FocusedElement;
        Check(intro.Current.ControlType == ControlType.Text && Safe(intro).StartsWith("Welcome to FA11y. FA11y makes Fortnite playable"),
            $"step 1 starts with its intro as the focused text (is \"{Clip(Safe(intro))}\")");
        Check(intro.Current.HelpText == "Setup: step 1 of 8", $"the intro is described as \"Setup: step 1 of 8\" (is \"{intro.Current.HelpText}\")");
        var stops = TabStops();
        Check(Names(stops).EndsWith("Skip setup | Next") && stops.Count == 3, $"step 1 tab order: intro, Skip setup, Next (is {Names(stops)})");

        foreach (var (name, key) in new[] { ("Skip setup", "Alt+K"), ("Next", "Alt+N") })
        {
            var button = stops.FirstOrDefault(e => e.Current.Name == name);
            Check(button?.Current.AccessKey == key, $"{name} has the access key {key} (is \"{button?.Current.AccessKey}\")");
        }
        Check(TabTo("Skip setup"), "step 1: Tab reaches Skip setup");
        Key(Vk.Right);
        Thread.Sleep(100);
        Check(FocusedNow() == "Next", $"Right arrow follows Tab order to Next (is \"{FocusedNow()}\")");
        Key(Vk.Left);
        Thread.Sleep(100);
        Check(FocusedNow() == "Skip setup", $"Left arrow returns to Skip setup (is \"{FocusedNow()}\")");
        Key(Vk.Up);
        Thread.Sleep(100);
        Check(FocusedNow().StartsWith("Welcome to FA11y"), $"Up arrow goes to the previous stop and does not leave setup (is \"{Clip(FocusedNow())}\")");

        Advance("Sign in to Epic Games.", 2);
        stops = TabStops();
        Check(Names(stops).Contains("Signed in as TestPlayer. | Sign in with a different account | Skip setup | Back | Next"),
            $"step 2 tab order: intro, status, sign in, Skip, Back, Next (is {Names(stops)})");

        Advance("Fortnite.", 3);
        Check(WaitFor(() => FocusedNow().StartsWith("Fortnite. Fortnite is installed through the Epic Games Launcher"), 3000),
            $"step 3 says what it found (is \"{Clip(FocusedNow())}\")");
        stops = TabStops();
        Check(Names(stops).Contains("Let FA11y manage it (recommended)") && Names(stops).Contains("Skip setup | Back | Next"),
            $"step 3 offers the Epic Games Launcher choice (is {Names(stops)})");
        Check(TabTo(stops[1].Current.Name), "Tab reaches the first choice");
        Check(IsSelected(AutomationElement.FocusedElement), "Let FA11y manage it is chosen by default");
        Key(Vk.Down);
        Thread.Sleep(100);
        Check(FocusedNow().StartsWith("Keep using the Epic Games Launcher") && IsSelected(AutomationElement.FocusedElement),
            "Down arrow chooses the next option and keeps focus on it");
        Key(Vk.Up);
        Thread.Sleep(100);
        Check(FocusedNow().StartsWith("Let FA11y manage it") && IsSelected(AutomationElement.FocusedElement), "Up arrow goes back");
        BackToIntro();

        Advance("Starting FA11y.", 4);
        stops = TabStops();
        Check(Names(stops).Contains("Start Fortnite when FA11y opens | Hide this window when Fortnite starts | Play navigation sounds in this window | Ask me | Skip setup"),
            $"step 4 tab order (is {Names(stops)})");
        Check(_window.FindFirst(TreeScope.Descendants, new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Group),
                new PropertyCondition(AutomationElement.NameProperty, "When I close the FA11y window"))) != null,
            "the close choices are in a group named \"When I close the FA11y window\"");
        Check(TabTo("Start Fortnite when FA11y opens"), "step 4: Tab reaches the first check box");
        Key(Vk.Down);
        Thread.Sleep(100);
        Check(FocusedNow() == "Hide this window when Fortnite starts", $"Down arrow moves to the next check box (is \"{FocusedNow()}\")");
        Key(Vk.Up);
        Thread.Sleep(100);
        Check(FocusedNow() == "Start Fortnite when FA11y opens", $"Up arrow moves back (is \"{FocusedNow()}\")");
        Check(TabTo("Ask me"), "Tab reaches the close choices");
        Key(Vk.Down);
        Thread.Sleep(100);
        Check(FocusedNow() == "Keep running in the tray" && IsSelected(AutomationElement.FocusedElement), "Down chooses Keep running in the tray");
        BackToIntro();

        Advance("Speech preferences.", 5);
        Check(TabTo("Verbose: full sentences, more context (recommended for new users)"), "step 5: Tab reaches the speech choice");
        Key(Vk.Down);
        Thread.Sleep(100);
        Check(FocusedNow().StartsWith("Simplified") && IsSelected(AutomationElement.FocusedElement), "Down chooses Simplified");
        BackToIntro();

        Advance("Audio check.", 6);
        stops = TabStops();
        Check(Names(stops).Contains("Master volume | Test sound | Skip setup | Back | Next"), $"step 6 tab order (is {Names(stops)})");
        var volume = stops.First(e => e.Current.Name == "Master volume");
        Check(volume.Current.ControlType == ControlType.Edit && volume.Current.HelpText == "Master volume, 0 to 100 percent.",
            "Master volume is an edit box with its help text");
        BackToIntro();

        Advance("Mouse setup.", 7);
        stops = TabStops();
        Check(Names(stops).Contains("Mouse DPI | Enable mouse passthrough (recommended) | Skip setup | Back | Next"),
            $"step 7 tab order (is {Names(stops)})");
        BackToIntro();

        Advance("All set.", 8);
        Check(_window.FindFirst(TreeScope.Descendants, new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Button),
                new PropertyCondition(AutomationElement.NameProperty, "Finish"))) != null, "the last step has a Finish button");

        // Escape asks to skip; Escape on that question stays in setup.
        Key(Vk.Escape);
        var dialog = (AutomationElement?)null;
        Check(WaitFor(() => (dialog = FindDialog("Skip setup")) != null, 3000), "Escape asks whether to skip setup");
        if (dialog != null)
        {
            Thread.Sleep(300);
            Check(Foreground() == Handle(dialog), "the question is in front");
            KeyRaw(Vk.Escape);
            Check(WaitFor(() => FindDialog("Skip setup") == null, 3000), "Escape on the question closes it");
            Thread.Sleep(300);
            Check(_window.Current.Name == "FA11y setup", "still in setup after answering no");
        }

        Check(WaitFor(() => Foreground() == Handle(_window), 2000), "the setup window has the foreground again");
        Key(Vk.Enter); // the default button: Finish
        Check(WaitFor(() => _window.Current.Name == "FA11y - Home", 3000), "Finish goes back to the pages");
        Thread.Sleep(300);
        var focused = AutomationElement.FocusedElement;
        Check(InSidebar2(focused) && Safe(focused) == "Home", $"focus is on the sidebar item Home (is \"{Safe(focused)}\")");
        Thread.Sleep(500);
        string text;
        using (var stream = new FileStream(log, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
        using (var reader = new StreamReader(stream))
            text = reader.ReadToEnd();
        var finish = text.Split('\n').FirstOrDefault(l => l.Contains("request setup.finish")) ?? "";
        Check(finish.Contains("'save': True") && finish.Contains("'close_action': 'tray'")
              && finish.Contains("'simplified_speech': True") && finish.Contains("'egl': 'manage'")
              && finish.Contains("'volume': 100") && finish.Contains("'dpi': 800"),
            $"the core received the answers (got: {Clip(finish)})");
    }

    private static bool InSidebar2(AutomationElement? el)
    {
        try
        {
            _pagesList = _window.FindFirst(TreeScope.Descendants, new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.List),
                new PropertyCondition(AutomationElement.NameProperty, "Pages")))!;
            return _pagesList != null && InSidebar(el);
        }
        catch
        {
            return false;
        }
    }

    /// <summary>Press Enter on the intro (the default button is Next) and wait for the next step's intro to have focus.</summary>
    private static void Advance(string titlePrefix, int step)
    {
        Key(Vk.Enter);
        var ok = WaitFor(() => FocusedNow().StartsWith(titlePrefix), 3000);
        Check(ok, $"Next shows step {step} with its intro focused (is \"{Clip(FocusedNow())}\")");
        var intro = AutomationElement.FocusedElement;
        Check(intro.Current.HelpText == $"Setup: step {step} of 8", $"step {step} is described as \"Setup: step {step} of 8\"");
    }

    /// <summary>Shift+Tab back to the intro of the current step, so Enter (Next) works from there.</summary>
    private static void BackToIntro()
    {
        for (var i = 0; i < 20; i++)
        {
            var el = AutomationElement.FocusedElement;
            if (el.Current.ControlType == ControlType.Text && el.Current.Name.Contains(". "))
                return;
            KeyWith(Vk.Tab, Vk.Shift);
            Thread.Sleep(60);
        }
    }

    private static AutomationElement? FindDialog(string title)
    {
        // A dialog owned by the window shows up under that window, not under the desktop.
        var named = new PropertyCondition(AutomationElement.NameProperty, title);
        return AutomationElement.RootElement.FindAll(TreeScope.Children, named)
            .Cast<AutomationElement>().FirstOrDefault(e => e.Current.ProcessId == _window.Current.ProcessId)
            ?? _window.FindAll(TreeScope.Children, new AndCondition(named,
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Window))).Cast<AutomationElement>().FirstOrDefault();
    }

    /// <summary>A key press for a window other than the main one (the caller has checked who is in front).</summary>
    private static void KeyRaw(Vk key)
    {
        Send(key, false);
        Send(key, true);
    }
}
