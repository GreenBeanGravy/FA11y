using System.Windows.Input;

namespace FA11y.UI.Core;

/// <summary>
/// True while a keybind button is waiting for the key to bind. The window's own key handling (Ctrl+Tab,
/// F6, Escape, the page's shortcuts) stands aside, so any key can be bound.
/// </summary>
public static class KeyCapture
{
    public static bool Active { get; set; }
}

/// <summary>
/// Which keys are held. The real state, except in test builds, where a test can say which keys
/// are held while it presses a key (the test core has no way to press two keys at once).
/// </summary>
public static class KeyState
{
    /// <summary>Test builds only: modifiers to report instead of the real ones, and the keys held.</summary>
    public static ModifierKeys? ModifiersOverride { get; set; }
    public static ISet<Key>? HeldOverride { get; set; }

    public static ModifierKeys Modifiers => ModifiersOverride ?? Keyboard.Modifiers;

    public static bool IsDown(Key key) =>
        HeldOverride != null ? HeldOverride.Contains(key) : Keyboard.IsKeyDown(key);
}
