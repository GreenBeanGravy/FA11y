using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Peers;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace FA11y.UI.Controls;

/// <summary>A radio button as one element: its label text is not a separate item.</summary>
public sealed class RadioOption : RadioButton
{
    static RadioOption()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(RadioOption), new FrameworkPropertyMetadata(typeof(RadioOption)));
    }

    protected override AutomationPeer OnCreateAutomationPeer() => new LeafRadioPeer(this);

    private sealed class LeafRadioPeer : RadioButtonAutomationPeer
    {
        public LeafRadioPeer(RadioOption owner) : base(owner) { }

        protected override List<AutomationPeer>? GetChildrenCore() => null;
    }
}

/// <summary>
/// A set of <see cref="RadioOption"/>s with a name. Screen readers see a
/// group with that name around the radio buttons. Tab reaches the chosen one, the arrow keys move
/// and choose. An underscore in the header ("_Graphics") makes an access key that focuses the
/// chosen option.
/// </summary>
public sealed class RadioGroup : ContentControl
{
    private static int _groups;
    private readonly string _groupName = $"RadioGroup{++_groups}";

    public static readonly DependencyProperty HeaderProperty =
        DependencyProperty.Register(nameof(Header), typeof(string), typeof(RadioGroup),
            new PropertyMetadata("", (d, _) => ((RadioGroup)d).UpdateName()));

    static RadioGroup()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(RadioGroup), new FrameworkPropertyMetadata(typeof(RadioGroup)));
        FocusableProperty.OverrideMetadata(typeof(RadioGroup), new FrameworkPropertyMetadata(false));
    }

    public RadioGroup()
    {
        Loaded += (_, _) => Adopt();
        AddHandler(System.Windows.Controls.Primitives.ToggleButton.CheckedEvent, new RoutedEventHandler((_, _) => UpdateTabStops()));
    }

    /// <summary>Tab reaches the chosen option only (the first when none is chosen); the arrow keys do the rest.</summary>
    private void UpdateTabStops()
    {
        var options = Options.ToList();
        var chosen = options.FirstOrDefault(o => o.IsChecked == true) ?? options.FirstOrDefault();
        foreach (var option in options)
            option.IsTabStop = option == chosen;
    }

    protected override void OnPreviewKeyDown(KeyEventArgs e)
    {
        base.OnPreviewKeyDown(e);
        if (Keyboard.Modifiers != ModifierKeys.None || e.OriginalSource is not RadioOption current)
            return;
        var step = e.Key switch { Key.Down or Key.Right => 1, Key.Up or Key.Left => -1, _ => 0 };
        if (step == 0)
            return;
        var options = Options.Where(o => o.IsEnabled && o.IsVisible).ToList();
        var index = options.IndexOf(current);
        if (index < 0)
            return;
        e.Handled = true;
        var next = options[(index + step + options.Count) % options.Count];
        next.IsChecked = true;
        next.Focus();
    }

    public string Header
    {
        get => (string)GetValue(HeaderProperty);
        set => SetValue(HeaderProperty, value);
    }

    public IEnumerable<RadioOption> Options => Find(this);

    /// <summary>Index of the chosen option, or -1.</summary>
    public int SelectedIndex
    {
        get => Options.Select((o, i) => (o, i)).FirstOrDefault(p => p.o.IsChecked == true) is { o: not null } hit
            ? hit.i : -1;
        set
        {
            var options = Options.ToList();
            for (var i = 0; i < options.Count; i++)
                options[i].IsChecked = i == value;
        }
    }

    private void UpdateName() => AutomationProperties.SetName(this, Header.Replace("_", ""));

    private void Adopt()
    {
        foreach (var option in Options)
            if (string.IsNullOrEmpty(option.GroupName))
                option.GroupName = _groupName;
        UpdateTabStops();
    }

    /// <summary>Focus the chosen option (the first when none is chosen); what the header's access key does.</summary>
    public void FocusChosen()
    {
        var options = Options.Where(o => o.IsEnabled && o.IsVisible).ToList();
        (options.FirstOrDefault(o => o.IsChecked == true) ?? options.FirstOrDefault())?.Focus();
    }

    private static IEnumerable<RadioOption> Find(DependencyObject parent)
    {
        foreach (var child in LogicalTreeHelper.GetChildren(parent).OfType<DependencyObject>())
        {
            if (child is RadioOption option)
                yield return option;
            else
                foreach (var nested in Find(child))
                    yield return nested;
        }
    }

    protected override AutomationPeer OnCreateAutomationPeer() => new RadioGroupPeer(this);

    private sealed class RadioGroupPeer : FrameworkElementAutomationPeer
    {
        public RadioGroupPeer(RadioGroup owner) : base(owner) { }

        protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.Group;
        protected override string GetClassNameCore() => "RadioGroup";
        protected override bool IsControlElementCore() => true;
        protected override bool IsContentElementCore() => true;
    }
}

