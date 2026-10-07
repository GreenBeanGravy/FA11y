using System.Windows;
using System.Windows.Automation;
using System.Windows.Input;
using FA11y.UI.Core;

namespace FA11y.UI.Controls;

/// <summary>
/// The button of one keybind. It draws the key ("Left Control") but is named "Fire: Left Control". Pressed, it
/// waits for the next key: <see cref="Captured"/> gets the main key's virtual key code and the codes of the
/// Shift and Alt keys held with it, and the core turns that into FA11y's combination text. Escape or a click
/// cancels; Shift and Alt on their own wait for the key they go with; the Enter or Space that pressed the
/// button is ignored until it is let go.
/// </summary>
public sealed class KeybindButton : IconButton
{
    private const int VkMButton = 0x04, VkXButton1 = 0x05, VkXButton2 = 0x06;
    private const int VkLShift = 0xA0, VkRShift = 0xA1, VkLMenu = 0xA4, VkRMenu = 0xA5;

    private readonly HashSet<Key> _ignore = new();
    private string _display = "";

    static KeybindButton()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(KeybindButton), new FrameworkPropertyMetadata(typeof(IconButton)));
    }

    public KeybindButton()
    {
        SetResourceReference(StyleProperty, typeof(IconButton));
    }

    public string Action { get; set; } = "";
    public bool Capturing { get; private set; }

    /// <summary>A key was pressed while capturing: main key's virtual key code, held Shift and Alt key codes.</summary>
    public event Action<int, int[]>? Captured;

    /// <summary>Capturing ended without a key (Escape, a click, focus left).</summary>
    public event Action? Cancelled;


    /// <summary>Show the key this keybind has ("Left Control" or "Unbound").</summary>
    public void SetKey(string display)
    {
        _display = display;
        Content = display;
        AutomationProperties.SetName(this, $"{Action}: {display}");
    }

    public void BeginCapture()
    {
        if (Capturing)
            return;
        Capturing = true;
        KeyCapture.Active = true;
        _ignore.Clear();
        foreach (var key in Enum.GetValues<Key>())
        {
            if (key != Key.None && KeyState.IsDown(key))
                _ignore.Add(key);
        }
        Content = "Press any key";
        AutomationProperties.SetName(this, $"{Action}: Press any key or mouse button");
    }

    /// <summary>Stop waiting. restore puts back the key that was shown before.</summary>
    public void EndCapture(bool restore)
    {
        if (!Capturing)
            return;
        Capturing = false;
        KeyCapture.Active = false;
        if (restore)
            SetKey(_display);
    }

    /// <summary>Show the key from before capturing again, when binding the captured key failed.</summary>
    public void RestoreKey() => SetKey(_display);

    private void Cancel()
    {
        EndCapture(true);
        Cancelled?.Invoke();
    }

    private static Key Real(KeyEventArgs e) =>
        e.Key == Key.System ? e.SystemKey
        : e.Key == Key.ImeProcessed ? e.ImeProcessedKey
        : e.Key == Key.DeadCharProcessed ? e.DeadCharProcessedKey
        : e.Key;

    // A keyboard click only counts when Enter or Space went down on this button. Otherwise the Enter that
    // moved focus here from the sidebar could press it as soon as it arrives.
    private bool _keyArmed;

    protected override void OnGotKeyboardFocus(KeyboardFocusChangedEventArgs e)
    {
        _keyArmed = false;
        base.OnGotKeyboardFocus(e);
    }

    protected override void OnClick()
    {
        if (InputManager.Current.MostRecentInputDevice is KeyboardDevice && !_keyArmed)
            return;
        _keyArmed = false;
        base.OnClick();
    }

    protected override void OnPreviewKeyDown(KeyEventArgs e)
    {
        if (!Capturing)
        {
            if (e.Key is Key.Enter or Key.Space)
                _keyArmed = true;
            base.OnPreviewKeyDown(e);
            return;
        }
        e.Handled = true;
        var key = Real(e);
        if (key == Key.None || _ignore.Contains(key))
            return;
        if (key == Key.Escape)
        {
            Cancel();
            return;
        }
        if (key is Key.LeftShift or Key.RightShift or Key.LeftAlt or Key.RightAlt)
            return; // wait for the key these go with
        var vk = KeyInterop.VirtualKeyFromKey(key);
        if (vk == 0)
            return;
        var modifiers = new List<int>();
        if (KeyState.IsDown(Key.LeftShift)) modifiers.Add(VkLShift);
        if (KeyState.IsDown(Key.RightShift)) modifiers.Add(VkRShift);
        if (KeyState.IsDown(Key.LeftAlt)) modifiers.Add(VkLMenu);
        if (KeyState.IsDown(Key.RightAlt)) modifiers.Add(VkRMenu);
        // The name stays "Press any key" until the core answers with the new key, so a screen reader
        // never hears the old key in between.
        EndCapture(false);
        Captured?.Invoke(vk, modifiers.ToArray());
    }

    protected override void OnPreviewKeyUp(KeyEventArgs e)
    {
        if (Capturing)
        {
            e.Handled = true;
            _ignore.Remove(Real(e));
            return;
        }
        base.OnPreviewKeyUp(e);
    }

    protected override void OnPreviewMouseDown(MouseButtonEventArgs e)
    {
        if (!Capturing)
        {
            base.OnPreviewMouseDown(e);
            return;
        }
        e.Handled = true;
        CaptureMouseButton(e.ChangedButton);
    }

    /// <summary>
    /// A mouse button pressed while capturing, here or anywhere on the "press a key" screen. Middle, back
    /// and forward bind (with Shift or Alt held, like keys); left and right click cancel.
    /// </summary>
    public void CaptureMouseButton(MouseButton button)
    {
        if (!Capturing)
            return;
        var vk = button switch
        {
            MouseButton.Middle => VkMButton,
            MouseButton.XButton1 => VkXButton1,
            MouseButton.XButton2 => VkXButton2,
            _ => 0,
        };
        if (vk == 0)
        {
            Cancel();
            return;
        }
        var modifiers = new List<int>();
        if (KeyState.IsDown(Key.LeftShift)) modifiers.Add(VkLShift);
        if (KeyState.IsDown(Key.RightShift)) modifiers.Add(VkRShift);
        if (KeyState.IsDown(Key.LeftAlt)) modifiers.Add(VkLMenu);
        if (KeyState.IsDown(Key.RightAlt)) modifiers.Add(VkRMenu);
        // The name stays "Press any key" until the core answers with the new key, so a screen reader
        // never hears the old key in between.
        EndCapture(false);
        Captured?.Invoke(vk, modifiers.ToArray());
    }

    protected override void OnLostKeyboardFocus(KeyboardFocusChangedEventArgs e)
    {
        base.OnLostKeyboardFocus(e);
        if (Capturing)
            Cancel();
    }
}
