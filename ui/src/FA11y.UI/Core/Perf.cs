using System.Diagnostics;
using System.Windows.Threading;

namespace FA11y.UI.Core;

/// <summary>Test builds only (FA11Y_UI_TEST=1): log how long something took to show, up to when the window went idle.</summary>
public static class Perf
{
    private static readonly bool On = Environment.GetEnvironmentVariable("FA11Y_UI_TEST") == "1";

    /// <summary>Call when work starts; the returned action, called after the work has been done, logs once layout and rendering are finished.</summary>
    public static void Measure(Dispatcher dispatcher, string what, Action work)
    {
        if (!On)
        {
            work();
            return;
        }
        var sw = Stopwatch.StartNew();
        work();
        var built = sw.Elapsed.TotalMilliseconds;
        dispatcher.BeginInvoke(DispatcherPriority.ContextIdle,
            () => Log.Info($"PERF {what}: built in {built:F0} ms, on screen after {sw.Elapsed.TotalMilliseconds:F0} ms"));
    }

    public static void Mark(string message)
    {
        if (On)
            Log.Info($"PERF {message}");
    }
}