/// <summary>
/// A caption with an access key ("E_xtra arguments") that sends focus to its Target, or to the chosen
/// option when it is inside a <see cref="RadioGroup"/>. It is invisible to screen readers: the
/// control it names has its own name.
/// </summary>
public sealed class AccessCaption : TextBlock
{
    public static readonly DependencyProperty CaptionProperty =
        DependencyProperty.Register(nameof(Caption), typeof(string), typeof(AccessCaption),
            new PropertyMetadata("", (d, _) => ((AccessCaption)d).Rebuild()));

    public static readonly DependencyProperty TargetProperty =
        DependencyProperty.Register(nameof(Target), typeof(UIElement), typeof(AccessCaption));

    private string? _registeredKey;

    public string Caption
    {
        get => (string)GetValue(CaptionProperty);
        set => SetValue(CaptionProperty, value);
    }

    public UIElement? Target
    {
        get => (UIElement?)GetValue(TargetProperty);
        set => SetValue(TargetProperty, value);
    }

    protected override AutomationPeer? OnCreateAutomationPeer() => null;

    private void Rebuild()
    {
        if (_registeredKey != null)
            AccessKeyManager.Unregister(_registeredKey, this);
        _registeredKey = null;
        Inlines.Clear();
        var caption = Caption;
        var at = caption.IndexOf('_');
        if (at < 0 || at == caption.Length - 1)
        {
            Inlines.Add(new System.Windows.Documents.Run(caption.Replace("_", "")));
            return;
        }
        Inlines.Add(new System.Windows.Documents.Run(caption[..at]));
        Inlines.Add(new System.Windows.Documents.Underline(new System.Windows.Documents.Run(caption[(at + 1)..(at + 2)])));
        Inlines.Add(new System.Windows.Documents.Run(caption[(at + 2)..]));
        _registeredKey = caption[(at + 1)..(at + 2)];
        AccessKeyManager.Register(_registeredKey, this);
    }

    protected override void OnAccessKey(AccessKeyEventArgs e)
    {
        for (DependencyObject? node = this; node != null; node = VisualTreeHelper.GetParent(node))
        {
            if (node is RadioGroup group)
            {
                group.FocusChosen();
                return;
            }
        }
        Target?.Focus();
    }
}

/// <summary>
/// A box for a whole number: digits only, Up and Down change it by 1,
/// Page Up and Page Down by 10, and a value out of range is brought back to the limits when focus leaves.
/// </summary>
public sealed class WholeNumberBox : TextBox
{
    public static readonly DependencyProperty MinimumProperty =
        DependencyProperty.Register(nameof(Minimum), typeof(int), typeof(WholeNumberBox), new PropertyMetadata(0));

    public static readonly DependencyProperty MaximumProperty =
        DependencyProperty.Register(nameof(Maximum), typeof(int), typeof(WholeNumberBox), new PropertyMetadata(100));

    public int Minimum
    {
        get => (int)GetValue(MinimumProperty);
        set => SetValue(MinimumProperty, value);
    }

    public int Maximum
    {
        get => (int)GetValue(MaximumProperty);
        set => SetValue(MaximumProperty, value);
    }

    /// <summary>The number in the box, kept within the limits; the minimum when the box is empty.</summary>
    public int Value
    {
        get => Clamp(int.TryParse(Text, out var n) ? n : Minimum);
        set => Text = Clamp(value).ToString();
    }

    public WholeNumberBox()
    {
        MaxLength = 6;
        InputScope = new InputScope { Names = { new InputScopeName(InputScopeNameValue.Number) } };
        LostKeyboardFocus += (_, _) => Text = Value.ToString();
        DataObject.AddPastingHandler(this, (_, e) =>
        {
            if (e.DataObject.GetData(typeof(string)) is not string pasted || !pasted.All(char.IsDigit))
                e.CancelCommand();
        });
    }

    private int Clamp(int n) => Math.Max(Minimum, Math.Min(Maximum, n));

    protected override void OnPreviewTextInput(TextCompositionEventArgs e)
    {
        base.OnPreviewTextInput(e);
        if (!e.Text.All(char.IsDigit))
            e.Handled = true;
    }

    protected override void OnPreviewKeyDown(KeyEventArgs e)
    {
        base.OnPreviewKeyDown(e);
        var step = e.Key switch { Key.Up => 1, Key.Down => -1, Key.PageUp => 10, Key.PageDown => -10, _ => 0 };
        if (step == 0 || Keyboard.Modifiers != ModifierKeys.None)
            return;
        e.Handled = true;
        Value += step;
        SelectAll();
    }
}
