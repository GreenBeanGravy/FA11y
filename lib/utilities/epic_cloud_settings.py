"""Fortnite's settings file in the player's Epic cloud storage.

The game downloads ClientSettings.Sav when it signs in, unless the copy it cached under
``Saved\\Cloud\\<account id>`` has the same SHA-1 as the cloud copy, and uploads it after every
change in its settings menu. So changes made outside the game only stick when they are uploaded
here, and only while the game is closed (a running game would upload its own copy over them).

Downloads may retry once after refreshing the sign-in; an upload is sent once and then checked by
listing the files again, so a failed or uncertain upload is never repeated blindly.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import quote

import requests

from lib.utilities.epic_passes import rejection_detail

logger = logging.getLogger(__name__)

FILE_NAME = 'ClientSettings.Sav'
CLOUD_URL = 'https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/cloudstorage/user/'
BACKUP_DIR = os.path.join('config', 'fortnite_settings_backups')
BACKUPS_KEPT = 10
_OPERATIONS = threading.RLock()


class CloudSettingsError(Exception):
    """A sentence to show the user; never includes raw responses or account secrets."""


@dataclass(frozen=True)
class CloudFile:
    data: bytes
    sha1: str
    account_id: str


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def local_cache_path(account_id: str) -> Optional[str]:
    base = os.environ.get('LOCALAPPDATA')
    if not base or not re.fullmatch(r'[0-9a-f]{32}', account_id or ''):
        return None
    return os.path.join(base, 'FortniteGame', 'Saved', 'Cloud', account_id, FILE_NAME)


class CloudSettingsAPI:
    def __init__(self, auth, session=None, backup_dir: str = BACKUP_DIR,
                 clock: Callable[[], float] = time.time, cache_path=local_cache_path):
        self.auth = auth
        self.session = session or requests.Session()
        self.backup_dir = backup_dir
        self.clock = clock
        self.cache_path = cache_path

    def _account(self) -> str:
        if not self.auth or not getattr(self.auth, 'account_id', None) or not getattr(self.auth, 'access_token', None):
            raise CloudSettingsError('Sign in to your Epic account first.')
        return self.auth.account_id

    def _request(self, method: str, url: str, *, mutation: bool = False, **kwargs):
        if hasattr(self.auth, 'ensure_valid') and not self.auth.ensure_valid():
            raise CloudSettingsError('Your Epic sign-in has expired. Sign in again, then try again.')
        for attempt in range(2):
            try:
                response = self.session.request(method, url, timeout=30,
                                                headers={'Authorization': 'Bearer ' + self.auth.access_token,
                                                         **kwargs.pop('headers', {})}, **kwargs)
            except requests.RequestException:
                raise CloudSettingsError('The upload result is uncertain. Reload before trying again.' if mutation
                                         else 'Could not reach Epic Games. Try again in a moment.') from None
            if response.status_code == 401 and not mutation and attempt == 0 and self.auth.refresh_access_token():
                continue
            if response.status_code not in (200, 204):
                message = {401: 'Your Epic sign-in has expired. Sign in again, then try again.',
                           403: 'Epic did not allow this account to change that file.',
                           404: 'Epic has no Fortnite settings for this account yet. Open Fortnite once first.',
                           429: 'Epic limited these requests. Try again later.'}.get(response.status_code)
                detail = rejection_detail(response, self.auth)
                raise CloudSettingsError((message or f'Epic rejected the request (HTTP {response.status_code}).')
                                         + (' ' + detail if detail else ''))
            return response

    def _url(self, account_id: str, name: str = '') -> str:
        return CLOUD_URL + account_id + ('/' + quote(name, safe='') if name else '')

    def cloud_hash(self) -> Optional[str]:
        """The SHA-1 Epic lists for the settings file, or None if there is no such file."""
        account = self._account()
        listing = self._request('GET', self._url(account)).json()
        files = listing if isinstance(listing, list) else listing.get('files', []) if isinstance(listing, dict) else []
        for entry in files:
            if isinstance(entry, dict) and entry.get('uniqueFilename') == FILE_NAME:
                value = entry.get('hash')
                return value.lower() if isinstance(value, str) else None
        return None

    def download(self) -> CloudFile:
        with _OPERATIONS:
            account = self._account()
            data = self._request('GET', self._url(account, FILE_NAME)).content
            if not data:
                raise CloudSettingsError('Epic sent an empty settings file.')
            return CloudFile(data, sha1(data), account)

    def upload(self, data: bytes, base: CloudFile, is_game_running: Callable[[], bool]) -> str:
        """Replace the cloud file with ``data``, if it is still the file ``base`` was downloaded from.

        Returns the sentence to announce. Keeps the replaced file as a backup first, and afterwards
        updates the game's local cache so it doesn't download the file again.
        """
        with _OPERATIONS:
            account = self._account()
            if account != base.account_id:
                raise CloudSettingsError('You signed in to a different account. Reload the settings first.')
            if is_game_running():
                raise CloudSettingsError('Close Fortnite first. While it runs, it would put its own settings back.')
            current = self.cloud_hash()
            if current != base.sha1:
                raise CloudSettingsError('Your Fortnite settings changed since FA11y loaded them. '
                                         'Reload them, then make your changes again.')
            self.backup(base)
            self._request('PUT', self._url(account, FILE_NAME), mutation=True, data=data,
                          headers={'Content-Type': 'application/octet-stream'})
            try:
                stored = self.cloud_hash()
            except CloudSettingsError:
                stored = None
            if stored != sha1(data):
                raise CloudSettingsError('Epic took the upload, but its copy does not match. '
                                         'Reload the settings to see what Epic has.')
            self._update_cache(account, data)
            return 'Saved. Fortnite uses these settings the next time it starts.'

    def backup(self, file: CloudFile) -> str:
        os.makedirs(self.backup_dir, exist_ok=True)
        stamp = time.strftime('%Y%m%d-%H%M%S', time.localtime(self.clock()))
        path = os.path.join(self.backup_dir, f'ClientSettings-{file.account_id}-{stamp}-{file.sha1[:8]}.Sav')
        with open(path, 'wb') as f:
            f.write(file.data)
        mine = sorted(n for n in os.listdir(self.backup_dir) if n.startswith(f'ClientSettings-{file.account_id}-'))
        for old in mine[:-BACKUPS_KEPT]:
            try:
                os.remove(os.path.join(self.backup_dir, old))
            except OSError:
                pass
        return path

    def latest_backup(self) -> Optional[str]:
        account = self._account()
        if not os.path.isdir(self.backup_dir):
            return None
        mine = sorted(n for n in os.listdir(self.backup_dir) if n.startswith(f'ClientSettings-{account}-'))
        return os.path.join(self.backup_dir, mine[-1]) if mine else None

    def _update_cache(self, account: str, data: bytes) -> None:
        path = self.cache_path(account)
        if not path or not os.path.isdir(os.path.dirname(path)):
            return
        try:
            with open(path, 'wb') as f:
                f.write(data)
        except OSError as e:
            # The game downloads the new file anyway when the hashes differ.
            logger.warning(f'Could not update the game\'s cached settings: {e}')
