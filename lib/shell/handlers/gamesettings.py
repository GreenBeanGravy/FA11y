"""Requests for the Fortnite Settings page: the game's own settings, edited outside the game.

The page loads the account's ClientSettings.Sav from Epic's cloud storage (gamesettings.schema),
and changes edit a draft held here (gamesettings.set, gamesettings.reset). Nothing reaches the
account until the user presses Save to Fortnite (gamesettings.action "upload"), which needs
Fortnite to be closed. Discard drops the draft; Reload downloads the file again; Restore puts
back the file as it was before FA11y's last save.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from lib.shell.bridge import handler
from lib.utilities.client_settings import SettingsFile, SettingsFileError, parse_file
from lib.utilities.client_settings_catalog import SettingsView
from lib.utilities.epic_cloud_settings import CloudFile, CloudSettingsAPI, CloudSettingsError, sha1

logger = logging.getLogger(__name__)

VIEW = 'gamesettings'
SIGN_IN_MESSAGE = 'Sign in to your Epic account on the Epic Account page to edit your Fortnite settings.'
ACTIONS = [
    {'id': 'upload', 'label': 'Save to Fortnite',
     'help': 'Uploads your changes to your Epic account. Fortnite must be closed.',
     'confirm': 'Save your changes to your Fortnite settings? Fortnite uses them the next time it starts.'},
    {'id': 'discard', 'label': 'Discard Changes', 'help': 'Puts every setting back to how it was loaded.'},
    {'id': 'reload', 'label': 'Reload', 'help': 'Downloads your Fortnite settings from Epic again.'},
    {'id': 'restore', 'label': 'Restore Previous Settings',
     'help': 'Puts back your Fortnite settings as they were before FA11y last saved them.',
     'confirm': 'Put back your Fortnite settings as they were before FA11y last saved them?'},
]

_lock = threading.RLock()


class Session:
    """The settings file as downloaded, and the draft the user is editing."""

    def __init__(self, base: CloudFile):
        self.base = base
        original = parse_file(base.data)
        self.draft = parse_file(base.data)
        self.view = SettingsView(self.draft.save, original.save)


_session: Optional[Session] = None


def _auth():
    from lib.utilities.epic_auth import get_epic_auth_instance
    return get_epic_auth_instance()


def _api() -> CloudSettingsAPI:
    return CloudSettingsAPI(_auth())


def _signed_in() -> bool:
    auth = _auth()
    return bool(auth and auth.access_token and auth.account_id)


def _game_running() -> bool:
    from lib.hub import game_watch
    return game_watch.fortnite_running_now()


def _status(session: Optional[Session]) -> str:
    if session is None:
        return ''
    changes = session.view.changes()
    if not changes:
        return 'No unsaved changes.'
    names = ', '.join(changes[:5]) + (f', and {len(changes) - 5} more' if len(changes) > 5 else '')
    return f"{len(changes)} unsaved change{'s' if len(changes) != 1 else ''}: {names}."


def _load(force: bool = False) -> Session:
    global _session
    with _lock:
        auth = _auth()
        if _session is not None and not force and _session.base.account_id == auth.account_id:
            return _session
        base = _api().download()
        try:
            _session = Session(base)
        except SettingsFileError as e:
            logger.error(f'Could not read the Fortnite settings file: {e}')
            raise CloudSettingsError('FA11y could not read your Fortnite settings file. '
                                     'A Fortnite update may have changed it.') from None
        return _session


def _require() -> Session:
    if _session is None:
        raise ValueError('The settings are not loaded.')
    return _session


@handler('gamesettings.schema')
def gamesettings_schema(params: dict) -> dict:
    if not _signed_in():
        return {'view': VIEW, 'tabs': [], 'login': True, 'message': SIGN_IN_MESSAGE}
    try:
        session = _load(force=bool(params.get('reload')))
    except CloudSettingsError as e:
        return {'view': VIEW, 'tabs': [], 'message': str(e), 'actions': [a for a in ACTIONS if a['id'] == 'reload']}
    with _lock:
        return {'view': VIEW, 'tabs': session.view.schema(), 'actions': ACTIONS, 'status': _status(session)}


@handler('gamesettings.search_index')
def gamesettings_search_index(_params: dict) -> dict:
    with _lock:
        return {'entries': _session.view.search_entries() if _session else []}


@handler('gamesettings.set')
def gamesettings_set(params: dict) -> dict:
    with _lock:
        session = _require()
        shown = session.view.apply(str(params.get('section', '')), str(params.get('key', '')), params.get('value'))
        return {'value': shown, 'status': _status(session)}


@handler('gamesettings.reset')
def gamesettings_reset(params: dict) -> dict:
    """Put one setting back to how it was loaded."""
    with _lock:
        session = _require()
        section, key = str(params.get('section', '')), str(params.get('key', ''))
        label = str(params.get('label', key))
        current = session.view.apply(section, key, session.view.original_value(section, key))
        return {'changed': True, 'value': current, 'status': _status(session),
                'message': f'{label} is back to how it was loaded.'}


def _upload(data: bytes, base: CloudFile) -> str:
    message = _api().upload(data, base, _game_running)
    global _session
    _session = Session(CloudFile(data, sha1(data), base.account_id))
    return message


@handler('gamesettings.action')
def gamesettings_action(params: dict) -> dict:
    """Save, discard, reload or restore. Returns the sentence to announce, and whether to reload the page."""
    action = str(params.get('id', ''))
    with _lock:
        try:
            if action == 'reload':
                _load(force=True)
                return {'message': 'Loaded your Fortnite settings.', 'reload': True}
            session = _require()
            if action == 'discard':
                changes = session.view.changes()
                _load_session_from(session.base)
                return {'message': 'Discarded your changes.' if changes else 'There were no changes to discard.',
                        'reload': bool(changes)}
            if action == 'upload':
                changes = session.view.changes()
                if not changes:
                    return {'message': 'There are no changes to save.', 'reload': False}
                data = session.draft.to_bytes()
                check = parse_file(data)            # never upload a file FA11y can't read back
                if check.to_bytes() != data:
                    raise CloudSettingsError('FA11y could not build a valid settings file. Nothing was saved.')
                message = _upload(data, session.base)
                return {'message': message, 'reload': True}
            if action == 'restore':
                api = _api()
                path = api.latest_backup()
                if path is None:
                    return {'message': 'FA11y has not saved your Fortnite settings before, so there is nothing to restore.',
                            'reload': False}
                with open(path, 'rb') as f:
                    data = f.read()
                parse_file(data)
                message = _upload(data, session.base)
                return {'message': 'Restored your previous settings. ' + message, 'reload': True}
        except (CloudSettingsError, SettingsFileError) as e:
            return {'message': str(e), 'reload': False, 'status': _status(_session)}
    raise ValueError('Unknown action.')


def _load_session_from(base: CloudFile) -> None:
    global _session
    _session = Session(base)


@handler('gamesettings.leave')
def gamesettings_leave(_params: dict) -> dict:
    return {}
