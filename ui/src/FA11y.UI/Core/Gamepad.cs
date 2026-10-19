using System.Runtime.InteropServices;

namespace FA11y.UI.Core;

/// <summary>
/// Which controller buttons are held, by their Fortnite names ("Gamepad_FaceButton_Bottom"), for binding
/// them on the Fortnite settings page. Xbox-style pads are read through XInput, PlayStation pads through the
/// joystick API (Windows numbers their buttons the same way for the DualShock 4 and DualSense). Only read
/// while a button is waiting for one, so nothing polls the controller otherwise.
/// </summary>
public static class Gamepad
{
    /// <summary>Test builds only: buttons to report as held instead of the real ones.</summary>
    public static IReadOnlySet<string>? HeldOverride { get; set; }

    private const ushort SonyVendor = 0x054C;
    private const int TriggerDown = 128;

    private static readonly (ushort Bit, string Name)[] XInputButtons =
    {
        (0x1000, "Gamepad_FaceButton_Bottom"), (0x2000, "Gamepad_FaceButton_Right"),
        (0x4000, "Gamepad_FaceButton_Left"), (0x8000, "Gamepad_FaceButton_Top"),
        (0x0100, "Gamepad_LeftShoulder"), (0x0200, "Gamepad_RightShoulder"),
        (0x0040, "Gamepad_LeftThumbstick"), (0x0080, "Gamepad_RightThumbstick"),
        (0x0001, "Gamepad_DPad_Up"), (0x0002, "Gamepad_DPad_Down"),
        (0x0004, "Gamepad_DPad_Left"), (0x0008, "Gamepad_DPad_Right"),
        (0x0020, "Gamepad_Special_Left"), (0x0010, "Gamepad_Special_Right"),
    };

    // DualShock 4 and DualSense through the joystick API: Square, Cross, Circle, Triangle, L1, R1, L2, R2,
    // Share/Create, Options, L3, R3, PS, touchpad. Share and PS belong to the system, so they bind nothing.
    private static readonly string?[] SonyButtons =
    {
        "Gamepad_FaceButton_Left", "Gamepad_FaceButton_Bottom", "Gamepad_FaceButton_Right", "Gamepad_FaceButton_Top",
        "Gamepad_LeftShoulder", "Gamepad_RightShoulder", "Gamepad_LeftTrigger", "Gamepad_RightTrigger",
        null, "Gamepad_Special_Right", "Gamepad_LeftThumbstick", "Gamepad_RightThumbstick", null, "Gamepad_Special_Left",
    };

    /// <summary>The buttons held on every connected controller.</summary>
    public static IReadOnlySet<string> Held()
    {
        if (HeldOverride != null)
            return HeldOverride;
        var held = new HashSet<string>();
        try
        {
            ReadXInput(held);
        }
        catch (Exception e) when (e is DllNotFoundException or EntryPointNotFoundException)
        {
            // No XInput on this system; the joystick API still covers PlayStation pads.
        }
        ReadSony(held);
        return held;
    }

    private static void ReadXInput(HashSet<string> held)
    {
        for (uint i = 0; i < 4; i++)
        {
            if (XInputGetState(i, out var state) != 0)
                continue;
            foreach (var (bit, name) in XInputButtons)
            {
                if ((state.Buttons & bit) != 0)
                    held.Add(name);
            }
            if (state.LeftTrigger >= TriggerDown)
                held.Add("Gamepad_LeftTrigger");
            if (state.RightTrigger >= TriggerDown)
                held.Add("Gamepad_RightTrigger");
        }
    }

    private static void ReadSony(HashSet<string> held)
    {
        var count = Math.Min(joyGetNumDevs(), 16u);
        for (uint id = 0; id < count; id++)
        {
            var caps = new JoyCaps();
            if (joyGetDevCapsW((UIntPtr)id, ref caps, (uint)Marshal.SizeOf<JoyCaps>()) != 0 || caps.Mid != SonyVendor)
                continue;
            var info = new JoyInfoEx { Size = (uint)Marshal.SizeOf<JoyInfoEx>(), Flags = 0xFF }; // JOY_RETURNALL
            if (joyGetPosEx(id, ref info) != 0)
                continue;
            for (var b = 0; b < SonyButtons.Length; b++)
            {
                if ((info.Buttons & (1u << b)) != 0 && SonyButtons[b] is { } name)
                    held.Add(name);
            }
            // The D-pad is the point of view hat, in hundredths of a degree clockwise from up.
            if (info.Pov <= 35900)
            {
                var pov = info.Pov;
                if (pov >= 31500 || pov <= 4500) held.Add("Gamepad_DPad_Up");
                if (pov >= 4500 && pov <= 13500) held.Add("Gamepad_DPad_Right");
                if (pov >= 13500 && pov <= 22500) held.Add("Gamepad_DPad_Down");
                if (pov >= 22500 && pov <= 31500) held.Add("Gamepad_DPad_Left");
            }
        }
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct XInputState
    {
        public uint PacketNumber;
        public ushort Buttons;
        public byte LeftTrigger;
        public byte RightTrigger;
        public short ThumbLX, ThumbLY, ThumbRX, ThumbRY;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct JoyCaps
    {
        public ushort Mid;
        public ushort Pid;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string Name;
        public uint XMin, XMax, YMin, YMax, ZMin, ZMax, NumButtons, PeriodMin, PeriodMax;
        public uint RMin, RMax, UMin, UMax, VMin, VMax, Caps, MaxAxes, NumAxes, MaxButtons;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string RegKey;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 260)] public string OemVxD;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct JoyInfoEx
    {
        public uint Size, Flags, X, Y, Z, R, U, V, Buttons, ButtonNumber, Pov, Reserved1, Reserved2;
    }

    [DllImport("xinput1_4.dll")] private static extern uint XInputGetState(uint index, out XInputState state);
    [DllImport("winmm.dll")] private static extern uint joyGetNumDevs();
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)] private static extern uint joyGetDevCapsW(UIntPtr id, ref JoyCaps caps, uint size);
    [DllImport("winmm.dll")] private static extern uint joyGetPosEx(uint id, ref JoyInfoEx info);
}
