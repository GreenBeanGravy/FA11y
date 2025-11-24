"""
Epic Games Login Dialog for FA11y
Combined dialog with browser login and manual code entry options
"""
import wx
import webbrowser
import logging
import json
import re
from accessible_output2.outputs.auto import Auto

from lib.guis.gui_utilities import AccessibleDialog, BoxSizerHelper, messageBox

logger = logging.getLogger(__name__)
speaker = Auto()


class LoginDialog(AccessibleDialog):
    """Dialog for Epic Games authentication with multiple login methods"""

    def __init__(self, parent, auth_instance):
        super().__init__(parent, title="Epic Games Login", helpId="EpicLogin")
        self.auth = auth_instance
        self.auth_url = None
        self.authenticated = False
        self.success_announced = False
        self.setupDialog()
        self.SetSize((650, 550))
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
            label="Choose a login method below. Browser login is recommended for easier authentication."
        )
        instructions.Wrap(600)
        sizer.addItem(instructions)

        # Create notebook for login methods
        self.notebook = wx.Notebook(self)

        # Browser Login Tab
        browser_panel = wx.Panel(self.notebook)
        browser_sizer = wx.BoxSizer(wx.VERTICAL)

        browser_instructions = wx.StaticText(
            browser_panel,
            label="Click 'Open Browser Login' to log in with your browser.\n"
                  "This opens an embedded browser where you can log in using any method\n"
                  "(Epic account, Google, Facebook, etc.).\n\n"
                  "After logging in, click 'I'm Logged In' in the browser window."
        )
        browser_instructions.Wrap(580)
        browser_sizer.Add(browser_instructions, 0, wx.ALL, 10)

        self.browser_login_btn = wx.Button(browser_panel, label="&Open Browser Login")
        self.browser_login_btn.Bind(wx.EVT_BUTTON, self.on_browser_login)
        browser_sizer.Add(self.browser_login_btn, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        browser_panel.SetSizer(browser_sizer)
        self.notebook.AddPage(browser_panel, "Browser Login")

        # Manual Code Tab
        manual_panel = wx.Panel(self.notebook)
        manual_sizer = wx.BoxSizer(wx.VERTICAL)

        manual_instructions = wx.StaticText(
            manual_panel,
            label="Alternative method: Get an authorization code manually.\n\n"
                  "1. Click 'Open Authorization Page' to open your browser\n"
                  "2. Log in to your Epic Games account\n"
                  "3. Copy the authorization code from the page\n"
                  "4. Paste the code below and click 'Submit Code'"
        )
        manual_instructions.Wrap(580)
        manual_sizer.Add(manual_instructions, 0, wx.ALL, 10)

        self.start_manual_btn = wx.Button(manual_panel, label="Open &Authorization Page")
        self.start_manual_btn.Bind(wx.EVT_BUTTON, self.on_start_login)
        manual_sizer.Add(self.start_manual_btn, 0, wx.ALL, 10)

        # Code input section
        code_label = wx.StaticText(manual_panel, label="Authorization &Code:")
        manual_sizer.Add(code_label, 0, wx.LEFT | wx.TOP, 10)

        self.code_input = wx.TextCtrl(manual_panel, style=wx.TE_PROCESS_ENTER)
        self.code_input.Bind(wx.EVT_TEXT_ENTER, self.on_submit_code)
        self.code_input.Bind(wx.EVT_KEY_DOWN, self.on_code_input_key)
        self.code_input.Enable(False)
        manual_sizer.Add(self.code_input, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.submit_btn = wx.Button(manual_panel, label="&Submit Code")
        self.submit_btn.Bind(wx.EVT_BUTTON, self.on_submit_code)
        self.submit_btn.Enable(False)
        manual_sizer.Add(self.submit_btn, 0, wx.ALL, 10)

        manual_panel.SetSizer(manual_sizer)
        self.notebook.AddPage(manual_panel, "Manual Code")

        sizer.addItem(self.notebook, flag=wx.EXPAND, proportion=1)

        # Status text
        status_label = wx.StaticText(self, label="Status:")
        sizer.addItem(status_label)

        self.status_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 80)
        )
        sizer.addItem(self.status_text, flag=wx.EXPAND)

        # Cancel button
        self.cancel_btn = wx.Button(self, label="&Cancel")
        self.cancel_btn.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))
        sizer.addItem(self.cancel_btn)

        # Bind key events
        self.Bind(wx.EVT_CHAR_HOOK, self.onKeyEvent)

    def onKeyEvent(self, event):
        """Handle key events"""
        key_code = event.GetKeyCode()
        if key_code == wx.WXK_ESCAPE:
            self.EndModal(wx.ID_CANCEL)
            return
        event.Skip()

    def on_code_input_key(self, event):
        """Handle key presses in code input field - enable Ctrl+V paste"""
        key_code = event.GetKeyCode()

        # Check for Ctrl+V (paste)
        if event.ControlDown() and key_code == ord('V'):
            # Manually handle paste from clipboard
            # Retry a few times as clipboard might be busy
            for _ in range(3):
                if wx.TheClipboard.Open():
                    try:
                        if wx.TheClipboard.IsSupported(wx.DataFormat(wx.DF_TEXT)):
                            data = wx.TextDataObject()
                            success = wx.TheClipboard.GetData(data)
                            if success:
                                # Get clipboard text
                                clipboard_text = data.GetText()
                                # Insert at current position
                                insertion_point = self.code_input.GetInsertionPoint()
                                current_text = self.code_input.GetValue()

                                # If there's a selection, replace it
                                sel_start, sel_end = self.code_input.GetSelection()
                                if sel_start != sel_end:
                                    new_text = current_text[:sel_start] + clipboard_text + current_text[sel_end:]
                                    new_pos = sel_start + len(clipboard_text)
                                else:
                                    new_text = current_text[:insertion_point] + clipboard_text + current_text[insertion_point:]
                                    new_pos = insertion_point + len(clipboard_text)

                                self.code_input.SetValue(new_text)
                                self.code_input.SetInsertionPoint(new_pos)
                                break # Success
                    finally:
                        wx.TheClipboard.Close()
                import time
                time.sleep(0.1)
            return  # Don't skip - we handled it

        # Let other keys pass through normally
        event.Skip()

    def _update_status(self, message: str):
        """Update status text"""
        self.status_text.AppendText(message + "\n")

    def on_browser_login(self, event):
        """Handle browser login button"""
        try:
            speaker.speak("Opening browser login")
            self._update_status("Opening browser login window...")
            wx.SafeYield()

            # Import and show browser login dialog
            from lib.guis.epic_browser_login import EpicBrowserLoginDialog

            dialog = EpicBrowserLoginDialog(self, auth_instance=self.auth)
            result = dialog.ShowModal()

            if result == wx.ID_OK and dialog.was_login_successful():
                # Reload auth state from saved cache
                self.auth.load_auth()

                # Check if auth is now valid
                if self.auth.access_token and self.auth.is_valid:
                    self.authenticated = True
                    self.success_announced = True
                    self._update_status(f"✓ Successfully authenticated as {self.auth.display_name}!")
                    speaker.speak(f"Authenticated as {self.auth.display_name}")
                    wx.CallLater(1000, lambda: self.EndModal(wx.ID_OK))
                else:
                    self._update_status("Browser login completed but authentication not confirmed.")
                    self._update_status("Please try the manual code method if issues persist.")
            else:
                self._update_status("Browser login cancelled or failed.")

            dialog.Destroy()

        except Exception as e:
            logger.error(f"Error in browser login: {e}")
            self._update_status(f"Error: {e}")
            speaker.speak("Error in browser login")

    def on_start_login(self, event):
        """Handle Start Login button for manual code method"""
        try:
            speaker.speak("Opening browser for login")
            self._update_status("Getting authorization URL...")
            wx.SafeYield()

            # Get authorization URL
            self.auth_url = self.auth.get_authorization_url()

            self._update_status("✓ Opening browser for Epic Games login...")
            self._update_status("After logging in, copy the authorization code and paste it below.")

            # Open browser
            webbrowser.open(self.auth_url)
            speaker.speak("Browser opened. Please log in and copy the authorization code.")

            # Enable code input and submit button
            self.start_manual_btn.Enable(False)
            self.code_input.Enable(True)
            self.submit_btn.Enable(True)
            self.code_input.SetFocus()

        except Exception as e:
            logger.error(f"Error starting login: {e}")
            speaker.speak("Error starting login")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

    @staticmethod
    def parse_auth_code(raw_input: str) -> str:
        """
        Parse authorization code from various input formats:
        1. Full JSON response: {"authorizationCode": "...", ...}
        2. Code in quotes: "01fec44ab47f47a1a62a5a325765046f"
        3. Plain code: 01fec44ab47f47a1a62a5a325765046f

        Returns the clean authorization code
        """
        if not raw_input:
            return ""

        # Strip leading/trailing whitespace
        raw_input = raw_input.strip()

        # Try to parse as JSON first
        try:
            data = json.loads(raw_input)
            # Check if it's a dict with authorizationCode field
            if isinstance(data, dict) and "authorizationCode" in data:
                code = data["authorizationCode"]
                if code:  # Make sure it's not null
                    logger.info("Parsed auth code from JSON format")
                    return str(code).strip()
        except (json.JSONDecodeError, ValueError):
            # Not JSON, continue with other parsing methods
            pass

        # Remove quotes if present (handles both single and double quotes)
        if (raw_input.startswith('"') and raw_input.endswith('"')) or \
           (raw_input.startswith("'") and raw_input.endswith("'")):
            code = raw_input[1:-1].strip()
            logger.info("Parsed auth code from quoted format")
            return code

        # Return as-is (plain code format)
        logger.info("Parsed auth code from plain format")
        return raw_input

    def on_submit_code(self, event):
        """Handle Submit Code button"""
        try:
            # Get the authorization code from the input and parse it
            raw_input = self.code_input.GetValue()
            auth_code = self.parse_auth_code(raw_input)

            if not auth_code:
                speaker.speak("Please enter an authorization code")
                messageBox(
                    "Please enter the authorization code from the browser.",
                    "Code Required",
                    wx.OK | wx.ICON_WARNING,
                    self
                )
                return

            speaker.speak("Exchanging authorization code for access token")
            self._update_status("Exchanging code for access token...")
            wx.SafeYield()

            # Disable input during exchange
            self.code_input.Enable(False)
            self.submit_btn.Enable(False)

            # Exchange code for token
            success = self.auth.exchange_code_for_token(auth_code)

            if success:
                self.authenticated = True
                self.success_announced = True
                speaker.speak(f"Authenticated as {self.auth.display_name}")
                self._update_status(f"✓ Successfully authenticated as {self.auth.display_name}!")
                wx.CallLater(1000, lambda: self.EndModal(wx.ID_OK))
            else:
                speaker.speak("Authentication failed")
                self._update_status("✗ Authentication failed. Please check your code and try again.")
                messageBox(
                    "Failed to authenticate with the provided code. The code may be invalid or expired.\n\n"
                    "Please click 'Open Authorization Page' again to get a new code.",
                    "Authentication Failed",
                    wx.OK | wx.ICON_ERROR,
                    self
                )
                # Re-enable login button so user can try again
                self.start_manual_btn.Enable(True)
                self.code_input.Enable(False)
                self.submit_btn.Enable(False)
                self.code_input.Clear()

        except Exception as e:
            logger.error(f"Error submitting code: {e}")
            speaker.speak("Error submitting code")
            self._update_status(f"✗ Error: {e}")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)
            # Re-enable controls for retry
            self.code_input.Enable(True)
            self.submit_btn.Enable(True)
