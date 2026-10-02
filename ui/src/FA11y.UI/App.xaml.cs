using System.Diagnostics;
using System.Windows;
using System.Windows.Threading;
using FA11y.UI.Core;
using FA11y.UI.Shell;

namespace FA11y.UI;

/// <summary>
/// Starts the window. Command line: --root &lt;FA11y Files folder&gt; --parent-pid &lt;core pid&gt; [--hidden].
/// Run by hand without them, the window works on its own with no core to ask (the pages show nothing).
/// </summary>
public partial class App : Application
{
    public static Bridge Bridge { get; private set; } = null!;
    public static int CoreProcessId { get; private set; }
    public static string Root { get; private set; } = "";

    private MainWindow? _window;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        var startedAt = Process.GetCurrentProcess().StartTime;

        var hidden = false;
        string? root = null;
        var parentPid = 0;
        for (var i = 0; i < e.Args.Length; i++)
        {
            switch (e.Args[i])
            {
                case "--root" when i + 1 < e.Args.Length:
                    root = e.Args[++i];
                    break;
                case "--parent-pid" when i + 1 < e.Args.Length:
                    int.TryParse(e.Args[++i], out parentPid);
                    break;
                case "--hidden":
                    hidden = true;
                    break;
            }
        }
        Root = root ?? "";
        CoreProcessId = parentPid;
        Log.Init(root);
        Log.Info($"Starting (pid {Environment.ProcessId}, core {parentPid}{(hidden ? ", hidden" : "")})");

        DispatcherUnhandledException += (_, args) =>
        {
            Log.Error("Unhandled error", args.Exception);
            args.Handled = true;
        };
        AppDomain.CurrentDomain.UnhandledException += (_, args) =>
            Log.Error("Fatal error", args.ExceptionObject as Exception);
        SessionEnding += (_, _) => _window?.Quit();

        // Connected means a core started us and is on the other end of stdin/stdout.
        Bridge = Bridge.FromConsole(connected: parentPid != 0);
        Bridge.Closed += () => _window?.Quit();
        Bridge.Start(Dispatcher);
        if (parentPid != 0)
            Bridge.WatchParent(parentPid);

        Log.Info($"OnStartup reached {(DateTime.Now - startedAt).TotalMilliseconds:F0} ms after the process started");
        _window = new MainWindow();
        Log.Info($"Window built {(DateTime.Now - startedAt).TotalMilliseconds:F0} ms after the process started");
        if (!hidden)
        {
            _window.ContentRendered += (_, _) =>
                Log.Info($"First render {(DateTime.Now - startedAt).TotalMilliseconds:F0} ms after the process started");
            _window.Show();
            WindowTools.BringToFront(_window);
            _window.FocusSidebar();
        }
        // After the first paint (Background is below Render): tray icon, other pages, ui.ready.
        Dispatcher.BeginInvoke(DispatcherPriority.Background, _window.FinishStartup);
    }
}
