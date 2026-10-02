using System.Windows;
using System.Windows.Automation.Peers;
using System.Windows.Controls;

namespace FA11y.UI.Controls;

/// <summary>A radio button as one element, like <see cref="CheckOption"/>: no stray label text inside it.</summary>
public sealed class RadioOption : RadioButton
{
    static RadioOption()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(RadioOption), new FrameworkPropertyMetadata(typeof(RadioOption)));
    }

    protected override AutomationPeer OnCreateAutomationPeer() => new LeafRadioPeer(this);

    private sealed class LeafRadioPeer : RadioButtonAutomationPeer
    {
        public LeafRadioPeer(RadioOption owner) : base(owner) { }

        protected override List<AutomationPeer>? GetChildrenCore() => null;
    }
}
