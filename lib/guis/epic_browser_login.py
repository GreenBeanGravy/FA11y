"""
Epic Browser Login Dialog for FA11y
Uses embedded WebView to capture Epic Games authentication
"""
import wx
import wx.html2
from lib.hub.controls import StyledButton
import logging
import time
import urllib.parse

from lib.utilities.epic_redirect import (
    FNAUTH_URL, code_from_auth_url, is_fnauth_page, is_login_page, is_redirect_endpoint,
    parse_redirect_response, safe_url,
)

logger = logging.getLogger(__name__)

# Epic Games URLs
EPIC_LOGIN_URL = "https://www.epicgames.com/id/login"
EPIC_ACCOUNT_URL = "https://www.epicgames.com/account/personal"
EPIC_REDIRECT_URL = "https://www.epicgames.com/id/api/redirect"

# How long to wait for Epic's reply after asking for a code, and how long to wait for the page to report that it
# has loaded before reading it anyway.
REDIRECT_WAIT_SECONDS = 8.0
REDIRECT_LOADED_GRACE = 4.0
# Epic's pages can look signed in before the sign in is done, so only this many automatic tries are made.
MAX_AUTO_ATTEMPTS = 2


def _read_page(browser):
    """The page as text and as source; an empty string for whichever the web view can't give."""
    pages = []
    for read in (browser.GetPageText, browser.GetPageSource):
        try:
            pages.append(read() or "")
        except Exception as e:
            logger.debug(f"Could not read the page: {e}")
            pages.append("")
    return tuple(pages)


class SilentAuthDialog(wx.Frame):
    """
    Off-screen window for silent authentication attempts. It never takes
    focus or shows in the taskbar, and it doesn't block: ``on_done(success)``
    is called on the wx thread when it finishes.
    Uses wx WebView to check if user has valid session cookies.
    """

    def __init__(self, auth_instance, timeout: float, on_done):
        # WebView needs a real, shown window to navigate, so it is shown far
        # off screen without being activated.
        super().__init__(
            None,
            title="Authenticating...",
            pos=(-32000, -32000),
            size=(800, 600),
            style=wx.FRAME_NO_TASKBAR | wx.FRAME_TOOL_WINDOW | wx.BORDER_NONE
        )

        self.auth_instance = auth_instance
        self.timeout = timeout
        self.auth_successful = False
        self.start_time = time.time()
        self._on_done = on_done
        self._finished = False
        self._timer = None
        self._redirect_requested = False
        self._followed = set()

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

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
        wx.CallAfter(self._start_silent_auth)

    def _finish(self, success: bool) -> None:
        """Report the result once and close the window."""
        if self._finished:
            return
        self._finished = True
        if self._timer is not None:
            self._timer.Stop()
        logger.debug(f"Silent auth result: {success}")
        try:
            self.Destroy()
        except Exception:
            pass
        try:
            self._on_done(success)
        except Exception:
            logger.exception("Silent auth callback failed")

    def _start_silent_auth(self):
        """Start the silent authentication attempt"""
        if not self.browser:
            logger.error("No browser available for silent auth")
            self._finish(False)
            return

        redirect_url = f"https://www.epicgames.com/id/api/redirect?clientId={self.auth_instance.CLIENT_ID}&responseType=code"
        logger.debug(f"Starting silent auth to: {redirect_url}")
        self.browser.LoadURL(EPIC_LOGIN_URL)
        self._timer = wx.CallLater(int(self.timeout * 1000), self._check_timeout)

    def was_successful(self) -> bool:
        """Check if authentication was successful"""
        return self.auth_successful

    def _on_navigated(self, event):
        self._handle_navigation(event.GetURL())

    def _on_page_loaded(self, event):
        self._handle_navigation(event.GetURL())
        wx.CallAfter(self._check_page_source)

    def _handle_navigation(self, url):
        if self._finished or self.auth_successful:
            return
        logger.debug(f"Silent auth page: {safe_url(url)}")
        # Only the Fortnite redirect carries the authorization code for our client.
        code = code_from_auth_url(url)
        if code:
            self._complete_with_code(code)
            return
        if not self._redirect_requested and (
            "epicgames.com/account" in url or "store.epicgames.com" in url or is_fnauth_page(url)
        ):
            self._redirect_requested = True
            self.browser.LoadURL(self.auth_instance.get_authorization_url())

    def _check_page_source(self):
        """Look for Epic's reply, with the authorization code, in the page"""
        if self.auth_successful or not self.browser:
            return

        try:
            reply = parse_redirect_response(*_read_page(self.browser))
            if reply is None:
                return

            if reply.code:
                logger.debug("Silent auth: Epic's reply has a sign-in code")
                self._complete_with_code(reply.code)
                return

            # An intermediate redirect may still reuse the saved browser session.
            # Keep navigating until the authorization response or the timeout.
            destination = reply.destination or ''
            parsed = urllib.parse.urlparse(destination)
            if (parsed.scheme == 'https' and parsed.hostname
                    and (parsed.hostname == 'epicgames.com' or parsed.hostname.endswith('.epicgames.com'))
                    and destination not in self._followed):
                self._followed.add(destination)
                self.browser.LoadURL(destination)

        except Exception as e:
            logger.debug(f"Silent auth: Error checking page source: {e}")

    def _complete_with_code(self, auth_code: str):
        """Exchange the authorization code and complete authentication"""
        if self.auth_successful:
            return  # Already processed

        try:
            logger.debug("Silent auth: exchanging the sign-in code")

            # Exchange code for token
            if self.auth_instance.exchange_code_for_token(auth_code):
                if self.auth_instance.is_valid and self.auth_instance.access_token:
                    logger.info(f"Silent auth successful for {self.auth_instance.display_name}")
                    self.auth_successful = True
                    wx.CallAfter(self._finish, True)
                    return
                else:
                    logger.warning("Silent auth: Token exchange succeeded but auth not valid")
            else:
                logger.warning(f"Silent auth: Epic refused the sign-in code ({self.auth_instance.last_error or 'no reason given'})")

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
        logger.debug(f"Silent auth: new window for {safe_url(url)}")
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
            self._finish(False)


