using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Peers;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace FA11y.UI.Controls;

/// <summary>One page in the sidebar. Heading is the section title drawn above it when it starts a section.</summary>
public sealed class NavListItem : ListBoxItem
{
    public static readonly DependencyProperty LabelProperty =
        DependencyProperty.Register(nameof(Label), typeof(string), typeof(NavListItem), new PropertyMetadata(""));

    public static readonly DependencyProperty IconProperty =
        DependencyProperty.Register(nameof(Icon), typeof(Geometry), typeof(NavListItem));

    public static readonly DependencyProperty HeadingProperty =
        DependencyProperty.Register(nameof(Heading), typeof(string), typeof(NavListItem), new PropertyMetadata(""));

    static NavListItem()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(NavListItem), new FrameworkPropertyMetadata(typeof(NavListItem)));
    }

    public NavListItem(string key, string label, Geometry? icon, string group, bool startsSection)
    {
        Key = key;
        Label = label;
        Icon = icon;
        Group = group;
        Heading = startsSection ? group : "";
        // What screen readers get: "Locker", a list item in the list "Pages". The section heading is
        // drawn but not read, so there is no help text.
        AutomationProperties.SetName(this, label);
    }

    public string Key { get; }
    public string Group { get; }

    public string Label
    {
        get => (string)GetValue(LabelProperty);
        set => SetValue(LabelProperty, value);
    }

    public Geometry? Icon
    {
        get => (Geometry?)GetValue(IconProperty);
        set => SetValue(IconProperty, value);
    }

    public string Heading
    {
        get => (string)GetValue(HeadingProperty);
        set => SetValue(HeadingProperty, value);
    }
}

/// <summary>
/// The sidebar: a list named "Pages" whose items are the pages. Arrow keys, Home, End and typing
/// a letter move the selection (and focus with it); Enter or Right arrow asks to move into the page.
/// </summary>
public sealed class NavList : ListBox
{
    static NavList()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(NavList), new FrameworkPropertyMetadata(typeof(NavList)));
    }

    public NavList()
    {
        SelectionMode = SelectionMode.Single;
        AutomationProperties.SetName(this, "Pages");
        ItemsPanel = new ItemsPanelTemplate(new FrameworkElementFactory(typeof(StackPanel)));
        TextSearch.SetTextPath(this, nameof(NavListItem.Label));
    }

    /// <summary>Enter or Right arrow on an item: the user wants to move into the page.</summary>
    public event Action? Activate;

    public IEnumerable<NavListItem> Pages => Items.OfType<NavListItem>();

    protected override DependencyObject GetContainerForItemOverride() =>
        throw new InvalidOperationException("Add NavListItem objects directly.");

    protected override bool IsItemItsOwnContainerOverride(object item) => item is NavListItem;

    protected override AutomationPeer OnCreateAutomationPeer() => new NavListPeer(this);

    /// <summary>The default list peer, plus the access key of the "Pages:" label, which WPF does not pass on by itself.</summary>
    private sealed class NavListPeer : ListBoxAutomationPeer
    {
        public NavListPeer(NavList owner) : base(owner) { }

        protected override string GetAccessKeyCore() => "Alt+P";
    }

    // Alt+P on the "Pages:" label focuses the list; hand focus on to the selected page.
    protected override void OnGotKeyboardFocus(KeyboardFocusChangedEventArgs e)
    {
        base.OnGotKeyboardFocus(e);
        if (ReferenceEquals(e.NewFocus, this))
            FocusSelected();
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (Keyboard.Modifiers == ModifierKeys.None && e.Key is Key.Enter or Key.Right)
        {
            e.Handled = true;
            Activate?.Invoke();
            return;
        }
        base.OnKeyDown(e);
    }

    /// <summary>Put keyboard focus on the selected item.</summary>
    public bool FocusSelected()
    {
        var item = SelectedItem as NavListItem ?? Pages.FirstOrDefault();
        return item != null && item.Focus();
    }

    public bool HasFocusInside => IsKeyboardFocusWithin;
}
