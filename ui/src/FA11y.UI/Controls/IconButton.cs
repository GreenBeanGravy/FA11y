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
internal sealed class LeafButtonPeer : ButtonAutomationPeer
{
    public LeafButtonPeer(Button owner) : base(owner) { }

    protected override List<AutomationPeer>? GetChildrenCore() => null;

    // WPF reports a bare "N"; NVDA reads "Alt+N" from its own dialogs, so say it the same way.
    protected override string GetAccessKeyCore() => base.GetAccessKeyCore() is { Length: 1 } key ? "Alt+" + key : base.GetAccessKeyCore();
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
