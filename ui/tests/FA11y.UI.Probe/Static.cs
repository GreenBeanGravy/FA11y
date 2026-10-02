using System.Diagnostics;
using System.IO;
using System.Windows.Automation;

namespace FA11y.UI.Probe;

/// <summary>
/// The same checks as the keyboard run, for a session with no foreground window (nobody at the
/// desktop): the tab order is read from the tree and buttons are pressed with UI Automation, so
/// names, roles, order and the core's replies are checked, but not where focus lands.
/// </summary>
internal static partial class Program
{
    private static List<AutomationElement> Focusables() =>
        _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.IsKeyboardFocusableProperty, true))
            .Cast<AutomationElement>().Where(e => IsPageStop(e)).ToList();

    // The title bar and the sidebar aren't the page; of a group of radio buttons only the chosen one is a tab stop.
    private static bool IsPageStop(AutomationElement e)
    {
        var type = e.Current.ControlType;
        if (type == ControlType.ListItem || type == ControlType.MenuBar || type == ControlType.Menu
            || type == ControlType.MenuItem || type == ControlType.List || e.Current.Name is "System" or "System Menu Bar")
            return false;
        return type != ControlType.RadioButton || IsSelected(e);
    }

    private static string ReadLog(string path)
    {
        using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }

    private static AutomationElement? Find(string name, ControlType type) =>
        _window.FindFirst(TreeScope.Descendants, new AndCondition(
            new PropertyCondition(AutomationElement.ControlTypeProperty, type),
            new PropertyCondition(AutomationElement.NameProperty, name)));

    private static void Press(string name)
    {
        var button = Find(name, ControlType.Button);
        if (button == null || !button.TryGetCurrentPattern(InvokePattern.Pattern, out var p))
        {
            Check(false, $"a button named \"{name}\" can be pressed");
            return;
        }
        ((InvokePattern)p).Invoke();
    }

    private static void RunStatic(Process core)
    {
        Console.WriteLine("\n== Fortnite page (static)");
        Info("No keys are typed in this mode: the tab order comes from the tree and focus is not checked.");
        core.StandardInput.WriteLine("show-page fortnite");
        Check(WaitFor(() => _window.Current.Name == "FA11y - Fortnite", 3000), "the Fortnite page is shown");
        Thread.Sleep(900);
        var stops = Focusables();
        Console.WriteLine("   " + Names(stops));
        CheckFortnitePage(stops, stops.Select(e => e.Current.Name).ToList());
        var underscores = _window.FindAll(TreeScope.Descendants, Condition.TrueCondition).Cast<AutomationElement>()
            .Select(e => { try { return e.Current.Name; } catch { return ""; } }).Where(n => n.Contains('_')).ToList();
        Check(underscores.Count == 0, $"no access key underscores in any name ({string.Join(", ", underscores.Select(Clip))})");

        for (var round = 1; round <= 2; round++)
        {
            var sw = Stopwatch.StartNew();
            Press("Verify and repair");
            Check(WaitFor(() => Find("Cancel", ControlType.Button) != null, 3000), "starting an operation shows Cancel");
            Check(Find("Verify and repair", ControlType.Button) == null, "the action buttons are hidden while it runs");
            var bar = _window.FindFirst(TreeScope.Descendants, new AndCondition(
                new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.ProgressBar),
                new PropertyCondition(AutomationElement.NameProperty, "Progress")));
            Check(bar != null, "a progress bar named \"Progress\" is shown");
            if (round == 1)
            {
                if (bar != null)
                    Check(WaitFor(() => bar.TryGetCurrentPattern(RangeValuePattern.Pattern, out var p)
                                         && ((RangeValuePattern)p).Current.Value >= 25, 3000),
                        "the progress bar's value follows the core's progress");
                Check(_window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.Text))
                        .Cast<AutomationElement>().Any(e => e.Current.Name.StartsWith("Verifying files")),
                    "the progress message is readable text");
                Check(WaitFor(() => Find("Cancel", ControlType.Button) == null, 8000), "the operation finishes and Cancel goes away");
                Check(WaitFor(() => Find("Verify and repair", ControlType.Button) != null, 3000), "the action buttons come back");
            }
            else
            {
                Thread.Sleep(700);
                Press("Cancel");
                sw.Restart();
                // Left alone the operation would take another second or so; cancelled it ends within one step.
                Check(WaitFor(() => Find("Cancel", ControlType.Button) == null, 3000) && sw.ElapsedMilliseconds < 1500,
                    $"Cancel ends the operation early ({sw.ElapsedMilliseconds} ms)");
            }
        }
    }

    private static void WalkSetupStatic(string log)
    {
        Info("No keys are typed in this mode: the tab order comes from the tree and focus is not checked.");
        Check(_window.Current.Name == "FA11y setup", $"the window is titled \"FA11y setup\" (is \"{_window.Current.Name}\")");
        Check(Find("Pages", ControlType.List) == null, "the sidebar is not in the tree during setup");

        void Step(int number, string titlePrefix, string? tabOrder)
        {
            if (number > 1)
            {
                Press("Next");
                Check(WaitFor(() => Focusables().FirstOrDefault()?.Current.Name.StartsWith(titlePrefix) == true, 5000),
                    $"Next shows step {number}");
                Thread.Sleep(400);
            }
            var stops = Focusables();
            var intro = stops[0];
            Check(intro.Current.ControlType == ControlType.Text && intro.Current.Name.StartsWith(titlePrefix),
                $"step {number} starts with its intro as the first tab stop (is \"{Clip(intro.Current.Name)}\")");
            Check(intro.Current.HelpText == $"Setup: step {number} of 8", $"step {number} is described as \"Setup: step {number} of 8\" (is \"{intro.Current.HelpText}\")");
            if (tabOrder != null)
                Check(Names(stops).Contains(tabOrder), $"step {number} tab order contains \"{tabOrder}\" (is {Names(stops)})");
            Check(stops.Last().Current.Name == (number == 8 ? "Finish" : "Next"), $"step {number} ends with {(number == 8 ? "Finish" : "Next")}");
            Check((number == 1) == (Find("Back", ControlType.Button) == null), "Back is hidden on the first step only");
        }

        Step(1, "Welcome to FA11y. FA11y makes Fortnite playable", "Skip setup | Next");
        Step(2, "Sign in to Epic Games.", "Signed in as TestPlayer. | Sign in with a different account | Skip setup | Back | Next");
        Step(3, "Fortnite.", null);
        Check(WaitFor(() => Focusables()[0].Current.Name.StartsWith("Fortnite. Fortnite is installed through the Epic Games Launcher"), 3000),
            "step 3 says what it found");
        var stops = Focusables();
        Check(Names(stops).Contains("Let FA11y manage it (recommended)") && Names(stops).Contains("Skip setup | Back | Next"),
            $"step 3 offers the Epic Games Launcher choice (is {Names(stops)})");
        var manage = stops.First(e => e.Current.Name.StartsWith("Let FA11y manage it"));
        Check(manage.Current.ControlType == ControlType.RadioButton && IsSelected(manage), "Let FA11y manage it is a radio button, chosen by default");
        Check(stops.Count(e => e.Current.ControlType == ControlType.RadioButton) == 1, "only the chosen option is a tab stop");
        var keep = _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.RadioButton))
            .Cast<AutomationElement>().First(e => e.Current.Name.StartsWith("Keep using the Epic Games Launcher"));
        Check(Find("How should Fortnite be managed?", ControlType.Group) != null, "the choices are in a group named \"How should Fortnite be managed?\"");
        ((SelectionItemPattern)keep.GetCurrentPattern(SelectionItemPattern.Pattern)).Select();
        Check(IsSelected(keep) && !IsSelected(manage), "choosing the other option unchooses the first");
        ((SelectionItemPattern)manage.GetCurrentPattern(SelectionItemPattern.Pattern)).Select();

        Step(4, "Starting FA11y.",
            "Start Fortnite when FA11y opens | Hide this window when Fortnite starts | Play navigation sounds in this window | Ask me | Skip setup");
        Check(Find("When I close the FA11y window", ControlType.Group) != null, "the close choices are in a group named \"When I close the FA11y window\"");
        var tray = _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.RadioButton))
            .Cast<AutomationElement>().First(e => e.Current.Name == "Keep running in the tray");
        ((SelectionItemPattern)tray.GetCurrentPattern(SelectionItemPattern.Pattern)).Select();

        Step(5, "Speech preferences.", "Verbose: full sentences, more context (recommended for new users) | Skip setup");
        var simplified = _window.FindAll(TreeScope.Descendants, new PropertyCondition(AutomationElement.ControlTypeProperty, ControlType.RadioButton))
            .Cast<AutomationElement>().First(e => e.Current.Name.StartsWith("Simplified"));
        ((SelectionItemPattern)simplified.GetCurrentPattern(SelectionItemPattern.Pattern)).Select();

        Step(6, "Audio check.", "Master volume | Test sound | Skip setup | Back | Next");
        var volume = Find("Master volume", ControlType.Edit);
        Check(volume != null && volume.Current.HelpText == "Master volume, 0 to 100 percent.", "Master volume is an edit box with its help text");
        Step(7, "Mouse setup.", "Mouse DPI | Enable mouse passthrough (recommended) | Skip setup | Back | Next");
        Step(8, "All set.", "Skip setup | Back | Finish");

        Press("Finish");
        Check(WaitFor(() => _window.Current.Name == "FA11y - Home", 3000), "Finish goes back to the pages");
        Check(WaitFor(() => Find("Pages", ControlType.List) != null, 2000), "the sidebar is back");
        Thread.Sleep(600);
        var finish = ReadLog(log).Split('\n').FirstOrDefault(l => l.Contains("request setup.finish")) ?? "";
        Check(finish.Contains("'save': True") && finish.Contains("'close_action': 'tray'")
              && finish.Contains("'simplified_speech': True") && finish.Contains("'egl': 'manage'")
              && finish.Contains("'volume': 100") && finish.Contains("'dpi': 800"),
            $"the core received the answers (got: {Clip(finish)})");
    }
}
