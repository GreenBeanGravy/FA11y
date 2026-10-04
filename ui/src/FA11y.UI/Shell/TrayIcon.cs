using System.Drawing;
using System.Windows;
using System.Windows.Forms;
using FA11y.UI.Core;
using Application = System.Windows.Application;

namespace FA11y.UI.Shell;

/// <summary>
/// The notification area icon. Click opens the window; the menu has Open FA11y, Play Fortnite,
/// Settings and Quit FA11y. Notifications from the core appear as balloon tips (Windows shows
/// them as toasts). This is the only WinForms in the program.
/// </summary>
public sealed class TrayIcon : IDisposable
{
    private readonly NotifyIcon _icon;
    private readonly ContextMenuStrip _menu;

    public TrayIcon(Action open, Action play, Action settings, Action quit)
    {
        _menu = new ContextMenuStrip
        {
            Renderer = new DarkRenderer(),
            BackColor = DarkColors.Surface,
            ForeColor = DarkColors.Text,
            ShowImageMargin = false,
            Font = new Font("Segoe UI", 10f),
        };
        AddItem("Open FA11y", open);
        AddItem("Play Fortnite", play);
        AddItem("Settings", settings);
        _menu.Items.Add(new ToolStripSeparator());
        AddItem("Quit FA11y", quit);

        _icon = new NotifyIcon
        {
            Icon = LoadIcon(),
            Text = "FA11y",
            ContextMenuStrip = _menu,
            Visible = true,
        };
        _icon.MouseUp += (_, e) =>
        {
            if (e.Button == MouseButtons.Left)
                open();
        };
    }

    private void AddItem(string text, Action action)
    {
        var item = new ToolStripMenuItem(text) { ForeColor = DarkColors.Text, Padding = new Padding(4, 4, 4, 4) };
        item.Click += (_, _) => action();
        _menu.Items.Add(item);
    }

    public void Notify(string title, string message)
    {
        // Windows already shows the app name as the toast header, so most notifications have no title.
        _icon.BalloonTipTitle = title ?? "";
        _icon.BalloonTipText = string.IsNullOrEmpty(message) ? " " : message;
        _icon.BalloonTipIcon = ToolTipIcon.None;
        _icon.ShowBalloonTip(5000);
    }

    private static Icon LoadIcon()
    {
        try
        {
            var stream = Application.GetResourceStream(new Uri("pack://application:,,,/Assets/fa11y.ico"))?.Stream;
            if (stream != null)
            {
                using (stream)
                    return new Icon(stream, SystemInformation.SmallIconSize);
            }
        }
        catch (Exception e)
        {
            Log.Error("Loading the tray icon failed", e);
        }
        return SystemIcons.Application;
    }

    public void Dispose()
    {
        _icon.Visible = false;
        _icon.Dispose();
        _menu.Dispose();
    }

    private static class DarkColors
    {
        public static readonly Color Surface = Color.FromArgb(0x25, 0x25, 0x25);
        public static readonly Color Hover = Color.FromArgb(0x30, 0x30, 0x2E);
        public static readonly Color Border = Color.FromArgb(0x5F, 0x5E, 0x5A);
        public static readonly Color Text = Color.FromArgb(0xE8, 0xE6, 0xDF);
    }

    private sealed class DarkTable : ProfessionalColorTable
    {
        public override Color ToolStripDropDownBackground => DarkColors.Surface;
        public override Color MenuBorder => DarkColors.Border;
        public override Color MenuItemBorder => DarkColors.Hover;
        public override Color MenuItemSelected => DarkColors.Hover;
        public override Color MenuItemSelectedGradientBegin => DarkColors.Hover;
        public override Color MenuItemSelectedGradientEnd => DarkColors.Hover;
        public override Color ImageMarginGradientBegin => DarkColors.Surface;
        public override Color ImageMarginGradientMiddle => DarkColors.Surface;
        public override Color ImageMarginGradientEnd => DarkColors.Surface;
        public override Color SeparatorDark => DarkColors.Border;
        public override Color SeparatorLight => DarkColors.Border;
    }

    private sealed class DarkRenderer : ToolStripProfessionalRenderer
    {
        public DarkRenderer() : base(new DarkTable()) { RoundedEdges = false; }

        protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
        {
            e.TextColor = DarkColors.Text;
            base.OnRenderItemText(e);
        }
    }
}
