using System.Windows.Automation.Peers;
using System.Windows.Controls;

namespace FA11y.UI.Controls;

/// <summary>Text that is purely visual (section headings, the brand name): screen readers never see it.</summary>
public sealed class HiddenText : TextBlock
{
    protected override AutomationPeer? OnCreateAutomationPeer() => null;
}

/// <summary>A picture that is purely decoration: screen readers never see it.</summary>
public sealed class HiddenImage : Image
{
    protected override AutomationPeer? OnCreateAutomationPeer() => null;
}
