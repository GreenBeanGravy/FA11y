using System.Windows.Automation;
using System.Windows.Controls;

namespace FA11y.UI.Shell;

/// <summary>
/// What the window shows while FA11y starts: a spinner, a progress bar and one line saying what is
/// happening. The bar is the only thing a screen reader reaches: its name is "Starting FA11y", its
/// value is the percent and its help text is the line.
/// </summary>
public partial class StartupView : UserControl
{
    public StartupView()
    {
        InitializeComponent();
        Set(0, "");
    }

    public void Set(int percent, string message)
    {
        // Progress only goes up.
        if (percent > Bar.Value)
            Bar.Value = Math.Min(percent, 100);
        Status.Text = message;
        AutomationProperties.SetHelpText(Bar, message);
    }

    public bool FocusBar() => Bar.Focus();
}
