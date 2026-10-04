using System.Windows;
using System.Windows.Automation;
using System.Windows.Input;
using FA11y.UI.Controls;
using FA11y.UI.Core;

namespace FA11y.UI.Shell;

/// <summary>
/// A small dark dialog with a message and buttons. The default button has focus when it opens; the
/// message is also announced, since NVDA reads a focused button but not the text above it.
/// Escape closes it with the cancel result.
/// </summary>
public partial class DialogWindow : Window
{
    private IconButton? _default;
    private string _message = "";

    public DialogWindow(Window? owner, string title, string message)
    {
        InitializeComponent();
        WindowTools.UseDarkTitleBar(this);
        Title = title;
        _message = message;
        MessageText.Text = message;
        if (owner != null && owner.IsVisible)
            Owner = owner;
        else
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
        Loaded += OnLoaded;
        PreviewKeyDown += (_, e) =>
        {
            if (e.Key == Key.Escape)
            {
                e.Handled = true;
                DialogResult = false;
            }
            else
            {
                ArrowNavigation.TryMove(e, this);
            }
        };
    }

    /// <summary>Which button was pressed, or null when the dialog was dismissed.</summary>
    public string? Result { get; private set; }

    public bool OptionChecked => OptionBox.IsChecked == true;

    public void AddOption(string text, bool isChecked)
    {
        OptionBox.Content = text;
        OptionBox.IsChecked = isChecked;
        OptionBox.Visibility = Visibility.Visible;
    }

    public void AddButton(string id, string label, bool isDefault = false, string variant = "secondary")
    {
        var button = new IconButton { Content = label, Variant = isDefault && variant == "secondary" ? "primary" : variant };
        if (ButtonRow.Children.Count > 0)
            button.Margin = new Thickness(8, 0, 0, 0);
        button.Click += (_, _) =>
        {
            Result = id;
            DialogResult = true;
        };
        if (isDefault)
        {
            button.IsDefault = true;
            _default = button;
        }
        ButtonRow.Children.Add(button);
    }

    private void OnLoaded(object sender, RoutedEventArgs e)
    {
        var target = _default ?? ButtonRow.Children.OfType<IconButton>().FirstOrDefault();
        if (target == null)
            return;
        target.Focus();
        Announcer.Announce(this, _message, important: true);
    }
}

/// <summary>The dialogs the window asks the user questions with.</summary>
public static class Dialogs
{
    public const string Tray = "tray";
    public const string Quit = "quit";

    /// <summary>Asked when the window is closed and the close action is "ask". Returns tray, quit, or null for cancel.</summary>
    public static (string? Action, bool Remember) AskClose(Window? owner)
    {
        var dialog = new DialogWindow(owner, "Keep FA11y running?",
            "FA11y's keybinds only work while FA11y is running. You can keep it running in the system tray, or quit it now.");
        dialog.AddOption("Don't ask again", true);
        dialog.AddButton(Quit, "Quit FA11y");
        dialog.AddButton(Tray, "Hide to tray", isDefault: true);
        return dialog.ShowDialog() == true ? (dialog.Result, dialog.OptionChecked) : (null, false);
    }

    /// <summary>A yes or no question. The default answer is No unless defaultYes.</summary>
    public static bool Confirm(Window? owner, string title, string message, bool defaultYes = false)
    {
        var dialog = new DialogWindow(owner, title, message);
        dialog.AddButton("yes", "Yes", isDefault: defaultYes);
        dialog.AddButton("no", "No", isDefault: !defaultYes);
        return dialog.ShowDialog() == true && dialog.Result == "yes";
    }
}
