using System.Windows;

namespace FA11y.UI.Core;

/// <summary>
/// What every pass tab shares: whether an account request is running and the last result
/// message. Tabs redraw when it changes.
/// </summary>
public sealed class PassSession
{
    private readonly Func<UIElement> _anchor;

    public PassSession(Func<UIElement> anchor)
    {
        _anchor = anchor;
    }

    public bool Busy { get; private set; }
    public bool Loaded { get; private set; }
    public string Message { get; private set; } = "Loading account status...";

    /// <summary>Raised on the UI thread when Busy or Message changed, or the account's passes were reloaded.</summary>
    public event Action? Changed;

    /// <summary>Show a result and have it spoken.</summary>
    public void Say(string message)
    {
        Message = message;
        Announcer.Announce(_anchor(), message);
        Changed?.Invoke();
    }

    public void SetBusy(bool busy)
    {
        Busy = busy;
        Changed?.Invoke();
    }

    /// <summary>Load the account's pass state. Does nothing while another account request runs.</summary>
    public async Task RefreshAsync()
    {
        if (Busy)
            return;
        Loaded = true;
        SetBusy(true);
        string message;
        try
        {
            message = (await App.Bridge.RequestAsync("passes.refresh", null, TimeSpan.FromSeconds(120))).Str("message", "Passes refreshed.");
        }
        catch (Exception e)
        {
            Log.Error("passes.refresh failed", e);
            message = "Pass data could not be loaded. Refresh to retry.";
        }
        Busy = false;
        Say(message);
    }
}
