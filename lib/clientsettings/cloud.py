"""
Fortnite cloud storage client for user settings files.

Wraps the `/fortnite/api/cloudstorage/user/{accountId}` endpoint so FA11y can
list, download, upload, and delete user-sync'd files (ClientSettings.Sav etc.)
using the existing EpicAuth bearer token — no separate auth flow needed.

Endpoint base: fortnite-public-service-prod11.ol.epicgames.com

Key behavior:
    GET    /fortnite/api/cloudstorage/user/{accountId}                -> list of files
    GET    /fortnite/api/cloudstorage/user/{accountId}/{filename}     -> raw bytes
    PUT    /fortnite/api/cloudstorage/user/{accountId}/{filename}     -> replace
    DELETE /fortnite/api/cloudstorage/user/{accountId}/{filename}     -> remove

Files the server considers "restricted" (certain per-platform files, UUID
replay files, etc.) are filtered out by default to avoid accidental
cross-platform writes.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

import requests

from lib.utilities.epic_auth import EpicAuth

logger = logging.getLogger(__name__)


CLOUDSTORAGE_BASE = "https://fortnite-public-service-prod11.ol.epicgames.com"
"""Fortnite cloud storage endpoint root."""

# Files we should never touch — the platform-specific Switch save uses a
# different container format and trying to read/write it fails server-side.
RESTRICTED_FILENAMES: set[str] = {"ClientSettingsSwitch.Sav"}

# UUID-pattern files produced by gameplay (replays, temp data); don't expose.
_UUID_FILE_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_r\d+_a\d+\.sav$",
    re.IGNORECASE,
)


@dataclass
class CloudFile:
    unique_filename: str
    filename: str
    hash: str
    hash256: str
    length: int
    content_type: str
    uploaded: str
    storage_type: str
    storage_ids: dict
    do_not_cache: bool
    raw: dict

    @classmethod
    def from_dict(cls, d: dict) -> "CloudFile":
        return cls(
            unique_filename=d.get("uniqueFilename", ""),
            filename=d.get("filename", ""),
            hash=d.get("hash", ""),
            hash256=d.get("hash256", ""),
            length=d.get("length", 0),
            content_type=d.get("contentType", ""),
            uploaded=d.get("uploaded", ""),
            storage_type=d.get("storageType", ""),
            storage_ids=d.get("storageIds", {}),
            do_not_cache=d.get("doNotCache", False),
            raw=d,
        )


class CloudStorageError(Exception):
    """Raised when a cloud-storage call fails."""


def is_file_allowed(filename: str) -> bool:
    """True if `filename` is safe to show/modify via this module."""
    if filename in RESTRICTED_FILENAMES:
        return False
    if _UUID_FILE_RE.match(filename):
        return False
    return True


class CloudStorage:
    """Reads/writes the authenticated user's Fortnite cloud storage."""

    def __init__(self, auth: Optional[EpicAuth] = None, base_url: str = CLOUDSTORAGE_BASE) -> None:
        self.auth = auth or EpicAuth()
        self.base_url = base_url
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_auth(self) -> None:
        if not self.auth.access_token or not self.auth.account_id:
            raise CloudStorageError(
                "Not authenticated with Epic — sign in via FA11y first "
                "(uses the same session as the Locker/STW features)."
            )
        # If the token is expired, try a refresh before giving up.
        if not self.auth.is_valid and hasattr(self.auth, "refresh_access_token"):
            try:
                self.auth.refresh_access_token()
            except Exception as e:
                logger.debug("token refresh failed: %s", e)

    def _url(self, filename: str | None = None) -> str:
        root = f"{self.base_url}/fortnite/api/cloudstorage/user/{self.auth.account_id}"
        return root if filename is None else f"{root}/{quote(filename, safe='')}"

    def _headers(self, **extra: str) -> dict:
        h = {"Authorization": f"bearer {self.auth.access_token}"}
        h.update(extra)
        return h

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_files(self, include_restricted: bool = False) -> list[CloudFile]:
        """Return all files in the authenticated user's cloud storage."""
        self._require_auth()
        resp = self._session.get(self._url(), headers=self._headers(), timeout=30)
        if resp.status_code != 200:
            raise CloudStorageError(
                f"list failed: HTTP {resp.status_code} {resp.text[:200]}"
            )

        data = resp.json()
        if isinstance(data, list):
            raw_files = data
        elif isinstance(data, dict):
            for key in ("files", "data", "items"):
                if key in data and isinstance(data[key], list):
                    raw_files = data[key]
                    break
            else:
                if "uniqueFilename" in data:
                    raw_files = [data]
                else:
                    raise CloudStorageError(f"unexpected list payload: {list(data.keys())}")
        else:
            raise CloudStorageError(f"unexpected list payload type: {type(data)!r}")

        files = [CloudFile.from_dict(d) for d in raw_files]
        if not include_restricted:
            files = [f for f in files if is_file_allowed(f.unique_filename)]
        return files

    def find_file(self, filename: str, include_restricted: bool = False) -> CloudFile | None:
        for f in self.list_files(include_restricted=include_restricted):
            if f.unique_filename == filename:
                return f
        return None

    def download(self, filename: str) -> bytes:
        """Download a cloud file's raw bytes."""
        self._require_auth()
        if not is_file_allowed(filename):
            raise CloudStorageError(f"file {filename!r} is restricted")

        resp = self._session.get(self._url(filename), headers=self._headers(), timeout=60)
        if resp.status_code != 200:
            raise CloudStorageError(
                f"download {filename} failed: HTTP {resp.status_code} {resp.text[:200]}"
            )
        return resp.content

    def download_to_path(self, filename: str, dest_path: str) -> int:
        data = self.download(filename)
        with open(dest_path, "wb") as f:
            f.write(data)
        return len(data)

    def upload(self, filename: str, data: bytes) -> None:
        """Upload bytes as the named cloud file (replaces existing)."""
        self._require_auth()
        if not is_file_allowed(filename):
            raise CloudStorageError(f"file {filename!r} is restricted")

        resp = self._session.put(
            self._url(filename),
            headers=self._headers(**{"Content-Type": "application/octet-stream"}),
            data=data,
            timeout=60,
        )
        if resp.status_code not in (200, 201, 204):
            raise CloudStorageError(
                f"upload {filename} failed: HTTP {resp.status_code} {resp.text[:200]}"
            )

    def upload_from_path(self, filename: str, src_path: str) -> int:
        with open(src_path, "rb") as f:
            data = f.read()
        self.upload(filename, data)
        return len(data)

    def delete(self, filename: str) -> None:
        self._require_auth()
        if not is_file_allowed(filename):
            raise CloudStorageError(f"file {filename!r} is restricted")

        resp = self._session.delete(self._url(filename), headers=self._headers(), timeout=30)
        if resp.status_code not in (200, 204):
            raise CloudStorageError(
                f"delete {filename} failed: HTTP {resp.status_code} {resp.text[:200]}"
            )
