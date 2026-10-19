using System.Windows.Input;

namespace FA11y.UI.Core;

/// <summary>
/// Fortnite's names for keys and mouse buttons (Unreal's key names, as its settings file stores them), for
/// keybind buttons on the Fortnite settings page. The core checks every name it is sent, so a key missing
/// here is only one that can't be bound by pressing it.
/// </summary>
public static class FortniteKeys
{
    private static readonly Dictionary<int, string> ByVirtualKey = Build();

    private static Dictionary<int, string> Build()
    {
        var keys = new Dictionary<int, string>
        {
            [0x01] = "LeftMouseButton", [0x02] = "RightMouseButton", [0x04] = "MiddleMouseButton",
            [0x05] = "ThumbMouseButton", [0x06] = "ThumbMouseButton2",
            [0x08] = "BackSpace", [0x09] = "Tab", [0x0D] = "Enter", [0x13] = "Pause", [0x14] = "CapsLock",
            [0x20] = "SpaceBar", [0x21] = "PageUp", [0x22] = "PageDown", [0x23] = "End", [0x24] = "Home",
            [0x25] = "Left", [0x26] = "Up", [0x27] = "Right", [0x28] = "Down", [0x2D] = "Insert", [0x2E] = "Delete",
            [0x6A] = "Multiply", [0x6B] = "Add", [0x6D] = "Subtract", [0x6E] = "Decimal", [0x6F] = "Divide",
            [0x90] = "NumLock", [0x91] = "ScrollLock",
            [0xA0] = "LeftShift", [0xA1] = "RightShift", [0xA2] = "LeftControl", [0xA3] = "RightControl",
            [0xA4] = "LeftAlt", [0xA5] = "RightAlt",
            [0xBA] = "Semicolon", [0xBB] = "Equals", [0xBC] = "Comma", [0xBD] = "Hyphen", [0xBE] = "Period",
            [0xBF] = "Slash", [0xC0] = "Tilde", [0xDB] = "LeftBracket", [0xDC] = "Backslash", [0xDD] = "RightBracket",
            [0xDE] = "Apostrophe",
        };
        string[] digits = { "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine" };
        for (var i = 0; i < 10; i++)
        {
            keys[0x30 + i] = digits[i];
            keys[0x60 + i] = "NumPad" + digits[i];
        }
        for (var c = 'A'; c <= 'Z'; c++)
            keys[c] = c.ToString();
        for (var f = 1; f <= 12; f++)
            keys[0x6F + f] = "F" + f;
        return keys;
    }

    /// <summary>The Fortnite name of a virtual key or mouse button code, or null when Fortnite has none.</summary>
    public static string? FromVirtualKey(int vk) => ByVirtualKey.GetValueOrDefault(vk);

    public static string? FromMouseButton(MouseButton button) => button switch
    {
        MouseButton.Left => "LeftMouseButton",
        MouseButton.Right => "RightMouseButton",
        MouseButton.Middle => "MiddleMouseButton",
        MouseButton.XButton1 => "ThumbMouseButton",
        MouseButton.XButton2 => "ThumbMouseButton2",
        _ => null,
    };

    public static string FromWheel(int delta) => delta > 0 ? "MouseScrollUp" : "MouseScrollDown";
}
