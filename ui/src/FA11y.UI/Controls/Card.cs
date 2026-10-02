using System.Windows;
using System.Windows.Controls;

namespace FA11y.UI.Controls;

/// <summary>A rounded, bordered panel (the look of widgets.Card). It has no accessible element of its own.</summary>
public class Card : Border
{
    static Card()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(Card), new FrameworkPropertyMetadata(typeof(Card)));
    }
}