def silent_webview_auth(auth_instance, on_done, timeout: float = 10.0) -> None:
    """
    Try to sign in from the WebView's saved Epic cookies, without any visible
    window. Returns at once; ``on_done(success)`` runs on the wx thread.
    """
    try:
        logger.debug("Creating silent auth window")
        frame = SilentAuthDialog(auth_instance, timeout, on_done)
        frame.ShowWithoutActivating()
    except Exception as e:
        logger.error(f"Error in silent WebView auth: {e}")
        on_done(False)


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
        self._auto_attempts = 0
        self._auto_hold = False
        self._redirect_loaded = False
        self._failure_kind = ""
        self._failure_detail = ""

        self._setup_ui()
        self._bind_events()

        # Center on screen
        self.CentreOnScreen()

        # Start login flow
        wx.CallAfter(self._start_login)

    def _safe_end_modal(self, code: int) -> None:
        """End the modal loop iff one is still running (race-safe)."""
        try:
            if self.IsBeingDeleted():
                return
            if not self.IsModal():
                return
            self.EndModal(code)
        except Exception as e:
            logger.debug(f"EndModal skipped: {e}")

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

        self.refresh_btn = StyledButton(panel, label="&Refresh")
        self.logged_in_btn = StyledButton(panel, label="&I'm Logged In")
        self.cancel_btn = StyledButton(panel, wx.ID_CANCEL, label="&Cancel")

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
            # Epic only answers the redirect with a code when the browser is signed in on Fortnite's own sign in
            # page as well, which www.epicgames.com/id/login does not do. Signing in here covers both.
            self.browser.LoadURL(FNAUTH_URL)

    def _on_new_window(self, event):
        """
        Handle new window requests (e.g., Google/Facebook login buttons).
        Instead of opening a new window, navigate the current browser to that URL.
        """
        url = event.GetURL()
        logger.debug(f"Epic login new window: {safe_url(url)}")

        # Navigate to the URL in the same browser window
        if self.browser:
            self.browser.LoadURL(url)
            self._update_status(f"Redirecting to external login...")

    def _on_navigating(self, event):
        """Handle navigation start"""
        logger.debug(f"Epic login navigating: {safe_url(event.GetURL())}")

    def _on_navigated(self, event):
        """Handle navigation events"""
        url = event.GetURL()
        logger.debug(f"Epic login navigated: {safe_url(url)}")

        # Only Fortnite's own redirect carries the authorization code; Google's and Facebook's come back with
        # a code of their own that Epic would refuse.
        if code_from_auth_url(url):
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
        logger.debug(f"Epic login page loaded: {safe_url(url)}")

        if is_redirect_endpoint(url):
            self._redirect_loaded = True

        # Back on a sign in page: whatever signed-in page comes next is a real sign in.
        if is_login_page(url):
            self._auto_hold = False
            self._auto_attempts = 0

        if code_from_auth_url(url):
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
        if is_fnauth_page(url):
            return True
        url_lower = url.lower()
        # Don't trigger on login page
        if "epicgames.com/id/login" in url_lower:
            return False
        return any(indicator in url_lower for indicator in logged_in_indicators)

    def _update_status(self, message: str):
        """Update the status label"""
        if hasattr(self, 'status_label'):
            self.status_label.SetLabel(f"Status: {message}")

    def _begin_attempt(self) -> bool:
        """Claim the sign in, so only one attempt runs at a time and a code is never used twice."""
        if self.login_successful or self._auto_completing:
            return False
        self._auto_completing = True
        self._failure_kind = ""
        self._failure_detail = ""
        return True

    def _exchange(self, code: str) -> bool:
        """Trade an authorization code for a token; when that fails, ``_failure_kind`` says why."""
        if not self.auth_instance.exchange_code_for_token(code):
            self._failure_kind = "refused"
            self._failure_detail = getattr(self.auth_instance, "last_error", "") or ""
            logger.error(f"Epic refused the sign-in code: {self._failure_detail or 'no reason given'}")
            return False
        if not (self.auth_instance.is_valid and self.auth_instance.access_token):
            self._failure_kind = "refused"
            self._failure_detail = "token not confirmed"
            logger.error("Token exchange succeeded but auth is not valid")
            return False
        return True

    def _failure_message(self) -> str:
        """What to tell the person about the attempt that just failed."""
        if self._failure_kind == "not_signed_in":
            return "Epic says you are not signed in yet. Sign in on the page, then choose I'm Logged In."
        if self._failure_kind == "refused":
            detail = f" ({self._failure_detail})" if self._failure_detail else ""
            return f"Epic did not accept the sign-in code{detail}. Choose I'm Logged In to try again."
        return ("FA11y could not read Epic's answer. Choose I'm Logged In to try again, "
                "or use the Manual Code tab in the sign-in window.")

    def _return_to_login_if_needed(self):
        """When Epic says nobody is signed in, bring the sign in page back so the person isn't left on Epic's reply."""
        if self._failure_kind == "not_signed_in" and self.browser:
            # Loading it must not start another automatic try before the person has signed in again.
            self._auto_hold = True
            self.browser.LoadURL(FNAUTH_URL)

    def _extract_and_use_auth_code(self, url: str):
        """
        Use the authorization code in Fortnite's redirect URL.
        This is the primary authentication method when browser navigates to a URL with code.
        """
        auth_code = code_from_auth_url(url)
        if not auth_code or not self._begin_attempt():
            return

        try:
            self._update_status("Authorization code detected! Exchanging for token...")
            wx.SafeYield()

            if self._exchange(auth_code):
                logger.info(f"Successfully authenticated as {self.auth_instance.display_name}")
                self.login_successful = True
                self._update_status(f"✓ Successfully authenticated as {self.auth_instance.display_name}!")
                wx.CallLater(500, self._safe_end_modal, wx.ID_OK)
            else:
                self._update_status(self._failure_message())

        except Exception as e:
            logger.error(f"Error extracting/using auth code: {e}")
            self._update_status(f"Error during authentication: {e}")
        finally:
            self._auto_completing = False

    def _auto_complete_login(self):
        """
        Automatically try to complete login when detected.
        Called when we detect the user is on a logged-in page.
        """
        if self._auto_hold or self._auto_attempts >= MAX_AUTO_ATTEMPTS or not self._begin_attempt():
            return
        self._auto_attempts += 1

        try:
            self._update_status("Verifying authentication...")
            wx.SafeYield()
            success = self._try_get_auth_code()
        finally:
            self._auto_completing = False

        if success:
            self.login_successful = True
            self._update_status("Authentication successful!")
            wx.CallLater(500, self._safe_end_modal, wx.ID_OK)
        else:
            # Auto-complete failed, let user try manual button
            self._update_status(self._failure_message())
            self._return_to_login_if_needed()

    def _on_logged_in_clicked(self, event):
        """
        Handle the 'I'm Logged In' button click.
        Try to authenticate using the redirect API.
        """
        if not self._begin_attempt():
            if not self.login_successful:
                self._update_status("Still verifying your login...")
            return

        try:
            self._update_status("Verifying login and getting authentication...")
            wx.SafeYield()
            success = self._try_get_auth_code()
        finally:
            self._auto_completing = False

        if success:
            self.login_successful = True
            self._update_status("Authentication successful!")
            wx.CallLater(500, self._safe_end_modal, wx.ID_OK)
            return

        message = self._failure_message()
        self._return_to_login_if_needed()
        self._update_status(message)
        wx.MessageBox(message, "Verification Failed", wx.OK | wx.ICON_WARNING)

    def _try_get_auth_code(self) -> bool:
        """
        Try to get an authentication code using the redirect API.
        This uses the WebView's session cookies.

        Returns:
            True if authentication was successful and token was obtained
        """
        try:
            logger.debug("Attempting to get auth code via redirect URL navigation")
            if self._try_redirect_in_browser():
                logger.info("Successfully obtained and verified token via redirect")
                return True

            logger.error(f"Authentication failed ({self._failure_kind or 'unknown'})")
            return False

        except Exception as e:
            logger.error(f"Error getting auth code: {e}")
            self._failure_kind = self._failure_kind or "unreadable"
            return False

    def _try_redirect_in_browser(self) -> bool:
        """
        Ask Epic's redirect page for an authorization code with the browser's session, then use it.
        The code arrives in the page's JSON reply, or in Fortnite's redirect if Epic sends the browser on.
        """
        self._failure_kind = "unreadable"
        if not self.browser:
            logger.error("Browser not available for redirect method")
            return False

        redirect_url = self.auth_instance.get_authorization_url()
        logger.debug(f"Navigating to redirect URL: {safe_url(redirect_url)}")
        self._redirect_loaded = False
        self.browser.LoadURL(redirect_url)

        started = time.monotonic()
        while time.monotonic() - started < REDIRECT_WAIT_SECONDS:
            wx.SafeYield()
            time.sleep(0.1)
            if self.login_successful:
                return True

            current_url = self.browser.GetCurrentURL()
            code = code_from_auth_url(current_url)
            if code:
                logger.debug("Auth code detected in Fortnite's redirect")
                return self._exchange(code)

            # The page is Epic's reply only once it has loaded. Until then it is the page we came from, which
            # can hold old or unrelated JSON.
            waited = time.monotonic() - started
            if not is_redirect_endpoint(current_url) or not (self._redirect_loaded or waited > REDIRECT_LOADED_GRACE):
                continue
            reply = parse_redirect_response(*_read_page(self.browser))
            if reply is None:
                continue
            if reply.code:
                logger.debug("Auth code found in Epic's reply")
                return self._exchange(reply.code)

            logger.debug("Epic's reply has no code: the browser is not signed in")
            self._failure_kind = "not_signed_in"
            return False

        logger.warning("Redirect method timed out waiting for Epic's reply")
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
        self._safe_end_modal(wx.ID_CANCEL)

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
