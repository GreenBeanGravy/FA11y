using System.Collections.Concurrent;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Windows;
using System.Windows.Threading;

namespace FA11y.UI.Core;

/// <summary>
/// The link to the core (FA11y's Python process): JSON Lines on stdin and stdout, one UTF-8 JSON
/// object per line. Nothing else may ever be written to stdout; logs go to logs/ui.log.
///
///   {"type":"request","id":7,"method":"home.info","params":{}}
///   {"type":"response","id":7,"ok":true,"result":{...}}      or "ok":false,"error":"message"
///   {"type":"event","name":"ui.summon","data":{...}}
///
/// Either side sends requests (ids are per sender) and events. Events from the core are held until
/// <see cref="Ready"/> (called once the window has subscribed), then raised on the UI thread in
/// order. The core never has to wait for the window to be up before it talks.
///
/// Startup handshake: after the first render the window sends the event ui.ready. The core answers
/// with the event core.hello: {version, keybinds_on, open_keybind, fortnite_running, update,
/// can_restart_to_update, page}. Anything else the pages need they ask for with requests
/// (home.info, account.state, about.info, ...). The same hello is sent again if the window is
/// restarted, and can be fetched at any time with the request app.state.
///
/// The process ends when stdin closes (the core exited) or when the parent process is gone.
/// </summary>
public sealed class Bridge
{
    private readonly Stream _in;
    private readonly Stream _out;
    private readonly object _writeGate = new();
    private readonly ConcurrentDictionary<long, TaskCompletionSource<JsonElement>> _pending = new();
    private readonly Dictionary<string, List<Action<JsonElement>>> _subscribers = new();
    private readonly List<(string Name, JsonElement Data)> _held = new();
    private readonly object _eventGate = new();
    private long _nextId;
    private bool _ready;
    private Dispatcher? _dispatcher;

    /// <summary>True when a core is on the other end (stdin is a pipe we were given).</summary>
    public bool Connected { get; }

    /// <summary>Raised once, on the UI thread, when the core has gone away.</summary>
    public event Action? Closed;

    public Bridge(Stream input, Stream output, bool connected)
    {
        _in = input;
        _out = output;
        Connected = connected;
    }

    public static Bridge FromConsole(bool connected)
    {
        Stream input = Stream.Null, output = Stream.Null;
        try { input = Console.OpenStandardInput(); } catch { /* standalone run */ }
        try { output = Console.OpenStandardOutput(); } catch { /* standalone run */ }
        return new Bridge(input, output, connected);
    }

    public void Start(Dispatcher dispatcher)
    {
        _dispatcher = dispatcher;
        if (!Connected)
            return;
        new Thread(ReadLoop) { IsBackground = true, Name = "BridgeReader" }.Start();
    }

    /// <summary>Watch the core's process; this process has no reason to live without it.</summary>
    public void WatchParent(int pid)
    {
        try
        {
            var parent = Process.GetProcessById(pid);
            parent.EnableRaisingEvents = true;
            parent.Exited += (_, _) => RaiseClosed("the core process ended");
            if (parent.HasExited)
                RaiseClosed("the core process ended");
        }
        catch (Exception e)
        {
            Log.Info($"Not watching parent {pid}: {e.Message}");
        }
    }

    /// <summary>Call after the window has subscribed to the events it needs.</summary>
    public void Ready()
    {
        List<(string Name, JsonElement Data)> held;
        lock (_eventGate)
        {
            _ready = true;
            held = new(_held);
            _held.Clear();
        }
        foreach (var (name, data) in held)
            Raise(name, data);
    }

    /// <summary>Call handler on the UI thread for each event with this name from the core.</summary>
    public void On(string name, Action<JsonElement> handler)
    {
        lock (_eventGate)
        {
            if (!_subscribers.TryGetValue(name, out var list))
                _subscribers[name] = list = new();
            list.Add(handler);
        }
    }

    public void SendEvent(string name, object? data = null) =>
        Write(new Dictionary<string, object?> { ["type"] = "event", ["name"] = name, ["data"] = data ?? new { } });

