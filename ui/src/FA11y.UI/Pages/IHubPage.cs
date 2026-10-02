using System.Windows;

namespace FA11y.UI.Pages;

/// <summary>One page of the window, shown when its sidebar entry is selected.</summary>
public interface IHubPage
{
    string Key { get; }

    /// <summary>The page's name; the window title is "FA11y - " plus this.</summary>
    string Title { get; }

    /// <summary>The page became visible (also called again when the window is shown on it).</summary>
    void OnShown();

    /// <summary>Another page replaced this one.</summary>
    void OnHidden();

    /// <summary>The control that gets focus when the user moves into the page.</summary>
    FrameworkElement? FirstFocus();

    /// <summary>Escape was pressed. Return true if the page used it (for example to leave a sub-view).</summary>
    bool HandleEscape();

    /// <summary>The core says this page's data changed; reload it.</summary>
    void Refresh();
}
