using System.Windows;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;

namespace FA11y.UI.Controls;

/// <summary>
/// Makes the arrow keys follow Tab order in a view made of buttons, check boxes and text. WPF's own
/// arrow navigation is spatial (Left from a button may jump anywhere), which a screen reader user
/// cannot predict. Call <see cref="TryMove"/> from a PreviewKeyDown handler.
/// </summary>
public static class ArrowNavigation
{
    /// <summary>
    /// Down and Right move to the next Tab stop, Up and Left to the previous one. Focus never leaves
    /// <paramref name="root"/>: at either end it stays where it is. Controls that use the arrows
    /// themselves are left alone: radio options, text boxes, combo boxes and lists.
    /// </summary>
    public static bool TryMove(KeyEventArgs e, UIElement root)
    {
        if (e.Handled || Keyboard.Modifiers != ModifierKeys.None)
            return false;
        var direction = e.Key switch
        {
            Key.Down or Key.Right => FocusNavigationDirection.Next,
            Key.Up or Key.Left => FocusNavigationDirection.Previous,
            _ => (FocusNavigationDirection?)null,
        };
        if (direction == null || Keyboard.FocusedElement is not FrameworkElement focused || !IsInside(focused, root))
            return false;
        for (DependencyObject? node = focused; node != null && node != root; node = Parent(node))
            if (node is RadioOption or RadioGroup or TextBoxBase or ComboBox or Selector)
                return false;

        e.Handled = true;
        focused.MoveFocus(new TraversalRequest(direction.Value));
        if (Keyboard.FocusedElement is not DependencyObject now || !IsInside(now, root))
            focused.Focus();
        return true;
    }

    private static bool IsInside(DependencyObject start, DependencyObject root)
    {
        for (DependencyObject? node = start; node != null; node = Parent(node))
            if (node == root)
                return true;
        return false;
    }

    private static DependencyObject? Parent(DependencyObject node) =>
        node is Visual ? VisualTreeHelper.GetParent(node) ?? LogicalTreeHelper.GetParent(node) : LogicalTreeHelper.GetParent(node);
}
