using System.IO;
using System.Text;

namespace FA11y.UI.Core;

/// <summary>Writes to logs/ui.log under the FA11y Files folder. Never to stdout, which carries the protocol.</summary>
public static class Log
{
    private static readonly object Gate = new();
    private static string? _path;

    public static void Init(string? root)
    {
        try
        {
            if (string.IsNullOrEmpty(root))
                return;
            var dir = Path.Combine(root, "logs");
            Directory.CreateDirectory(dir);
            var path = Path.Combine(dir, "ui.log");
            var info = new FileInfo(path);
            if (info.Exists && info.Length > 1_000_000)
                File.Move(path, path + ".1", overwrite: true);
            _path = path;
        }
        catch
        {
            _path = null;
        }
    }

    public static void Info(string message) => Write("INFO", message);

    public static void Error(string message, Exception? error = null) =>
        Write("ERROR", error == null ? message : $"{message}: {error}");

    private static void Write(string level, string message)
    {
        var path = _path;
        if (path == null)
            return;
        try
        {
            lock (Gate)
                File.AppendAllText(path, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} {level} {message}{Environment.NewLine}",
                    Encoding.UTF8);
        }
        catch
        {
            // Logging must never take the window down.
        }
    }
}