    /// <summary>Call a method in the core and wait for its result. Throws if the core reports an error.</summary>
    public async Task<JsonElement> RequestAsync(string method, object? parameters = null, TimeSpan? timeout = null)
    {
        if (!Connected)
            throw new InvalidOperationException("Not connected to FA11y.");
        var id = Interlocked.Increment(ref _nextId);
        var tcs = new TaskCompletionSource<JsonElement>(TaskCreationOptions.RunContinuationsAsynchronously);
        _pending[id] = tcs;
        Write(new Dictionary<string, object?>
        {
            ["type"] = "request", ["id"] = id, ["method"] = method, ["params"] = parameters ?? new { },
        });
        var limit = timeout ?? TimeSpan.FromSeconds(30);
        if (limit == Timeout.InfiniteTimeSpan)
            return await tcs.Task.ConfigureAwait(false);
        var winner = await Task.WhenAny(tcs.Task, Task.Delay(limit)).ConfigureAwait(false);
        if (winner != tcs.Task)
        {
            _pending.TryRemove(id, out _);
            throw new TimeoutException($"{method} took too long.");
        }
        return await tcs.Task.ConfigureAwait(false);
    }

    /// <summary>A request whose answer isn't needed (sounds, "the window was hidden"). Errors are logged.</summary>
    public void Notify(string method, object? parameters = null)
    {
        if (!Connected)
            return;
        _ = Task.Run(async () =>
        {
            try { await RequestAsync(method, parameters, TimeSpan.FromSeconds(10)); }
            catch (Exception e) { Log.Error($"{method} failed", e); }
        });
    }

    private void Write(object message)
    {
        if (!Connected)
            return;
        try
        {
            var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(message) + "\n");
            lock (_writeGate)
            {
                _out.Write(bytes, 0, bytes.Length);
                _out.Flush();
            }
        }
        catch (Exception e)
        {
            Log.Error("Writing to the core failed", e);
            RaiseClosed("the pipe to the core broke");
        }
    }

    private void ReadLoop()
    {
        try
        {
            using var reader = new StreamReader(_in, new UTF8Encoding(false));
            string? line;
            while ((line = reader.ReadLine()) != null)
            {
                if (line.Length == 0)
                    continue;
                try
                {
                    Dispatch(JsonDocument.Parse(line).RootElement);
                }
                catch (JsonException e)
                {
                    Log.Error("The core sent a line that isn't JSON", e);
                }
            }
        }
        catch (Exception e)
        {
            Log.Error("Reading from the core failed", e);
        }
        RaiseClosed("stdin closed");
    }

    private void Dispatch(JsonElement message)
    {
        switch (message.Str("type"))
        {
            case "response":
                if (message.TryGetProperty("id", out var idElement) && idElement.TryGetInt64(out var id)
                    && _pending.TryRemove(id, out var tcs))
                {
                    if (message.Bool("ok"))
                        tcs.TrySetResult(message.TryGetProperty("result", out var result) ? result.Clone() : default);
                    else
                        tcs.TrySetException(new InvalidOperationException(message.Str("error", "The request failed.")));
                }
                break;
            case "event":
                var name = message.Str("name");
                var data = message.TryGetProperty("data", out var d) ? d.Clone() : default;
                lock (_eventGate)
                {
                    if (!_ready)
                    {
                        _held.Add((name, data));
                        return;
                    }
                }
                Raise(name, data);
                break;
            case "request":
                // The core has no requests for the window yet; answer so it never waits.
                var requestId = message.TryGetProperty("id", out var rid) ? rid.GetInt64() : 0;
                Write(new Dictionary<string, object?>
                {
                    ["type"] = "response", ["id"] = requestId, ["ok"] = false,
                    ["error"] = $"Unknown method: {message.Str("method")}",
                });
                break;
        }
    }

    private void Raise(string name, JsonElement data)
    {
        Action<JsonElement>[] handlers;
        lock (_eventGate)
            handlers = _subscribers.TryGetValue(name, out var list) ? list.ToArray() : Array.Empty<Action<JsonElement>>();
        if (handlers.Length == 0)
            return;
        _dispatcher?.BeginInvoke(() =>
        {
            foreach (var handler in handlers)
            {
                try { handler(data); }
                catch (Exception e) { Log.Error($"Handler for {name} failed", e); }
            }
        });
    }

    private int _closed;

    private void RaiseClosed(string reason)
    {
        if (Interlocked.Exchange(ref _closed, 1) != 0)
            return;
        Log.Info($"The core is gone ({reason}); exiting.");
        foreach (var tcs in _pending.Values)
            tcs.TrySetException(new InvalidOperationException("FA11y is closing."));
        _pending.Clear();
        _dispatcher?.BeginInvoke(() => Closed?.Invoke());
    }
}
