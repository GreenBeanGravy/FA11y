<<<<<<< HEAD
"""
Epic Games Login Dialog for FA11y
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
    """Dialog for Epic Games manual authorization code authentication"""

    def __init__(self, parent, auth_instance):
        super().__init__(parent, title="Epic Games Login", helpId="EpicLogin")
        self.auth = auth_instance
        self.auth_url = None
        self.authenticated = False
        self.setupDialog()
        self.SetSize((600, 450))
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
                  "Click 'Start Login' to open your browser and get an authorization code."
        )
        instructions.Wrap(550)
        sizer.addItem(instructions)

        # Status text
        self.status_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 120)
        )
        sizer.addItem(self.status_text, flag=wx.EXPAND, proportion=1)

        # Authorization code input section
        code_label = wx.StaticText(self, label="&Authorization Code:")
        sizer.addItem(code_label)

        self.code_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.code_input.Bind(wx.EVT_TEXT_ENTER, self.on_submit_code)
        self.code_input.Bind(wx.EVT_KEY_DOWN, self.on_code_input_key)
        self.code_input.Enable(False)
        sizer.addItem(self.code_input, flag=wx.EXPAND)

        # Buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.login_btn = wx.Button(self, label="&Start Login")
        self.login_btn.Bind(wx.EVT_BUTTON, self.on_start_login)
        button_sizer.Add(self.login_btn)

        button_sizer.AddSpacer(10)

        self.submit_btn = wx.Button(self, label="&Submit Code")
        self.submit_btn.Bind(wx.EVT_BUTTON, self.on_submit_code)
        self.submit_btn.Enable(False)
        button_sizer.Add(self.submit_btn)

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

    def on_start_login(self, event):
        """Handle Start Login button"""
        try:
            speaker.speak("Opening browser for login")
            self.status_text.AppendText("Getting authorization URL...\n")
            wx.SafeYield()

            # Get authorization URL
            self.auth_url = self.auth.get_authorization_url()

            message = (
                f"\n✓ Opening browser for Epic Games login...\n\n"
                f"Steps to complete:\n"
                f"1. Log in to your Epic Games account in the browser\n"
                f"2. Authorize FA11y when prompted\n"
                f"3. You will be redirected to a page showing 'redirectUrl=' followed by a code\n"
                f"4. Copy the authorization code from the URL\n"
                f"5. Paste the code below and click Submit Code\n\n"
                f"Browser opening...\n"
            )

            self.status_text.AppendText(message)

            # Open browser
            webbrowser.open(self.auth_url)
            speaker.speak("Browser opened. Please log in and copy the authorization code from the URL.")

            # Enable code input and submit button, disable login button
            self.login_btn.Enable(False)
            self.code_input.Enable(True)
            self.submit_btn.Enable(True)
            self.code_input.SetFocus()

        except Exception as e:
            logger.error(f"Error starting login: {e}")
            speaker.speak("Error starting login")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

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
            self.status_text.AppendText("\nExchanging code for access token...\n")
            wx.SafeYield()

            # Disable input during exchange
            self.code_input.Enable(False)
            self.submit_btn.Enable(False)

            # Exchange code for token
            success = self.auth.exchange_code_for_token(auth_code)

            if success:
                self.authenticated = True
                speaker.speak(f"Successfully logged in as {self.auth.display_name}")
                self.status_text.AppendText(f"\n✓ Successfully authenticated as {self.auth.display_name}!\n")
                wx.CallLater(1000, lambda: self.EndModal(wx.ID_OK))
            else:
                speaker.speak("Authentication failed")
                self.status_text.AppendText("\n✗ Authentication failed. Please check your code and try again.\n")
                messageBox(
                    "Failed to authenticate with the provided code. The code may be invalid or expired.\n\n"
                    "Please click 'Start Login' again to get a new code.",
                    "Authentication Failed",
                    wx.OK | wx.ICON_ERROR,
                    self
                )
                # Re-enable login button so user can try again
                self.login_btn.Enable(True)
                self.code_input.Enable(False)
                self.submit_btn.Enable(False)
                self.code_input.Clear()

        except Exception as e:
            logger.error(f"Error submitting code: {e}")
            speaker.speak("Error submitting code")
            self.status_text.AppendText(f"\n✗ Error: {e}\n")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)
            # Re-enable controls for retry
            self.code_input.Enable(True)
            self.submit_btn.Enable(True)
=======
"""
Epic Games Login Dialog for FA11y
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
    """Dialog for Epic Games manual authorization code authentication"""

    def __init__(self, parent, auth_instance):
        super().__init__(parent, title="Epic Games Login", helpId="EpicLogin")
        self.auth = auth_instance
        self.auth_url = None
        self.authenticated = False
        self.setupDialog()
        self.SetSize((600, 450))
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
                  "Click 'Start Login' to open your browser and get an authorization code."
        )
        instructions.Wrap(550)
        sizer.addItem(instructions)

        # Status text
        self.status_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP,
            size=(-1, 120)
        )
        sizer.addItem(self.status_text, flag=wx.EXPAND, proportion=1)

        # Authorization code input section
        code_label = wx.StaticText(self, label="&Authorization Code:")
        sizer.addItem(code_label)

        self.code_input = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.code_input.Bind(wx.EVT_TEXT_ENTER, self.on_submit_code)
        self.code_input.Bind(wx.EVT_KEY_DOWN, self.on_code_input_key)
        self.code_input.Enable(False)
        sizer.addItem(self.code_input, flag=wx.EXPAND)

        # Buttons
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.login_btn = wx.Button(self, label="&Start Login")
        self.login_btn.Bind(wx.EVT_BUTTON, self.on_start_login)
        button_sizer.Add(self.login_btn)

        button_sizer.AddSpacer(10)

        self.submit_btn = wx.Button(self, label="&Submit Code")
        self.submit_btn.Bind(wx.EVT_BUTTON, self.on_submit_code)
        self.submit_btn.Enable(False)
        button_sizer.Add(self.submit_btn)

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

    def on_code_input_key(self, event):
        """Handle key presses in code input field - enable Ctrl+V paste"""
        key_code = event.GetKeyCode()

        # Check for Ctrl+V (paste)
        if event.ControlDown() and key_code == ord('V'):
            # Manually handle paste from clipboard
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
                finally:
                    wx.TheClipboard.Close()
            return  # Don't skip - we handled it

        # Let other keys pass through normally
        event.Skip()

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

    def on_start_login(self, event):
        """Handle Start Login button"""
        try:
            speaker.speak("Opening browser for login")
            self.status_text.AppendText("Getting authorization URL...\n")
            wx.SafeYield()

            # Get authorization URL
            self.auth_url = self.auth.get_authorization_url()

            message = (
                f"\n✓ Opening browser for Epic Games login...\n\n"
                f"Steps to complete:\n"
                f"1. Log in to your Epic Games account in the browser\n"
                f"2. Authorize FA11y when prompted\n"
                f"3. You will be redirected to a page showing 'redirectUrl=' followed by a code\n"
                f"4. Copy the authorization code from the URL\n"
                f"5. Paste the code below and click Submit Code\n\n"
                f"Browser opening...\n"
            )

            self.status_text.AppendText(message)

            # Open browser
            webbrowser.open(self.auth_url)
            speaker.speak("Browser opened. Please log in and copy the authorization code from the URL.")

            # Enable code input and submit button, disable login button
            self.login_btn.Enable(False)
            self.code_input.Enable(True)
            self.submit_btn.Enable(True)
            self.code_input.SetFocus()

        except Exception as e:
            logger.error(f"Error starting login: {e}")
            speaker.speak("Error starting login")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)

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
            self.status_text.AppendText("\nExchanging code for access token...\n")
            wx.SafeYield()

            # Disable input during exchange
            self.code_input.Enable(False)
            self.submit_btn.Enable(False)

            # Exchange code for token
            success = self.auth.exchange_code_for_token(auth_code)

            if success:
                self.authenticated = True
                speaker.speak(f"Successfully logged in as {self.auth.display_name}")
                self.status_text.AppendText(f"\n✓ Successfully authenticated as {self.auth.display_name}!\n")
                wx.CallLater(1000, lambda: self.EndModal(wx.ID_OK))
            else:
                speaker.speak("Authentication failed")
                self.status_text.AppendText("\n✗ Authentication failed. Please check your code and try again.\n")
                messageBox(
                    "Failed to authenticate with the provided code. The code may be invalid or expired.\n\n"
                    "Please click 'Start Login' again to get a new code.",
                    "Authentication Failed",
                    wx.OK | wx.ICON_ERROR,
                    self
                )
                # Re-enable login button so user can try again
                self.login_btn.Enable(True)
                self.code_input.Enable(False)
                self.submit_btn.Enable(False)
                self.code_input.Clear()

        except Exception as e:
            logger.error(f"Error submitting code: {e}")
            speaker.speak("Error submitting code")
            self.status_text.AppendText(f"\n✗ Error: {e}\n")
            messageBox(f"Error: {e}", "Error", wx.OK | wx.ICON_ERROR, self)
            # Re-enable controls for retry
            self.code_input.Enable(True)
            self.submit_btn.Enable(True)
>>>>>>> 7c21c23a460e8f25bc96524c200b22c8b26c9b15
