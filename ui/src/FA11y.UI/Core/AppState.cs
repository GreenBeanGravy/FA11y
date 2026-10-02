using System.Text.Json;

namespace FA11y.UI.Core;

/// <summary>What the core has told the window about itself, shared by all the pages.</summary>
public static class AppState
{
    public static string Version { get; private set; } = "";
    public static bool KeybindsOn { get; private set; }
    public static string OpenKeybind { get; private set; } = "";
    public static bool FortniteRunning { get; private set; }
    public static string? Update { get; private set; }
    public static bool CanRestartToUpdate { get; private set; }
    public static bool HelloReceived { get; private set; }

    /// <summary>First-run setup is in progress (the core says so in core.hello).</summary>
    public static bool SetupActive { get; private set; }

    /// <summary>Raised on the UI thread after any of the values above changed.</summary>
    public static event Action? Changed;

    public static void ApplyHello(JsonElement hello)
    {
        Version = hello.Str("version");
        KeybindsOn = hello.Bool("keybinds_on");
        OpenKeybind = hello.Str("open_keybind");
        FortniteRunning = hello.Bool("fortnite_running");
        Update = hello.NullableStr("update");
        CanRestartToUpdate = hello.Bool("can_restart_to_update");
        SetupActive = hello.Bool("setup");
        HelloReceived = true;
        Changed?.Invoke();
    }

    public static void SetKeybinds(bool on, string openKeybind)
    {
        KeybindsOn = on;
        if (!string.IsNullOrEmpty(openKeybind))
            OpenKeybind = openKeybind;
        Changed?.Invoke();
    }

    public static void SetFortniteRunning(bool running)
    {
        FortniteRunning = running;
        Changed?.Invoke();
    }

    public static void SetUpdate(string? version)
    {
        Update = version;
        Changed?.Invoke();
    }
}
