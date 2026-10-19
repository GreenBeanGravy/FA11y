using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Input;
using FA11y.UI.Controls;
using FA11y.UI.Core;

namespace FA11y.UI.Shell;

/// <summary>
/// Questions a page asks the user: a message with OK, a line of text, one choice from a list, several
/// choices as check boxes, or a list to read before pressing one of a few buttons. They look and behave
/// like <see cref="DialogWindow"/>: the prompt is announced when the dialog opens, the input has focus,
/// Enter answers and Escape cancels.
/// </summary>
public static class Prompts
{
    /// <summary>A message with an OK button.</summary>
    public static void Message(Window? owner, string title, string message)
    {
        var dialog = new DialogWindow(owner, title, message);
        dialog.AddButton("ok", "OK", isDefault: true);
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

    /// <summary>Ask which of the choices are wanted, as check boxes. Returns the checked indexes, or null when cancelled.</summary>
    public static IReadOnlyList<int>? Pick(Window? owner, string title, string prompt, IReadOnlyList<string> choices)
    {
        var boxes = choices.Select(c => new CheckOption { Content = c, Margin = new Thickness(0, 0, 0, 4) }).ToList();
        var panel = new StackPanel();
        foreach (var box in boxes)
            panel.Children.Add(box);
        var scroll = new ScrollViewer
        {
            Margin = new Thickness(0, 12, 0, 0),
            MaxHeight = 320,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
            Focusable = false,
            Content = panel,
        };
        var window = new PromptWindow(owner, title, prompt, scroll, null);
        window.Loaded += (_, _) => boxes.FirstOrDefault()?.Focus();
        if (window.ShowDialog() != true)
            return null;
        return Enumerable.Range(0, boxes.Count).Where(i => boxes[i].IsChecked == true).ToList();
    }

    /// <summary>
    /// Show a list to read (arrow keys move through it) and buttons, the first one the default. Returns the id
    /// of the button pressed, or null when cancelled. A button with the id "cancel" also closes it.
    /// </summary>
    public static string? Review(Window? owner, string title, string prompt, IReadOnlyList<string> lines,
        IReadOnlyList<(string Id, string Label)> buttons)
    {
        ListBox? list = null;
        if (lines.Count > 0)
        {
            list = new ListBox { Margin = new Thickness(0, 12, 0, 0), MaxHeight = 280, ItemsSource = lines };
            AutomationProperties.SetName(list, title);
            KeyboardNavigation.SetTabNavigation(list, KeyboardNavigationMode.Once);
            list.SelectedIndex = 0;
        }
        var window = new PromptWindow(owner, title, prompt, list, null, buttons);
        window.Loaded += (_, _) =>
        {
            if (list?.ItemContainerGenerator.ContainerFromIndex(0) is ListBoxItem first)
                first.Focus();
        };
        return window.ShowDialog() == true ? window.Result : null;
    }
}

/// <summary>The window behind <see cref="Prompts"/>: a prompt, one input control, and OK and Cancel (or the given buttons).</summary>
internal sealed class PromptWindow : Window
{
    private readonly string _prompt;

    /// <summary>The id of the button that closed the window, when it was given buttons.</summary>
    public string? Result { get; private set; }

    public PromptWindow(Window? owner, string title, string prompt, UIElement? input, TextBox? textInput,
        IReadOnlyList<(string Id, string Label)>? choices = null)
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

        var buttons = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 16, 0, 0) };
        foreach (var (id, label) in choices ?? new[] { ("ok", "OK"), ("cancel", "Cancel") })
        {
            var first = buttons.Children.Count == 0;
            var button = new IconButton
            {
                Content = label,
                Variant = first ? "primary" : "secondary",
                IsDefault = first,
                IsCancel = id == "cancel",
                Margin = new Thickness(first ? 0 : 8, 0, 0, 0),
            };
            button.Click += (_, _) =>
            {
                Result = id;
                DialogResult = id != "cancel";
            };
            buttons.Children.Add(button);
        }

        var message = new ReadableText { Text = prompt, Padding = new Thickness(3) };
        var panel = new StackPanel { Margin = new Thickness(16), MinWidth = 380, MaxWidth = choices == null ? 460 : 560 };
        panel.Children.Add(message);
        if (input != null)
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
            else
            {
                ArrowNavigation.TryMove(e, this);
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
