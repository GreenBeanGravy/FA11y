"""
Epic Games Login Dialog for FA11y
"""
import wx
import webbrowser
import threading
import logging
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import AccessibleDialog, BoxSizerHelper, messageBox

logger = logging.getLogger(__name__)
speaker = Auto()


class LoginDialog(AccessibleDialog):
    """Dialog for Epic Games device code authentication"""

    def __init__(self, parent, auth_instance):
        super().__init__(parent, title="Epic Games Login", helpId="EpicLogin")
        self.auth = auth_instance
        self.device_code_data = None
        self.auth_thread = None
        self.authenticated = False
        self.setupDialog()
        self.SetSize((600, 400))
        self.CentreOnParent()

    def makeSettings(self, sizer: BoxSizerHelper):
        """Create dialog content"""

        # Title
        title_label = wx.StaticText(self, label="Login to Epic Games")
        title_font = title_label.GetFont()
        title_font.PointSize += 3
        title_font = title_font.Bold()
        title_label.SetFont(title_font)
        sizer.addItem(title_label)

        # Instructions
        instructions = wx.StaticText(
            self,
            label="To access your Fortnite locker, you need to log in with your Epic Games account.\n\n"
                  "Click 'Start Login' below to begin the authentication process."
        )
        instructions.Wrap(550)
        sizer.addItem(instructions)

        # Status text
        self.status_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 150)
        )
        sizer.addItem(self.status_text, flag=wx.EXPAND, proportion=1)

        # Buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.login_btn = wx.Button(self, label="&Start Login")
        self.login_btn.Bind(wx.EVT_BUTTON, self.on_start_login)
        button_sizer.Add(self.login_btn)

        button_sizer.AddSpacer(10)

        self.open_browser_btn = wx.Button(self, label="&Open Browser")
        self.open_browser_btn.Bind(wx.EVT_BUTTON, self.on_open_browser)
        self.open_browser_btn.Enable(False)
        button_sizer.Add(self.open_browser_btn)

        button_sizer.AddStretchSpacer()

        self.cancel_btn = wx.Button(self, label="&Cancel")
        self.cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))
        button_sizer.Add(self.cancel_btn)

        sizer.addItem(button_sizer, flag=wx.EXPAND)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

    def onKeyEvent(self, event):
        """Handle key events"""
        key_code = event.GetKeyCode()
        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()

    def on_start_login(self, event):
        """Handle Start Login button"""
        try:
            speaker.speak("Starting authentication process")
            self.status_text.AppendText("Requesting device code from Epic Games...\n")
            wx.SafeYield()

            # Get device code
            self.device_code_data = self.auth.authenticate_device_code()

            if not self.device_code_data:
                speaker.speak("Failed to get device code")
                messageBox(
                    "Failed to get device code from Epic Games. Please check your internet connection.",
                    "Authentication Error",
                    wx.OK | wx.ICON_ERROR,
                    self
                )
                return

            # Show the verification URL and user code
            user_code = self.device_code_data["user_code"]
            verification_uri = self.device_code_data["verification_uri"]

            message = (
                f"\n✓ Device code obtained!\n\n"
                f"To complete login:\n"
                f"1. Open this URL in your browser:\n   {verification_uri}\n\n"
                f"2. The page should automatically fill in the code.\n"
                f"   If not, enter this code: {user_code}\n\n"
                f"3. Authorize FA11y to access your Epic Games account\n\n"
                f"Waiting for authorization...\n"
            )

            self.status_text.AppendText(message)
            speaker.speak(f"Device code received. Click Open Browser to log in.")

            # Enable browser button, disable login button
            self.login_btn.Enable(False)
            self.open_browser_btn.Enable(True)
            self.open_browser_btn.SetFocus()

            # Start polling for token in background thread
            self.auth_thread = threading.Thread(target=self.poll_for_auth, daemon=True)
            self.auth_thread.start()

        except Exception as e:
            logger.error(f"Error starting login: {e}")
            speaker.speak("Error starting login")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

    def on_open_browser(self, event):
        """Open browser to verification URL"""
        if self.device_code_data:
            verification_uri = self.device_code_data["verification_uri"]
            webbrowser.open(verification_uri)
            speaker.speak("Browser opened. Please log in and authorize FA11y.")
            self.status_text.AppendText("\n✓ Browser opened. Please log in and authorize FA11y.\n")

    def poll_for_auth(self):
        """Poll for authentication in background thread"""
        try:
            device_code = self.device_code_data["device_code"]
            interval = self.device_code_data["interval"]

            success = self.auth.poll_for_token(device_code, interval)

            # Update UI on main thread
            wx.CallAfter(self.on_auth_complete, success)

        except Exception as e:
            logger.error(f"Error polling for auth: {e}")
            wx.CallAfter(self.on_auth_error, str(e))

    def on_auth_complete(self, success: bool):
        """Handle authentication completion"""
        if success:
            self.authenticated = True
            speaker.speak(f"Successfully logged in as {self.auth.display_name}")
            self.status_text.AppendText(f"\n✓ Successfully authenticated as {self.auth.display_name}!\n")
            wx.CallLater(1000, lambda: self.EndModal(wx.ID_OK))
        else:
            speaker.speak("Authentication failed")
            self.status_text.AppendText("\n✗ Authentication failed or timed out.\n")
            messageBox(
                "Authentication failed. Please try again.",
                "Authentication Failed",
                wx.OK | wx.ICON_ERROR,
                self
            )
            self.login_btn.Enable(True)
            self.open_browser_btn.Enable(False)

    def on_auth_error(self, error: str):
        """Handle authentication error"""
        speaker.speak("Authentication error")
        self.status_text.AppendText(f"\n✗ Error: {error}\n")
        messageBox(f"Authentication error: {error}", "Error", wx.OK | wx.ICON_ERROR, self)
        self.login_btn.Enable(True)
        self.open_browser_btn.Enable(False)
