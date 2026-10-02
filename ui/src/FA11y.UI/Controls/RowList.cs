using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Controls;
using System.Windows.Data;
using System.Windows.Input;

namespace FA11y.UI.Controls;

/// <summary>One line of a <see cref="RowList"/>. Label is what a screen reader reads; Key identifies the row across reloads.</summary>
public sealed class ListRow : INotifyPropertyChanged
{
    private string _label;
    private string _details;

    public ListRow(string key, string label, string details = "", object? tag = null)
    {
        Key = key;
        _label = label;
        _details = details;
        Tag = tag;
    }

    public string Key { get; }
    public object? Tag { get; }

    public string Label
    {
        get => _label;
        set
        {
            if (_label == value)
                return;
            _label = value;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Label)));
        }
    }

    /// <summary>Text for a details box that follows the selection.</summary>
    public string Details
    {
        get => _details;
        set
        {
            if (_details == value)
                return;
            _details = value;
            PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(nameof(Details)));
        }
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public override string ToString() => _label;
}

/// <summary>
/// A list of text rows, like the wx list boxes. One Tab stop (the selected row), arrow keys move
/// focus with the selection, typing a letter jumps to a row, and the list is virtualized so long
/// lists stay fast. With <see cref="Wrap"/>, Up on the first row goes to the last and Down on the
/// last goes to the first. Enter raises <see cref="Activated"/>, as does a double click.
/// </summary>
public class RowList : ListBox
{
    private readonly ObservableCollection<ListRow> _rows = new();

    public RowList()
    {
        // Look like every other ListBox in the window (the theme styles ListBox by exact type).
        if (Application.Current?.TryFindResource(typeof(ListBox)) is Style listStyle)
            Style = listStyle;
        ItemsSource = _rows;
        SelectionMode = SelectionMode.Single;
        KeyboardNavigation.SetTabNavigation(this, KeyboardNavigationMode.Once);
        KeyboardNavigation.SetDirectionalNavigation(this, KeyboardNavigationMode.Contained);
        ScrollViewer.SetCanContentScroll(this, true);
        VirtualizingPanel.SetIsVirtualizing(this, true);
        VirtualizingPanel.SetScrollUnit(this, ScrollUnit.Item);
        TextSearch.SetTextPath(this, nameof(ListRow.Label));
        var text = new FrameworkElementFactory(typeof(TextBlock));
        text.SetBinding(TextBlock.TextProperty, new Binding(nameof(ListRow.Label)));
        text.SetValue(TextBlock.TextWrappingProperty, TextWrapping.Wrap);
        ItemTemplate = new DataTemplate { VisualTree = text };
        var style = new Style(typeof(ListBoxItem), Application.Current?.TryFindResource(typeof(ListBoxItem)) as Style);
        style.Setters.Add(new Setter(AutomationProperties.NameProperty, new Binding(nameof(ListRow.Label))));
        ItemContainerStyle = style;
    }

    /// <summary>Up on the first row goes to the last, Down on the last goes to the first.</summary>
    public bool Wrap { get; set; }

    public IReadOnlyList<ListRow> Rows => _rows;

    public ListRow? SelectedRow => SelectedItem as ListRow;

    /// <summary>Enter on a row, or a double click on it.</summary>
    public event Action<ListRow>? Activated;

    /// <summary>
    /// Show these rows. If they are the same rows as before (by key) only changed labels and
    /// details are updated, so the list keeps its position. Otherwise the selection stays on the
    /// same key when it is still there, else on the first row. Focus stays in the list if it was.
    /// </summary>
    public void SetRows(IReadOnlyList<ListRow> rows)
    {
        var hadFocus = IsKeyboardFocusWithin;
        var selectedKey = SelectedRow?.Key;
        var same = rows.Count == _rows.Count;
        for (var i = 0; same && i < rows.Count; i++)
            same = rows[i].Key == _rows[i].Key;
        if (same)
        {
            for (var i = 0; i < rows.Count; i++)
            {
                _rows[i].Label = rows[i].Label;
                _rows[i].Details = rows[i].Details;
            }
            if (SelectedItem == null && _rows.Count > 0)
                SelectedIndex = 0;
            return;
        }
        _rows.Clear();
        foreach (var row in rows)
            _rows.Add(row);
        if (_rows.Count == 0)
            return;
        var index = selectedKey == null ? 0 : Math.Max(0, _rows.ToList().FindIndex(r => r.Key == selectedKey));
        SelectedIndex = index;
        if (hadFocus)
            FocusRow(index);
    }

    /// <summary>Put keyboard focus on a row, scrolling it into view first.</summary>
    public void FocusRow(int index)
    {
        if (index < 0 || index >= _rows.Count)
            return;
        SelectedIndex = index;
        ScrollIntoView(_rows[index]);
        UpdateLayout();
        if (ItemContainerGenerator.ContainerFromIndex(index) is ListBoxItem item)
            item.Focus();
        else
            Focus();
    }

    /// <summary>Focus the selected row (or the first).</summary>
    public bool FocusSelected()
    {
        if (_rows.Count == 0)
            return Focus();
        FocusRow(SelectedIndex < 0 ? 0 : SelectedIndex);
        return true;
    }

    // Focus that lands on the list itself (Tab, or Focus()) goes to the selected row, which is what is named.
    protected override void OnGotKeyboardFocus(KeyboardFocusChangedEventArgs e)
    {
        base.OnGotKeyboardFocus(e);
        if (e.NewFocus == this && _rows.Count > 0)
            Dispatcher.BeginInvoke(() =>
            {
                if (IsKeyboardFocused)
                    FocusRow(SelectedIndex < 0 ? 0 : SelectedIndex);
            });
    }

    protected override void OnKeyDown(KeyEventArgs e)
    {
        if (Keyboard.Modifiers == ModifierKeys.None && _rows.Count > 0)
        {
            if (e.Key == Key.Enter && SelectedRow is { } row)
            {
                e.Handled = true;
                Activated?.Invoke(row);
                return;
            }
            if (Wrap && e.Key == Key.Up && SelectedIndex <= 0)
            {
                e.Handled = true;
                FocusRow(_rows.Count - 1);
                return;
            }
            if (Wrap && e.Key == Key.Down && SelectedIndex == _rows.Count - 1)
            {
                e.Handled = true;
                FocusRow(0);
                return;
            }
            if (e.Key is Key.Left or Key.Right)
            {
                e.Handled = true; // like the wx lists: sideways does nothing
                return;
            }
        }
        base.OnKeyDown(e);
    }

    protected override void OnMouseDoubleClick(MouseButtonEventArgs e)
    {
        base.OnMouseDoubleClick(e);
        if (SelectedRow is { } row && e.OriginalSource is DependencyObject source && ItemsControl.ContainerFromElement(this, source) != null)
            Activated?.Invoke(row);
    }
}
