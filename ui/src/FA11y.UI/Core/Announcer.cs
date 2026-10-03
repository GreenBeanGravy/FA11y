using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Peers;

namespace FA11y.UI.Core;

/// <summary>
/// Speaks messages that aren't tied to focus (for example "Signed out.") with UI Automation
/// notification events, which screen readers read aloud.
/// </summary>
public static class Announcer
{
    public static void Announce(UIElement anchor, string message, bool important = false)
    {
        if (string.IsNullOrWhiteSpace(message))
            return;
        try
        {
            var peer = UIElementAutomationPeer.FromElement(anchor) ?? UIElementAutomationPeer.CreatePeerForElement(anchor);
            peer?.RaiseNotificationEvent(
                AutomationNotificationKind.ActionCompleted,
                important ? AutomationNotificationProcessing.ImportantMostRecent : AutomationNotificationProcessing.MostRecent,
                message,
                "FA11y");
        }
        catch (Exception e)
        {
            Log.Error("Announcing failed", e);
        }
    }
}
