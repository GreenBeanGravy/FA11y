using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using FA11y.UI.Controls;
using FA11y.UI.Core;

namespace FA11y.UI.Shell;

/// <summary>
/// First-run setup, shown in the main window instead of the sidebar and pages. Eight steps with
/// Next, Back and Skip. Each step starts with one focusable text (its title and intro) that has
/// focus when the step appears. Escape asks to skip. The choices go to the core when setup
/// finishes (setup.finish), which writes them to the config.
/// </summary>
public partial class SetupView : UserControl
{
    private sealed record Step(string Title, string Intro, Panel Panel, ReadableText IntroText);

    private readonly List<Step> _steps = new();
    private int _index = -1;
    private bool _active;
    private bool _offerChoice;

    /// <summary>Raised when setup is over (finished or skipped); the window goes back to the pages.</summary>
    public event Action? Finished;

    public SetupView()
    {
        InitializeComponent();
        _steps.Add(new Step("Welcome to FA11y",
            "FA11y makes Fortnite playable with a screen reader. This short setup signs you in, finds Fortnite, and sets a few preferences. Press Tab to move between controls, and Next to continue. You can skip setup at any time.",
            WelcomeStep, WelcomeIntro));
        _steps.Add(new Step("Sign in to Epic Games",
            "Your Epic account is used for your locker, friends and party, quests, and for downloading and updating Fortnite. You can also sign in later on the Epic account page.",
            SignInStep, SignInIntro));
        _steps.Add(new Step("Fortnite", "Looking for Fortnite on this computer…", FortniteStep, FortniteIntro));
        _steps.Add(new Step("Starting FA11y",
            "FA11y opens this window when it starts, and its keybinds work in the background while it runs. Choose how the window behaves.",
            StartupStep, StartupIntro));
        _steps.Add(new Step("Speech preferences",
            "FA11y narrates events through your screen reader. Choose how talkative you want it to be. You can change this later in the configuration menu.",
            SpeechStep, SpeechIntro));
        _steps.Add(new Step("Audio check",
            "FA11y plays spatial audio cues for storms, points of interest, and dynamic objects. Use the Test button to play a sound at the current master volume, and adjust the slider until it's comfortable before you continue.",
            AudioStep, AudioIntro));
        _steps.Add(new Step("Mouse setup",
            "FA11y reads your mouse DPI to compute correct in-game sensitivity for its turn and look keys. Enter the DPI your mouse is set to. If you don't know, 800 is a safe default. You can fine-tune it later.",
            MouseStep, MouseIntro));
        _steps.Add(new Step("All set",
            "Setup is complete. Press Finish to start using FA11y. You can run setup again from the Settings page, and change any setting there.",
            DoneStep, DoneIntro));
        foreach (var step in _steps)
            ShowIntro(step, step.Intro);

        PreviewKeyDown += OnPreviewKeyDown;
    }

    public bool IsActive => _active;

    // Steps -------------------------------------------------------------------------

    /// <summary>Start from the first step. The step texts are the same every time; the answers start at their defaults.</summary>
    public void Begin()
    {
        _active = true;
        ResetAnswers();
        ShowIntro(_steps[2], _steps[2].Intro);
        _offerChoice = false;
        EglGroup.Visibility = Visibility.Collapsed;
        _ = LoadFortniteStep();
        Show(0);
    }

    private void ResetAnswers()
    {
        StartFortnite.IsChecked = false;
        HideOnLaunch.IsChecked = true;
        NavSounds.IsChecked = true;
        CloseGroup.SelectedIndex = 0;
        SpeechGroup.SelectedIndex = 0;
        EglGroup.SelectedIndex = 0;
        VolumeBox.Value = 100;
        DpiBox.Value = 800;
        PassthroughBox.IsChecked = true;
    }

    private static void ShowIntro(Step step, string intro)
    {
        step.IntroText.SetLines(
            new TextLine(step.Title, 18.6666667, FontWeights.Bold),
            new TextLine(intro, 0, null, null, 6));
    }

    private void Show(int index)
    {
        if (index < 0 || index >= _steps.Count)
            return;
        for (var i = 0; i < _steps.Count; i++)
            _steps[i].Panel.Visibility = i == index ? Visibility.Visible : Visibility.Collapsed;
        var changed = index != _index;
        _index = index;
        var counter = $"Setup: step {index + 1} of {_steps.Count}";
        StepCounter.Text = counter;
        System.Windows.Automation.AutomationProperties.SetHelpText(_steps[index].IntroText, counter);
        BackButton.Visibility = index > 0 ? Visibility.Visible : Visibility.Collapsed;
        NextButton.Content = index == _steps.Count - 1 ? "_Finish" : "_Next"; // Alt+N, Alt+B, Alt+F like NVDA's own wizards
        if (changed)
            App.Bridge.Notify("app.sound", new { name = "navigate" });
        UpdateLayout();
        FocusIntro();
        if (index == 1)
            _ = RefreshSignIn();
    }

