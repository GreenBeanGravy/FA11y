using System.Windows;
using System.Windows.Controls;

namespace FA11y.UI.Pages;

/// <summary>Shared behavior of the pages: the window they are in, and no-op defaults for IHubPage.</summary>
public abstract class PageBase : UserControl, IHubPage
{
    public abstract string Key { get; }
    public abstract string Title { get; }

    protected Window? Host => Window.GetWindow(this);

    public virtual void OnShown() { }
    public virtual void OnHidden() { }
    public virtual FrameworkElement? FirstFocus() => null;
    public virtual bool HandleEscape() => false;
    public virtual void Refresh() { }
}
