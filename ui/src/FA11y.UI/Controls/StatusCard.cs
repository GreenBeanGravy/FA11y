using System.Windows;
using System.Windows.Media;

namespace FA11y.UI.Controls;

/// <summary>
/// A Home page card: a muted title, the value, and a detail line colored by level. The whole card
/// is one tab stop, read as "Fortnite, 31.10, Ready".
/// </summary>
public sealed class StatusCard : ReadableText
{
    static StatusCard()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(StatusCard), new FrameworkPropertyMetadata(typeof(StatusCard)));
    }

    public StatusCard()
    {
        Separator = ", ";
    }

    public static readonly DependencyProperty TitleProperty =
        DependencyProperty.Register(nameof(Title), typeof(string), typeof(StatusCard),
            new PropertyMetadata("", (d, _) => ((StatusCard)d).Set("Loading…")));

    public string Title
    {
        get => (string)GetValue(TitleProperty);
        set => SetValue(TitleProperty, value);
    }

    /// <summary>Show the value and detail. level is "ok", "warn", "error" or "" (shown muted).</summary>
    public void Set(string value, string detail = "", string level = "")
    {
        var color = level switch
        {
            "ok" => "Success",
            "warn" => "Warning",
            "error" => "Danger",
            _ => "TextMuted",
        };
        SetLines(
            new TextLine(Title, 12, null, (Brush)Application.Current.Resources["TextSecondary"]),
            new TextLine(value, 16, FontWeights.SemiBold, (Brush)Application.Current.Resources["Text"], 2),
            new TextLine(detail, 12, null, (Brush)Application.Current.Resources[color], 2));
    }
}
