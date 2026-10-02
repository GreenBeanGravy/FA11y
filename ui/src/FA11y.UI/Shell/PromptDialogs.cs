using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using FA11y.UI.Controls;
using FA11y.UI.Core;

namespace FA11y.UI.Shell;

/// <summary>
/// Questions a page asks the user: a message with OK, a line of text, or one choice from a list.
/// They look and behave like <see cref="DialogWindow"/>: the prompt is announced when the dialog opens,
/// the input has focus, Enter answers and Escape cancels.
/// </summary>
public static class Prompts
{
    /// <summary>A message with an OK button.</summary>
    public static void Message(Window? owner, string title, string message)
    {
        var dialog = new DialogWindow(owner, title, message);
        dialog.AddButton("ok", "_OK", isDefault: true);
        dialog.ShowDialog();
    }

    /// <summary>Ask for a line of text. Returns null when cancelled.</summary>
    public static string? Ask(Window? owner, string title, string prompt, string initial = "")
    {
        var box = new TextBox { Text = initial, Margin = new Thickness(0, 12, 0, 0), MinWidth = 320 };
        AutomationProperties.SetName(box, prompt);
        box.SelectAll();
        var window = new PromptWindow(owner, title, prompt, box, box);
        return window.ShowDialog() == true ? box.Text : null;
    }

    /// <summary>Ask which of the choices is wanted. Returns its index, or -1 when cancelled.</summary>
    public static int Choose(Window? owner, string title, string prompt, IReadOnlyList<string> choices)
    {
        var list = new ListBox
        {
            Margin = new Thickness(0, 12, 0, 0),
            MaxHeight = 280,
            ItemsSource = choices,
        };
        AutomationProperties.SetName(list, title);
        KeyboardNavigation.SetTabNavigation(list, KeyboardNavigationMode.Once);
        list.SelectedIndex = 0;
        var window = new PromptWindow(owner, title, prompt, list, null);
        window.Loaded += (_, _) =>
        {
            if (list.ItemContainerGenerator.ContainerFromIndex(0) is ListBoxItem first)
                first.Focus();
        };
        list.MouseDoubleClick += (_, e) =>
        {
            if (e.OriginalSource is DependencyObject source && ItemsControl.ContainerFromElement(list, source) != null)
                window.DialogResult = true;
        };
        return window.ShowDialog() == true ? list.SelectedIndex : -1;
    }
}

/// <summary>The window behind <see cref="Prompts"/>: a prompt, one input control, and OK and Cancel.</summary>
internal sealed class PromptWindow : Window
{
    private readonly string _prompt;

    public PromptWindow(Window? owner, string title, string prompt, UIElement input, TextBox? textInput)
    {
        Style = (Style)Application.Current.FindResource("AppWindow");
        Title = title;
        _prompt = prompt;
        SizeToContent = SizeToContent.WidthAndHeight;
        ResizeMode = ResizeMode.NoResize;
        ShowInTaskbar = false;
        WindowTools.UseDarkTitleBar(this);
        if (owner != null && owner.IsVisible)
        {
            Owner = owner;
            WindowStartupLocation = WindowStartupLocation.CenterOwner;
        }
        else
        {
            WindowStartupLocation = WindowStartupLocation.CenterScreen;
        }

        var ok = new IconButton { Content = "_OK", Variant = "primary", IsDefault = true, Margin = new Thickness(0, 0, 8, 0) };
        ok.Click += (_, _) => DialogResult = true;
        var cancel = new IconButton { Content = "_Cancel", IsCancel = true };
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 16, 0, 0) };
        buttons.Children.Add(ok);
        buttons.Children.Add(cancel);

        var message = new ReadableText { Text = prompt, Padding = new Thickness(3) };
        var panel = new StackPanel { Margin = new Thickness(16), MinWidth = 380, MaxWidth = 460 };
        panel.Children.Add(message);
        panel.Children.Add(input);
        panel.Children.Add(buttons);
        Content = panel;

        PreviewKeyDown += (_, e) =>
        {
            if (e.Key == Key.Escape)
            {
                e.Handled = true;
                DialogResult = false;
            }
        };
        Loaded += (_, _) =>
        {
            if (textInput != null)
            {
                textInput.Focus();
                textInput.SelectAll();
            }
            Announcer.Announce(this, _prompt, important: true);
        };
    }
}
