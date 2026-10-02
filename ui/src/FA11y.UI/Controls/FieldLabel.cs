using System.Windows.Automation.Peers;
using System.Windows.Controls;

namespace FA11y.UI.Controls;

/// <summary>
/// The visible label of a field. Its access key (an underscore before a letter) moves focus to
/// its Target. Screen readers don't see it: the field carries its own name, and the label's text
/// would only add the underscore.
/// </summary>
public sealed class FieldLabel : Label
{
    protected override AutomationPeer OnCreateAutomationPeer() => new FieldLabelPeer(this);

    private sealed class FieldLabelPeer : FrameworkElementAutomationPeer
    {
        public FieldLabelPeer(FieldLabel owner) : base(owner) { }

        protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.Text;
        protected override bool IsControlElementCore() => false;
        protected override bool IsContentElementCore() => false;
        protected override List<AutomationPeer>? GetChildrenCore() => null;
    }
}
