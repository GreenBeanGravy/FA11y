using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Peers;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace FA11y.UI.Controls;

/// <summary>One paragraph of a <see cref="ReadableText"/>, with its own size, weight and color.</summary>
/// <param name="Text">The words.</param>
/// <param name="FontSize">Size in device independent pixels; 0 keeps the control's size.</param>
/// <param name="Weight">Font weight; null keeps normal.</param>
/// <param name="Foreground">Brush; null keeps the control's foreground.</param>
/// <param name="GapTop">Space above this paragraph, when another paragraph comes before it.</param>
public sealed record TextLine(string Text, double FontSize = 0, FontWeight? Weight = null,
                              Brush? Foreground = null, double GapTop = 0);

/// <summary>
/// Read-only text that Tab reaches. Screen readers see one Text element whose name is the whole
/// text ("Fortnite, 31.10, Ready"), so a status or an explanation is read with Tab instead of
/// needing object navigation. Ctrl+C copies the text. A control with no text isn't a tab stop.
/// </summary>
public class ReadableText : Control
{
    private StackPanel? _host;
    private IReadOnlyList<TextLine> _lines = Array.Empty<TextLine>();
    private string _accessibleText = "";

    static ReadableText()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(ReadableText), new FrameworkPropertyMetadata(typeof(ReadableText)));
        FocusableProperty.OverrideMetadata(typeof(ReadableText), new FrameworkPropertyMetadata(false));
    }

    public ReadableText()
    {
        CommandBindings.Add(new CommandBinding(ApplicationCommands.Copy, (_, e) =>
        {
            try { Clipboard.SetText(_accessibleText); } catch { /* the clipboard may be busy */ }
            e.Handled = true;
        }, (_, e) => e.CanExecute = _accessibleText.Length > 0));
        InputBindings.Add(new KeyBinding(ApplicationCommands.Copy, Key.C, ModifierKeys.Control));
    }

    /// <summary>What goes between paragraphs in the name screen readers hear.</summary>
    public string Separator { get; set; } = " ";

    /// <summary>The words as a screen reader hears them.</summary>
    public string AccessibleText => _accessibleText;

    /// <summary>Convenience for a single paragraph.</summary>
    public string Text
    {
        get => _accessibleText;
        set => SetLines(new TextLine(value));
    }

    public void SetLines(params TextLine[] lines)
    {
        _lines = lines;
        var old = _accessibleText;
        _accessibleText = string.Join(Separator, lines.Where(l => l.Text.Length > 0).Select(l => l.Text));
        Focusable = _accessibleText.Length > 0;
        IsTabStop = Focusable;
        Rebuild();
        if (old != _accessibleText && UIElementAutomationPeer.FromElement(this) is { } peer)
            peer.RaisePropertyChangedEvent(AutomationElementIdentifiers.NameProperty, old, _accessibleText);
    }

    public override void OnApplyTemplate()
    {
        base.OnApplyTemplate();
        _host = GetTemplateChild("PART_Lines") as StackPanel;
        Rebuild();
    }

    private void Rebuild()
    {
        if (_host == null)
            return;
        _host.Children.Clear();
        var first = true;
        foreach (var line in _lines)
        {
            if (line.Text.Length == 0)
                continue;
            var block = new HiddenText
            {
                Text = line.Text,
                TextWrapping = TextWrapping.Wrap,
                Margin = new Thickness(0, first ? 0 : line.GapTop, 0, 0),
            };
            if (line.FontSize > 0)
                block.FontSize = line.FontSize;
            if (line.Weight is { } weight)
                block.FontWeight = weight;
            if (line.Foreground != null)
                block.Foreground = line.Foreground;
            _host.Children.Add(block);
            first = false;
        }
    }

    protected override AutomationPeer OnCreateAutomationPeer() => new ReadableTextPeer(this);
}

/// <summary>A focusable Text element named by the control's whole text.</summary>
internal sealed class ReadableTextPeer : FrameworkElementAutomationPeer
{
    public ReadableTextPeer(ReadableText owner) : base(owner) { }

    private ReadableText Text => (ReadableText)Owner;

    protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.Text;
    protected override string GetClassNameCore() => Owner.GetType().Name;
    protected override string GetNameCore() => Text.AccessibleText;
    protected override bool IsControlElementCore() => true;
    protected override bool IsContentElementCore() => true;
    protected override List<AutomationPeer>? GetChildrenCore() => null;
}
