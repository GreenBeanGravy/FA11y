using System.Windows;
using FA11y.UI.Core;

namespace FA11y.UI.Pages;

/// <summary>
/// A page the new window doesn't have yet. It points at the existing wx window for the feature,
/// which the core opens when the button is pressed.
/// </summary>
public partial class PlaceholderPage : PageBase
{
    private readonly string _key;
    private readonly string _title;

    public PlaceholderPage(string key, string title)
    {
        _key = key;
        _title = title;
        InitializeComponent();
        Heading.Text = title;
        Explanation.Text = $"{title} opens in its own window for now.";
        OpenButton.Content = $"_Open {title}";
    }

    public override string Key => _key;
    public override string Title => _title;

    // The button first: it is the one thing to do here. The sentence is a Shift+Tab away.
    public override FrameworkElement? FirstFocus() => OpenButton;

    private async void OnOpenClick(object sender, RoutedEventArgs e)
    {
        try
        {
            var result = await App.Bridge.RequestAsync("app.open_classic", new { key = _key }, TimeSpan.FromSeconds(30));
            if (!result.Bool("ok"))
                Announcer.Announce(Host ?? (UIElement)this, $"Couldn't open {_title}.");
        }
        catch (Exception ex)
        {
            Log.Error($"Opening {_title} failed", ex);
            Announcer.Announce(Host ?? (UIElement)this, $"Couldn't open {_title}.");
        }
    }
}
