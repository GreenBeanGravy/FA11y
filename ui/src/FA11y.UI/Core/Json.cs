using System.Text.Json;

namespace FA11y.UI.Core;

/// <summary>Forgiving readers for the JSON the core sends: a missing or wrong-typed field gives a default.</summary>
public static class Json
{
    public static string Str(this JsonElement e, string name, string fallback = "")
    {
        if (e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String)
            return v.GetString() ?? fallback;
        return fallback;
    }

    public static bool Bool(this JsonElement e, string name, bool fallback = false)
    {
        if (e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v))
        {
            if (v.ValueKind == JsonValueKind.True) return true;
            if (v.ValueKind == JsonValueKind.False) return false;
        }
        return fallback;
    }

    /// <summary>true, false, or null when the field is null or missing.</summary>
    public static bool? NullableBool(this JsonElement e, string name)
    {
        if (e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v))
        {
            if (v.ValueKind == JsonValueKind.True) return true;
            if (v.ValueKind == JsonValueKind.False) return false;
        }
        return null;
    }

    /// <summary>A string field, or null when it is null or missing.</summary>
    public static string? NullableStr(this JsonElement e, string name)
    {
        if (e.ValueKind == JsonValueKind.Object && e.TryGetProperty(name, out var v) && v.ValueKind == JsonValueKind.String)
            return v.GetString();
        return null;
    }
}