    /// <summary>Focus the current step's first text, which reads its title and intro.</summary>
    public void FocusIntro()
    {
        if (_index < 0)
            return;
        var target = _steps[_index].IntroText;
        Dispatcher.BeginInvoke(DispatcherPriority.Input, () =>
        {
            if (!target.Focus())
                NextButton.Focus();
        });
    }

    private void OnNextClick(object sender, RoutedEventArgs e)
    {
        if (_index < _steps.Count - 1)
            Show(_index + 1);
        else
            Finish(save: true);
    }

    private void OnBackClick(object sender, RoutedEventArgs e) => Show(_index - 1);

    private void OnSkipClick(object sender, RoutedEventArgs e) => Skip();

    private void OnPreviewKeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Escape && Keyboard.Modifiers == ModifierKeys.None)
        {
            e.Handled = true;
            Skip();
            return;
        }
        // Arrow keys follow Tab order (a RadioGroup, text box or list keeps its own arrows).
        ArrowNavigation.TryMove(e, this);
    }

    private void Skip()
    {
        if (!_active)
            return;
        if (Dialogs.Confirm(Window.GetWindow(this), "Skip setup",
                "Skip setup? FA11y starts with default settings. You can run setup again from the Settings page.",
                defaultYes: true))
            Finish(save: false);
    }

    // The core ----------------------------------------------------------------------------

    private async Task RefreshSignIn()
    {
        try
        {
            var state = await App.Bridge.RequestAsync("setup.signin_state");
            SignInStatus.Text = state.Str("text");
            SignInButton.Content = state.Bool("signed_in") ? "Sign in with a different account" : "Sign in";
        }
        catch (Exception e)
        {
            Log.Error("setup.signin_state failed", e);
            SignInStatus.Text = "Not signed in.";
        }
    }

    private bool _signingIn;

    private async void OnSignInClick(object sender, RoutedEventArgs e)
    {
        if (_signingIn)
            return;
        _signingIn = true;
        try
        {
            // The sign in dialog is the core's (a wx dialog); this returns when it closes.
            await App.Bridge.RequestAsync("account.sign_in", null, Timeout.InfiniteTimeSpan);
            if (Window.GetWindow(this) is { } window && WindowTools.ForegroundIsFa11y(App.CoreProcessId))
                WindowTools.BringToFront(window);
        }
        catch (Exception ex)
        {
            Log.Error("account.sign_in failed", ex);
        }
        finally
        {
            _signingIn = false;
        }
        await RefreshSignIn();
        SignInButton.Focus();
    }

    private async Task LoadFortniteStep()
    {
        string message;
        var offer = false;
        try
        {
            var state = await App.Bridge.RequestAsync("setup.fortnite", null, TimeSpan.FromSeconds(120));
            message = state.Str("message");
            offer = state.Bool("offer_choice");
        }
        catch (Exception e)
        {
            Log.Error("setup.fortnite failed", e);
            message = "FA11y couldn't check for Fortnite. You can set it up on the Fortnite page later.";
        }
        if (!_active)
            return;
        _offerChoice = offer;
        EglGroup.Visibility = offer ? Visibility.Visible : Visibility.Collapsed;
        // A focused intro reports the new text to screen readers itself.
        ShowIntro(_steps[2], message);
    }

    private async void OnTestSoundClick(object sender, RoutedEventArgs e)
    {
        try
        {
            var result = await App.Bridge.RequestAsync("setup.test_sound", new { volume = VolumeBox.Value });
            var message = result.NullableStr("message");
            if (!string.IsNullOrEmpty(message))
                Announcer.Announce(Window.GetWindow(this) ?? (UIElement)this, message);
        }
        catch (Exception ex)
        {
            Log.Error("setup.test_sound failed", ex);
            Announcer.Announce(Window.GetWindow(this) ?? (UIElement)this, "Audio test failed.");
        }
    }

    private static readonly string[] CloseActions = { "ask", "tray", "quit" };

    private async void Finish(bool save)
    {
        if (!_active)
            return;
        var answers = new
        {
            start_fortnite = StartFortnite.IsChecked == true,
            hide_on_launch = HideOnLaunch.IsChecked == true,
            nav_sounds = NavSounds.IsChecked == true,
            close_action = CloseActions[Math.Max(0, CloseGroup.SelectedIndex)],
            simplified_speech = SpeechGroup.SelectedIndex == 1,
            volume = VolumeBox.Value,
            dpi = DpiBox.Value,
            passthrough = PassthroughBox.IsChecked == true,
        };
        string? egl = save && _offerChoice ? (EglGroup.SelectedIndex == 1 ? "sync" : "manage") : null;
        _active = false;
        // The window goes back to the pages at once; the core's follow-up (home, or the Fortnite
        // page for the Epic Games Launcher choice) arrives as events after that.
        Finished?.Invoke();
        try
        {
            await App.Bridge.RequestAsync("setup.finish", new { save, answers, egl }, TimeSpan.FromSeconds(60));
        }
        catch (Exception e)
        {
            Log.Error("setup.finish failed", e);
        }
    }
}
