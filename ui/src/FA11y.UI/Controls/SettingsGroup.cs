using System.Windows;
using System.Windows.Controls;

namespace FA11y.UI.Controls;

/// <summary>
/// A card with a heading holding related settings. Screen readers
/// hear the heading as the group's name when focus moves in, for example "Announcements grouping".
/// </summary>
public sealed class SettingsGroup : GroupBox
{
    static SettingsGroup()
    {
        DefaultStyleKeyProperty.OverrideMetadata(typeof(SettingsGroup), new FrameworkPropertyMetadata(typeof(SettingsGroup)));
    }
}
