"""
Epic Browser Login Dialog for FA11y
Uses embedded WebView to capture Epic Games authentication
"""
import wx
import wx.html2
import logging
import json
import time
import threading
import urllib.parse
from typing import Optional, Dict, Callable
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Epic Games URLs
EPIC_LOGIN_URL = "https://www.epicgames.com/id/login"
EPIC_ACCOUNT_URL = "https://www.epicgames.com/account/personal"
EPIC_REDIRECT_URL = "https://www.epicgames.com/id/api/redirect"


class SilentAuthDialog(wx.Dialog):
    """
    Minimized dialog for silent authentication attempts.
    Uses wx WebView to check if user has valid session cookies.
    """

    def __init__(self, auth_instance, timeout: float = 10.0):
        """
        Initialize minimized auth dialog.

        Args:
            auth_instance: EpicAuth instance to update
            timeout: Maximum time to wait for auth code
        """
        super().__init__(
            None,
            title="Authenticating...",
            size=(800, 600),  # Normal size for proper WebView initialization
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self.auth_instance = auth_instance
        self.timeout = timeout
        self.auth_successful = False
        self.start_time = time.time()

        # Create panel and sizer for WebView
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Create WebView
        try:
            self.browser = wx.html2.WebView.New(panel)
            self.browser.Bind(wx.html2.EVT_WEBVIEW_NAVIGATED, self._on_navigated)
            self.browser.Bind(wx.html2.EVT_WEBVIEW_LOADED, self._on_page_loaded)
            self.browser.Bind(wx.html2.EVT_WEBVIEW_ERROR, self._on_error)
            self.browser.Bind(wx.html2.EVT_WEBVIEW_NEWWINDOW, self._on_new_window)
            sizer.Add(self.browser, 1, wx.EXPAND)
        except Exception as e:
            logger.error(f"Failed to create WebView for silent auth: {e}")
            self.browser = None

        panel.SetSizer(sizer)

        # Iconify (minimize) the window
        self.Iconize(True)

        # Start authentication attempt
        wx.CallAfter(self._start_silent_auth)

    def _start_silent_auth(self):
        """Start the silent authentication attempt"""
        if not self.browser:
            logger.error("No browser available for silent auth")
            wx.CallAfter(lambda: self.EndModal(wx.ID_CANCEL))
            return

        # Navigate to Epic's redirect URL
        redirect_url = f"https://www.epicgames.com/id/api/redirect?clientId={self.auth_instance.CLIENT_ID}&responseType=code"
        logger.debug(f"Starting silent auth to: {redirect_url}")
        self.browser.LoadURL(redirect_url)

        # Set up timeout
        wx.CallLater(int(self.timeout * 1000), self._check_timeout)

    def _on_navigated(self, event):
        """Handle navigation events"""
        url = event.GetURL()
        logger.debug(f"Silent auth navigated to: {url[:100]}")

    def _on_page_loaded(self, event):
        """Handle page load completion - check page source for JSON response"""
        url = event.GetURL()
        logger.debug(f"Silent auth page loaded: {url[:100]}")

        # Auth code is NEVER in the URL - it's always in the page content as JSON
        # Check page source for JSON response with redirectUrl containing the code
        wx.CallAfter(self._check_page_source)

    def _check_page_source(self):
        """Check page source for auth code in JSON response"""
        if self.auth_successful or not self.browser:
            return

        try:
            page_source = self.browser.GetPageSource()
            if not page_source or 'redirectUrl' not in page_source:
                return

            logger.debug("Silent auth: Found redirectUrl in page source")

            # Try to parse JSON response
            import json
            import re

            # Try to extract JSON from page
            json_match = re.search(r'\{[^}]*"redirectUrl"[^}]+\}', page_source)
            if json_match:
                try:
                    json_data = json.loads(json_match.group(0))
                    redirect_url_value = json_data.get('redirectUrl', '')

                    if redirect_url_value and 'code=' in redirect_url_value:
                        logger.debug(f"Silent auth: Extracted redirectUrl from JSON: {redirect_url_value[:100]}")
                        self._extract_and_complete(redirect_url_value)
                        return
                except json.JSONDecodeError:
                    pass

            # Fallback: regex extraction
            match = re.search(r'"redirectUrl"\s*:\s*"([^"]+)"', page_source)
            if match:
                redirect_url_value = match.group(1)
                redirect_url_value = redirect_url_value.replace('\\u0026', '&').replace('\\/', '/')

                if 'code=' in redirect_url_value:
                    logger.debug(f"Silent auth: Extracted redirectUrl from regex: {redirect_url_value[:100]}")
                    self._extract_and_complete(redirect_url_value)

        except Exception as e:
            logger.debug(f"Silent auth: Error checking page source: {e}")

    def _extract_and_complete(self, url: str):
        """Extract auth code and complete authentication"""
        if self.auth_successful:
            return  # Already processed

        try:
            # Parse authorization code from URL
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            auth_code = params.get('code', [None])[0]

            if not auth_code:
                # No code in this URL, keep waiting for redirect
                logger.debug("Silent auth: No code in this URL yet, waiting for redirect...")
                return

            logger.debug(f"Silent auth: Extracted code: {auth_code[:20]}...")

            # Exchange code for token
            if self.auth_instance.exchange_code_for_token(auth_code):
                if self.auth_instance.is_valid and self.auth_instance.access_token:
                    logger.info(f"Silent auth successful for {self.auth_instance.display_name}")
                    self.auth_successful = True
                    wx.CallAfter(lambda: self.EndModal(wx.ID_OK))
                    return
                else:
                    logger.warning("Silent auth: Token exchange succeeded but auth not valid")
            else:
                logger.warning("Silent auth: Failed to exchange auth code")

            # Don't close on failure - let timeout handle it
            # The code might be expired, but we'll let the timeout close the dialog

        except Exception as e:
            logger.error(f"Silent auth error: {e}")
            # Don't close on exception - let timeout handle it

    def _on_new_window(self, event):
        """
        Handle new window requests (e.g., Google/Facebook login).
        Navigate in the same window instead of opening new window.
        """
        url = event.GetURL()
        logger.debug(f"Silent auth: New window requested for: {url}")
        if self.browser:
            self.browser.LoadURL(url)

    def _on_error(self, event):
        """Handle WebView errors - ignore CONNECTION_ABORTED"""
        error_msg = event.GetString()
        if "CONNECTION_ABORTED" in error_msg:
            logger.debug("Silent auth: Connection aborted (normal redirect)")
            return
        logger.debug(f"Silent auth error: {error_msg}")

    def _check_timeout(self):
        """Check if authentication has timed out"""
        if not self.auth_successful:
            elapsed = time.time() - self.start_time
            logger.debug(f"Silent auth timed out after {elapsed:.1f}s")
            self.EndModal(wx.ID_CANCEL)

    def was_successful(self) -> bool:
        """Check if authentication was successful"""
        return self.auth_successful


def silent_webview_auth(auth_instance, timeout: float = 10.0) -> bool:
    """
    Attempt authentication using a hidden WebView window.
    If wx has valid cookies, this will succeed silently.

    Args:
        auth_instance: EpicAuth instance to update
        timeout: Max time to wait for auth

    Returns:
        True if authentication succeeded
    """
    try:
        logger.debug("Creating silent auth dialog")
        dialog = SilentAuthDialog(auth_instance, timeout)
        result = dialog.ShowModal()
        success = dialog.was_successful()
        dialog.Destroy()

        logger.debug(f"Silent auth result: {success}")
        return success

    except Exception as e:
        logger.error(f"Error in silent WebView auth: {e}")
        return False


class EpicBrowserLoginDialog(wx.Dialog):
    """
    Dialog with embedded browser for Epic Games login.
    Uses wx WebView's native cookie management.
    """

    def __init__(self, parent, auth_instance):
        """
        Initialize the browser login dialog.

        Args:
            parent: Parent window
            auth_instance: EpicAuth instance to update
        """
        super().__init__(
            parent,
            title="Epic Games Browser Login",
            size=(900, 700),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self.auth_instance = auth_instance
        self.login_successful = False
        self._login_detected = False
        self._auto_completing = False

        self._setup_ui()
        self._bind_events()

        # Center on screen
        self.CentreOnScreen()

        # Start login flow
        wx.CallAfter(self._start_login)

    def _setup_ui(self):
        """Setup the dialog UI with WebView"""
        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        # Instructions
        instructions = wx.StaticText(
            panel,
            label="Please log in to your Epic Games account. After logging in, click 'I'm Logged In' to complete."
        )
        instructions.Wrap(850)
        sizer.Add(instructions, 0, wx.ALL | wx.EXPAND, 10)

        # Create WebView
        try:
            self.browser = wx.html2.WebView.New(panel)
            sizer.Add(self.browser, 1, wx.EXPAND | wx.ALL, 5)
        except Exception as e:
            logger.error(f"Failed to create WebView: {e}")
            error_text = wx.StaticText(
                panel,
                label=f"Error: Could not create browser window.\n{e}\n\nPlease use the manual login method instead."
            )
            sizer.Add(error_text, 1, wx.ALL | wx.EXPAND, 10)
            self.browser = None

        # Status text
        self.status_label = wx.StaticText(panel, label="Status: Waiting for login...")
        sizer.Add(self.status_label, 0, wx.ALL | wx.EXPAND, 5)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.refresh_btn = wx.Button(panel, label="&Refresh")
        self.logged_in_btn = wx.Button(panel, label="&I'm Logged In")
        self.cancel_btn = wx.Button(panel, wx.ID_CANCEL, label="&Cancel")

        btn_sizer.Add(self.refresh_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.logged_in_btn, 0, wx.ALL, 5)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(self.cancel_btn, 0, wx.ALL, 5)

        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)

        panel.SetSizer(sizer)

    def _bind_events(self):
        """Bind event handlers"""
        if self.browser:
            self.browser.Bind(wx.html2.EVT_WEBVIEW_NAVIGATING, self._on_navigating)
            self.browser.Bind(wx.html2.EVT_WEBVIEW_NAVIGATED, self._on_navigated)
            self.browser.Bind(wx.html2.EVT_WEBVIEW_LOADED, self._on_page_loaded)
            self.browser.Bind(wx.html2.EVT_WEBVIEW_ERROR, self._on_error)
            self.browser.Bind(wx.html2.EVT_WEBVIEW_NEWWINDOW, self._on_new_window)

        self.refresh_btn.Bind(wx.EVT_BUTTON, self._on_refresh)
        self.logged_in_btn.Bind(wx.EVT_BUTTON, self._on_logged_in_clicked)
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel)
        self.Bind(wx.EVT_CLOSE, self._on_close)

    def _start_login(self):
        """Start the login flow by navigating to Epic login page"""
        if self.browser:
            logger.debug("Starting Epic Games browser login")
            self.browser.LoadURL(EPIC_LOGIN_URL)

    def _on_new_window(self, event):
        """
        Handle new window requests (e.g., Google/Facebook login buttons).
        Instead of opening a new window, navigate the current browser to that URL.
        """
        url = event.GetURL()
        logger.debug(f"New window requested for: {url}")

        # Navigate to the URL in the same browser window
        if self.browser:
            self.browser.LoadURL(url)
            self._update_status(f"Redirecting to external login...")

    def _on_navigating(self, event):
        """Handle navigation start"""
        url = event.GetURL()
        logger.debug(f"Navigating to: {url}")

    def _on_navigated(self, event):
        """Handle navigation events"""
        url = event.GetURL()
        logger.debug(f"Browser navigated to: {url}")

        # Check if URL contains authorization code
        if 'code=' in url:
            logger.debug(f"Auth code detected in URL: {url[:100]}")
            wx.CallAfter(self._extract_and_use_auth_code, url)
            return

        # Update status based on URL
        if "google.com" in url.lower():
            self._update_status("Logging in with Google...")
        elif "facebook.com" in url.lower():
            self._update_status("Logging in with Facebook...")
        elif "apple.com" in url.lower():
            self._update_status("Logging in with Apple...")
        elif "epicgames.com/id/login" in url.lower():
            self._update_status("On Epic Games login page...")
        elif self._is_logged_in_url(url):
            self._login_detected = True
            self._update_status("Login detected! Verifying authentication...")
            # Auto-complete - don't require user to click button
            wx.CallAfter(self._auto_complete_login)

    def _on_page_loaded(self, event):
        """Handle page load completion"""
        url = event.GetURL()
        logger.debug(f"Page loaded: {url}")

        # Check if URL contains authorization code
        if 'code=' in url:
            logger.debug(f"Auth code detected in loaded page URL: {url[:100]}")
            wx.CallAfter(self._extract_and_use_auth_code, url)
            return

        # Check if we've reached a page that indicates successful login
        if self._is_logged_in_url(url):
            self._login_detected = True
            self._update_status("Login detected! Verifying authentication...")
            # Auto-complete - don't require user to click button
            wx.CallAfter(self._auto_complete_login)

    def _is_logged_in_url(self, url: str) -> bool:
        """Check if URL indicates user is logged in"""
        logged_in_indicators = [
            "epicgames.com/account",
            "epicgames.com/store",
            "epicgames.com/id/logout",  # Logout link means we're logged in
            "fortnite.com",
            "store.epicgames.com",
            "launcher.store.epicgames.com",
        ]
        url_lower = url.lower()
        # Don't trigger on login page
        if "epicgames.com/id/login" in url_lower:
            return False
        return any(indicator in url_lower for indicator in logged_in_indicators)

    def _update_status(self, message: str):
        """Update the status label"""
        if hasattr(self, 'status_label'):
            self.status_label.SetLabel(f"Status: {message}")

    def _extract_and_use_auth_code(self, url: str):
        """
        Extract authorization code from URL and use it to authenticate.
        This is the primary authentication method when browser navigates to a URL with code.
        """
        # Prevent multiple auth attempts
        if self.login_successful or self._auto_completing:
            return
        self._auto_completing = True

        try:
            self._update_status("Authorization code detected! Exchanging for token...")
            wx.SafeYield()

            # Parse the authorization code from URL
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            auth_code = params.get('code', [None])[0]

            if not auth_code:
                logger.error(f"Could not parse auth code from URL: {url[:200]}")
                self._auto_completing = False
                return

            logger.debug(f"Extracted auth code: {auth_code[:20]}...")

            # Exchange code for token using the auth instance
            if self.auth_instance.exchange_code_for_token(auth_code):
                # Verify token was actually obtained
                if self.auth_instance.is_valid and self.auth_instance.access_token:
                    logger.info(f"Successfully authenticated as {self.auth_instance.display_name}")
                    self.login_successful = True
                    self._update_status(f"✓ Successfully authenticated as {self.auth_instance.display_name}!")
                    wx.CallLater(500, lambda: self.EndModal(wx.ID_OK))
                else:
                    logger.error("Token exchange succeeded but auth is not valid")
                    self._auto_completing = False
                    self._update_status("Token exchange succeeded but authentication not confirmed. Please try again.")
            else:
                logger.error("Failed to exchange auth code for token")
                self._auto_completing = False
                self._update_status("Failed to exchange authorization code. Please try again.")

        except Exception as e:
            logger.error(f"Error extracting/using auth code: {e}")
            self._auto_completing = False
            self._update_status(f"Error during authentication: {e}")

    def _auto_complete_login(self):
        """
        Automatically try to complete login when detected.
        Called when we detect the user is on a logged-in page.
        """
        # Prevent multiple auto-complete attempts
        if self.login_successful or self._auto_completing:
            return
        self._auto_completing = True

        self._update_status("Verifying authentication...")
        wx.SafeYield()

        # Try to get auth code
        success = self._try_get_auth_code()

        if success:
            self.login_successful = True
            self._update_status("Authentication successful!")
            wx.CallLater(500, lambda: self.EndModal(wx.ID_OK))
        else:
            # Auto-complete failed, let user try manual button
            self._auto_completing = False
            self._update_status("Auto-verification failed. Click 'I'm Logged In' to try again.")

    def _on_logged_in_clicked(self, event):
        """
        Handle the 'I'm Logged In' button click.
        Try to authenticate using the redirect API.
        """
        self._update_status("Verifying login and getting authentication...")
        wx.SafeYield()

        # Try to get auth code using the redirect API
        success = self._try_get_auth_code()

        if success:
            self.login_successful = True
            self._update_status("Authentication successful!")
            wx.CallLater(500, lambda: self.EndModal(wx.ID_OK))
        else:
            # Show error and let user retry
            wx.MessageBox(
                "Could not verify login. Please make sure you are fully logged in to Epic Games, "
                "then try clicking 'I'm Logged In' again.\n\n"
                "Tip: Try navigating to epicgames.com/account first to ensure you're logged in.",
                "Verification Failed",
                wx.OK | wx.ICON_WARNING
            )
            self._update_status("Verification failed. Please try again.")

    def _try_get_auth_code(self) -> bool:
        """
        Try to get an authentication code using the redirect API.
        This uses the WebView's session cookies.

        Returns:
            True if authentication was successful and token was obtained
        """
        try:
            # Primary method: Navigate to redirect URL and capture auth code from URL
            logger.debug("Attempting to get auth code via redirect URL navigation")
            if self._try_redirect_in_browser():
                # Verify token was actually obtained
                if self.auth_instance.is_valid and self.auth_instance.access_token:
                    logger.info("Successfully obtained and verified token via redirect")
                    return True
                else:
                    logger.warning("Redirect method completed but token not valid")

            logger.error("Authentication failed")
            return False

        except Exception as e:
            logger.error(f"Error getting auth code: {e}")
            return False

    def _try_redirect_in_browser(self) -> bool:
        """
        Navigate to the redirect URL and try to capture the auth code.
        This method will trigger URL navigation which will be caught by _extract_and_use_auth_code.
        """
        if not self.browser:
            logger.error("Browser not available for redirect method")
            return False

        try:
            # Navigate to redirect URL - this will trigger navigation events
            redirect_url = f"https://www.epicgames.com/id/api/redirect?clientId={self.auth_instance.CLIENT_ID}&responseType=code"
            
            logger.debug(f"Navigating to redirect URL: {redirect_url}")
            self.browser.LoadURL(redirect_url)

            # Wait for navigation and potential auth code capture
            # The _on_navigated and _on_page_loaded handlers will catch the auth code
            for i in range(50):  # Wait up to 5 seconds
                wx.SafeYield()
                time.sleep(0.1)

                current_url = self.browser.GetCurrentURL()

                # Check if we got redirected to a URL with an auth code
                if 'code=' in current_url and current_url != redirect_url:
                    logger.debug(f"Auth code detected in redirect URL (attempt {i+1})")
                    parsed = urllib.parse.urlparse(current_url)
                    params = urllib.parse.parse_qs(parsed.query)
                    auth_code = params.get('code', [None])[0]

                    if auth_code:
                        logger.debug(f"Extracted auth code from redirect: {auth_code[:20]}...")
                        if self.auth_instance.exchange_code_for_token(auth_code):
                            logger.info("Successfully exchanged auth code from redirect")
                            return True
                        else:
                            logger.error("Failed to exchange auth code from redirect")
                            return False

                # Check if the page content contains the redirect URL with code
                try:
                    page_source = self.browser.GetPageSource()
                    if page_source and 'redirectUrl' in page_source:
                        # Try to parse JSON response
                        import json
                        import re
                        
                        # Try to extract JSON from page
                        json_match = re.search(r'\{[^}]*"redirectUrl"[^}]+\}', page_source)
                        if json_match:
                            try:
                                json_data = json.loads(json_match.group(0))
                                redirect_url_value = json_data.get('redirectUrl', '')
                                
                                if redirect_url_value and 'code=' in redirect_url_value:
                                    parsed = urllib.parse.urlparse(redirect_url_value)
                                    params = urllib.parse.parse_qs(parsed.query)
                                    auth_code = params.get('code', [None])[0]

                                    if auth_code:
                                        logger.debug(f"Extracted auth code from JSON response: {auth_code[:20]}...")
                                        if self.auth_instance.exchange_code_for_token(auth_code):
                                            logger.info("Successfully exchanged auth code from JSON")
                                            return True
                                        else:
                                            logger.error("Failed to exchange auth code from JSON")
                                            return False
                            except json.JSONDecodeError:
                                pass
                        
                        # Fallback: regex extraction
                        match = re.search(r'"redirectUrl"\s*:\s*"([^"]+)"', page_source)
                        if match:
                            redirect_url_value = match.group(1)
                            # Unescape the URL
                            redirect_url_value = redirect_url_value.replace('\\u0026', '&').replace('\\/', '/')

                            if 'code=' in redirect_url_value:
                                parsed = urllib.parse.urlparse(redirect_url_value)
                                params = urllib.parse.parse_qs(parsed.query)
                                auth_code = params.get('code', [None])[0]

                                if auth_code:
                                    logger.debug(f"Extracted auth code from regex match: {auth_code[:20]}...")
                                    if self.auth_instance.exchange_code_for_token(auth_code):
                                        logger.info("Successfully exchanged auth code from regex")
                                        return True
                                    else:
                                        logger.error("Failed to exchange auth code from regex")
                                        return False
                except Exception as e:
                    logger.debug(f"Error parsing page source (attempt {i+1}): {e}")

            logger.warning("Redirect method timed out waiting for auth code")
            return False

        except Exception as e:
            logger.error(f"Error in redirect method: {e}")
            return False

    def _on_error(self, event):
        """Handle WebView errors"""
        error_msg = event.GetString()
        
        # Ignore CONNECTION_ABORTED - this is normal for redirects
        if "CONNECTION_ABORTED" in error_msg:
            logger.debug("WebView connection aborted (normal redirect behavior)")
            return
        
        # Log other errors
        logger.error(f"WebView error: {error_msg}")
        self._update_status(f"Error: {error_msg[:50]}...")

    def _on_refresh(self, event):
        """Handle refresh button"""
        if self.browser:
            self.browser.Reload()
            self._update_status("Refreshing...")

    def _on_cancel(self, event):
        """Handle cancel button"""
        self.EndModal(wx.ID_CANCEL)

    def _on_close(self, event):
        """Handle dialog close"""
        if self._check_timer:
            self._check_timer.Stop()
        event.Skip()

    def was_login_successful(self) -> bool:
        """Check if login was successful"""
        return self.login_successful


def show_browser_login(parent=None, auth_instance=None) -> bool:
    """
    Show the browser login dialog.

    Args:
        parent: Parent window
        auth_instance: EpicAuth instance to update

    Returns:
        True if login was successful
    """
    if not auth_instance:
        logger.error("auth_instance is required for browser login")
        return False

    try:
        dialog = EpicBrowserLoginDialog(parent, auth_instance=auth_instance)
        result = dialog.ShowModal()
        success = result == wx.ID_OK and dialog.was_login_successful()
        dialog.Destroy()
        return success

    except Exception as e:
        logger.error(f"Error showing browser login: {e}")
        return False
