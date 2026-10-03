using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using FA11y.UI.Core;

namespace FA11y.UI.Controls;

/// <summary>
/// A text box for a number that behaves like the wx spin box: Up and Down step the value (Page Up and
/// Page Down by ten steps), typing is limited to digits, a number outside the range is held to it, and
/// the new value is selected so a screen reader reads it. <see cref="Edited"/> is raised for every
/// change the user makes; its argument is true when the change should be saved at once (Enter, leaving
/// the box) and false when more edits may follow (typing, stepping).
/// </summary>
public sealed class NumberBox : TextBox
{
    private double _value;

    static NumberBox()
    {
        // Looks like every other text box.
        DefaultStyleKeyProperty.OverrideMetadata(typeof(NumberBox), new FrameworkPropertyMetadata(typeof(TextBox)));
    }

    public NumberBox()
    {
        SetResourceReference(StyleProperty, typeof(TextBox));
        DataObject.AddPastingHandler(this, (_, e) =>
        {
            if (e.DataObject.GetData(DataFormats.UnicodeText) is not string text || !text.All(IsAllowed))
                e.CancelCommand();
        });
        TextChanged += (_, _) =>
        {
            if (_setting)
                return;
            _dirty = true;
            Edited?.Invoke(false);
        };
        LostKeyboardFocus += (_, _) => Finish();
    }

    private bool _dirty;

    /// <summary>The edit is done (Enter, leaving the box): tidy the text and ask for it to be saved now.</summary>
    private void Finish()
    {
        if (!_dirty)
            return;
        _dirty = false;
        Commit();
        Edited?.Invoke(true);
    }

    public double Minimum { get; set; } = double.MinValue;
    public double Maximum { get; set; } = double.MaxValue;
    public double Step { get; set; } = 1;
    public int Decimals { get; set; }

    /// <summary>The user changed the value. True: save now. False: wait for more edits.</summary>
    public event Action<bool>? Edited;

    private bool _setting;

    /// <summary>The value of the last text that parsed, held to the range.</summary>
    public double Value
    {
        get
        {
            if (TryParse(Text, out var parsed))
                _value = Clamp(parsed);
            return _value;
        }
    }

    /// <summary>Show a value without raising <see cref="Edited"/>.</summary>
    public void SetValue(double value)
    {
        _setting = true;
        try
        {
            _value = Clamp(value);
            Text = Format(_value);
            _dirty = false;
        }
        finally
        {
            _setting = false;
        }
    }

    /// <summary>Make the text the value it parses to. Returns false when the text was already that value.</summary>
    public bool Commit()
    {
        var shown = Format(Value);
        if (Text == shown)
            return false;
        _setting = true;
        try { Text = shown; }
        finally { _setting = false; }
        return true;
    }

    public string Format(double value) =>
        Decimals > 0
            ? value.ToString("F" + Decimals, CultureInfo.InvariantCulture)
            : Math.Round(value).ToString("F0", CultureInfo.InvariantCulture);

    private double Clamp(double value) => Math.Max(Minimum, Math.Min(Maximum, value));

    private static bool TryParse(string text, out double value) =>
        double.TryParse(text.Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out value);

    private bool IsAllowed(char c) =>
        char.IsAsciiDigit(c) || (c == '.' && Decimals > 0) || (c == '-' && Minimum < 0);

    protected override void OnPreviewTextInput(TextCompositionEventArgs e)
    {
        base.OnPreviewTextInput(e);
        if (!e.Text.All(IsAllowed))
            e.Handled = true;
    }

    protected override void OnPreviewKeyDown(KeyEventArgs e)
    {
        base.OnPreviewKeyDown(e);
        if (e.Handled || KeyState.Modifiers != ModifierKeys.None)
            return;
        switch (e.Key)
        {
            case Key.Up: StepBy(1); e.Handled = true; break;
            case Key.Down: StepBy(-1); e.Handled = true; break;
            case Key.PageUp: StepBy(10); e.Handled = true; break;
            case Key.PageDown: StepBy(-10); e.Handled = true; break;
            case Key.Enter:
                Finish();
                SelectAll();
                e.Handled = true;
                break;
        }
    }

    private void StepBy(int steps)
    {
        var next = Clamp(Math.Round(Value + steps * Step, Math.Max(Decimals, 0)));
        _value = next;
        Text = Format(next);
        SelectAll();
    }
}
