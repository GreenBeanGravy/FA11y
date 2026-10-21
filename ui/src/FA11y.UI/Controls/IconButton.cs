using System.Windows;
using System.Windows.Automation.Peers;
using System.Windows.Controls;
using System.Windows.Media;

namespace FA11y.UI.Controls;

/// <summary>
/// A button with an optional icon before its label. Variant picks the look:
/// "secondary" (default), "primary", "danger" or "ghost". Buttons carry no access keys, so screen
/// readers do not read one out, except setup's Back, Next, Finish and Skip ("_Next"), which screen
/// readers read as "Alt+N" like NVDA's own wizards.
/// </summary>
public class IconButton : Button
{
    public static readonly DependencyProperty IconProperty =
        DependencyProperty.Register(nameof(Icon), typeof(Geometry), typeof(IconButton));

    public static readonly DependencyProperty VariantProperty =
        DependencyProperty.Register(nameof(Variant), typeof(string), typeof(IconButton), new PropertyMetadata("secondary"));

    static IconButton()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(IconButton), new FrameworkPropertyMetadata(typeof(IconButton)));
    }

    public Geometry? Icon
    {
        get => (Geometry?)GetValue(IconProperty);
        set => SetValue(IconProperty, value);
    }

    public string Variant
    {
        get => (string)GetValue(VariantProperty);
        set => SetValue(VariantProperty, value);
    }

    protected override AutomationPeer OnCreateAutomationPeer() => new LeafButtonPeer(this);
}

/// <summary>A button as one element: its label's text (with the access key underscore) is not a separate item.</summary>
internal class LeafButtonPeer : ButtonAutomationPeer
{
    public LeafButtonPeer(Button owner) : base(owner) { }

    protected override List<AutomationPeer>? GetChildrenCore() => null;

    // WPF reports a bare "N"; NVDA reads "Alt+N" from its own dialogs, so say it the same way.
    // A default button (IsDefault) also registers Enter ("\r") as an access key, and WPF can hand
    // that back instead of the label's letter, so take the letter from the label then.
    protected override string GetAccessKeyCore()
    {
        var key = base.GetAccessKeyCore();
        if (key is { Length: 1 } && !char.IsControl(key[0])) return "Alt+" + key;
        if (Owner is ContentControl { Content: string label } && label.IndexOf('_') is var i and >= 0 && i + 1 < label.Length)
            return "Alt+" + label[i + 1];
        return key is { Length: 1 } ? string.Empty : key;
    }
}

/// <summary>A check box as one element, with the same rule: no stray label text inside it.</summary>
public sealed class CheckOption : CheckBox
{
    static CheckOption()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(CheckOption), new FrameworkPropertyMetadata(typeof(CheckOption)));
    }

    protected override AutomationPeer OnCreateAutomationPeer() => new LeafCheckPeer(this);

    private sealed class LeafCheckPeer : CheckBoxAutomationPeer
    {
        public LeafCheckPeer(CheckOption owner) : base(owner) { }

        protected override List<AutomationPeer>? GetChildrenCore() => null;
    }
}
