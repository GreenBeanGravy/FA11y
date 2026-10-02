using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;

namespace FA11y.UI.Shell;

/// <summary>Dark title bar and bringing a window to the foreground.</summary>
public static class WindowTools
{
    /// <summary>Give the window a dark title bar once its handle exists.</summary>
    public static void UseDarkTitleBar(Window window)
    {
        window.SourceInitialized += (_, _) =>
        {
            var hwnd = new WindowInteropHelper(window).Handle;
            int on = 1;
            if (NativeMethods.DwmSetWindowAttribute(hwnd, NativeMethods.DWMWA_USE_IMMERSIVE_DARK_MODE, ref on, sizeof(int)) != 0)
                NativeMethods.DwmSetWindowAttribute(hwnd, NativeMethods.DWMWA_USE_IMMERSIVE_DARK_MODE_OLD, ref on, sizeof(int));
        };
    }

    /// <summary>
    /// Show the window, restore it if minimized, and make it the foreground window. Windows only
    /// lets the process that last received input take the foreground, so when plain activation
    /// isn't enough this sends a zero distance mouse move (nothing moves, nothing is pressed) and
    /// tries again, the same trick the wx window used.
    /// </summary>
    public static void BringToFront(Window window)
    {
        var hwnd = new WindowInteropHelper(window).EnsureHandle();
        if (window.WindowState == WindowState.Minimized || NativeMethods.IsIconic(hwnd))
            window.WindowState = WindowState.Normal;
        if (!window.IsVisible)
            window.Show();
        window.Activate();
        if (NativeMethods.GetForegroundWindow() == hwnd)
            return;

        NativeMethods.ShowWindow(hwnd, NativeMethods.SW_RESTORE);
        NativeMethods.SetWindowPos(hwnd, NativeMethods.HWND_TOPMOST, 0, 0, 0, 0,
            NativeMethods.SWP_NOMOVE | NativeMethods.SWP_NOSIZE | NativeMethods.SWP_SHOWWINDOW);
        NativeMethods.SetWindowPos(hwnd, NativeMethods.HWND_NOTOPMOST, 0, 0, 0, 0,
            NativeMethods.SWP_NOMOVE | NativeMethods.SWP_NOSIZE | NativeMethods.SWP_SHOWWINDOW);
        NativeMethods.SetForegroundWindow(hwnd);
        if (NativeMethods.GetForegroundWindow() != hwnd)
        {
            SendNullMouseMove();
            NativeMethods.SetForegroundWindow(hwnd);
        }
        NativeMethods.BringWindowToTop(hwnd);
        NativeMethods.SetActiveWindow(hwnd);

        var foreground = NativeMethods.GetForegroundWindow();
        if (foreground != IntPtr.Zero && foreground != hwnd)
        {
            // AttachThreadInput gets past the foreground lock when another program's window is active.
            var theirThread = NativeMethods.GetWindowThreadProcessId(foreground, out _);
            var ourThread = NativeMethods.GetCurrentThreadId();
            if (theirThread != 0 && theirThread != ourThread)
            {
                NativeMethods.AttachThreadInput(ourThread, theirThread, true);
                try
                {
                    NativeMethods.SetForegroundWindow(hwnd);
                    NativeMethods.SetFocus(hwnd);
                }
                finally
                {
                    NativeMethods.AttachThreadInput(ourThread, theirThread, false);
                }
            }
        }
    }

    private static void SendNullMouseMove()
    {
        var input = new NativeMethods.INPUT { type = NativeMethods.INPUT_MOUSE };
        input.mi.dwFlags = NativeMethods.MOUSEEVENTF_MOVE;
        NativeMethods.SendInput(1, new[] { input }, Marshal.SizeOf<NativeMethods.INPUT>());
    }

    /// <summary>
    /// Give memory back to Windows. The window spends most of its life hidden in the tray while a
    /// game runs, so after hiding it collects garbage and trims the working set; pages fault back
    /// in when the window is shown again.
    /// </summary>
    public static void TrimMemory()
    {
        GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: true);
        NativeMethods.SetProcessWorkingSetSize(System.Diagnostics.Process.GetCurrentProcess().Handle, new IntPtr(-1), new IntPtr(-1));
    }

    /// <summary>True when the window in front belongs to this program or to the core (e.g. a sign in dialog).</summary>
    public static bool ForegroundIsFa11y(int coreProcessId)
    {
        var foreground = NativeMethods.GetForegroundWindow();
        if (foreground == IntPtr.Zero)
            return true;
        NativeMethods.GetWindowThreadProcessId(foreground, out var pid);
        return pid == Environment.ProcessId || (coreProcessId != 0 && pid == coreProcessId);
    }
}
