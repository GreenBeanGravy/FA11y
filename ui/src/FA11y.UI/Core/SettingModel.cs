using System.Text.Json;

namespace FA11y.UI.Core;

/// <summary>One setting of the editor, as the core's settings.schema describes it.</summary>
public sealed class SettingModel
{
    public string Id { get; private init; } = "";
    public string Section { get; private init; } = "";
    public string Key { get; private init; } = "";
    public string Label { get; private init; } = "";
    public string Description { get; private init; } = "";
    public bool ShowDescription { get; private init; }

    /// <summary>toggle, number, text, choice, volume or keybind.</summary>
    public string Kind { get; private init; } = "text";

    public JsonElement Value { get; private init; }
    public JsonElement Default { get; private init; }

    // Numbers and volumes.
    public double Min { get; private init; }
    public double Max { get; private init; }
    public double Step { get; private init; } = 1;
    public int Decimals { get; private init; }

    public IReadOnlyList<(string Value, string Label)> Choices { get; private init; } = Array.Empty<(string, string)>();

    /// <summary>For keybinds: the readable name of the key ("Left Control", or "Unbound").</summary>
    public string Display { get; private init; } = "";

    public static SettingModel From(JsonElement e)
    {
        var choices = new List<(string, string)>();
        if (e.TryGetProperty("choices", out var list) && list.ValueKind == JsonValueKind.Array)
        {
            foreach (var c in list.EnumerateArray())
                choices.Add((c.Str("value"), c.Str("label")));
        }
        return new SettingModel
        {
            Id = e.Str("id"),
            Section = e.Str("section"),
            Key = e.Str("key"),
            Label = e.Str("label"),
            Description = e.Str("description"),
            ShowDescription = e.Bool("show_description"),
            Kind = e.Str("kind", "text"),
            Value = e.TryGetProperty("value", out var v) ? v.Clone() : default,
            Default = e.TryGetProperty("default", out var d) ? d.Clone() : default,
            Min = Number(e, "min", double.MinValue),
            Max = Number(e, "max", double.MaxValue),
            Step = Number(e, "step", 1),
            Decimals = (int)Number(e, "decimals", 0),
            Choices = choices,
            Display = e.Str("display"),
        };
    }

    private static double Number(JsonElement e, string name, double fallback) =>
        e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.Number
            ? v.GetDouble()
            : fallback;
}
