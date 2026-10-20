"""Requests for the Fortnite Settings page: the game's own settings, edited outside the game.

The page loads the account's ClientSettings.Sav from Epic's cloud storage (gamesettings.schema),
and changes edit a draft held here (gamesettings.set, gamesettings.reset). Nothing reaches the
account until the user presses Save to Fortnite (gamesettings.action "upload"), which needs
Fortnite to be closed. Discard drops the draft; Reload downloads the file again; Restore puts
back the file as it was before FA11y's last save.

Presets (client_settings_presets) apply to the draft too: gamesettings.presets lists them,
preset_preview says what one would change, preset_apply changes it, and preset_import,
preset_export and preset_delete manage the user's .preset files.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from lib.shell.bridge import handler
from lib.utilities import client_settings_binds as binds
from lib.utilities import client_settings_gamepad as pad
from lib.utilities import client_settings_presets as presets
from lib.utilities import client_settings_turning as turning
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
    {'id': 'presets', 'label': 'Presets',
     'help': 'Changes the settings a preset lists. You hear what changes before anything does.'},
    {'id': 'import_preset', 'label': 'Import Preset', 'help': 'Adds a .preset file to your presets.'},
    {'id': 'export_preset', 'label': 'Export Preset',
     'help': 'Saves settings you pick as a .preset file you can share, and adds it to your presets.'},
]
# The three preset buttons are handled by the window: it opens dialogs, then sends the
# gamesettings.preset_* requests below.

_lock = threading.RLock()


class Session:
    """The settings file as downloaded, and the draft the user is editing."""

    def __init__(self, base: CloudFile):
        self.base = base
        original = parse_file(base.data)
        self.draft = parse_file(base.data)
        self.view = SettingsView(self.draft.save, original.save, controller=_controller_connected())


_session: Optional[Session] = None


def _auth():
    from lib.utilities.epic_auth import get_epic_auth_instance
    return get_epic_auth_instance()


def _api() -> CloudSettingsAPI:
    return CloudSettingsAPI(_auth())


def _signed_in() -> bool:
    auth = _auth()
    return bool(auth and auth.access_token and auth.account_id)


def _controller_connected() -> bool:
    return pad.controller_connected()


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
        section, key = str(params.get('section', '')), str(params.get('key', ''))
        was_custom = pad.preset(session.draft.save) == pad.CUSTOM_PRESET
        shown = session.view.apply(section, key, params.get('value'))
        result = {'value': shown, 'status': _status(session), **_key_display(section, key, shown)}
        notes = []
        if section == pad.PAD_BIND and not was_custom:
            notes.append('Controller preset switched to Custom, so this button counts.')
            # Other rows the change moved, for the page to show without reloading.
            result['updates'] = [{'id': f'{pad.PAD_PRESET}/{pad.PRESET}', 'value': pad.CUSTOM_PRESET}]
        others = (binds.conflicts(session.draft.save, key) if section == binds.BIND
                  else turning.conflicts(session.draft.save, key) if section == turning.TURN
                  else pad.pad_conflicts(session.draft.save, key) if section == pad.PAD_BIND else [])
        if others:
            notes.append('Also used by ' + ', '.join(others[:3]) + '.')
        if notes:
            result['message'] = ' '.join(notes)
        return result


@handler('gamesettings.reset')
def gamesettings_reset(params: dict) -> dict:
    """Put one setting back to how it was loaded."""
    with _lock:
        session = _require()
        section, key = str(params.get('section', '')), str(params.get('key', ''))
        label = str(params.get('label', key))
        current = session.view.apply(section, key, session.view.original_value(section, key))
        return {'changed': True, 'value': current, 'status': _status(session), **_key_display(section, key, current),
                'message': f'{label} is back to how it was loaded.'}


def _key_display(section: str, key: str, value) -> dict:
    """For a key or button row, the name its button shows."""
    if section in (binds.BIND, turning.TURN) and not key.startswith('speed:'):
        return {'display': binds.key_label(value)}
    if section == pad.PAD_BIND:
        return {'display': pad.PAD_KEY_LABELS.get(value, value)}
    return {}


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


# Presets -----------------------------------------------------------------------------------------

def _plural(n: int, word: str = 'setting') -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


@handler('gamesettings.presets')
def gamesettings_presets(_params: dict) -> dict:
    return {'presets': [{'id': p.id, 'name': p.name, 'description': p.description, 'builtin': p.builtin,
                         'count': len(p.settings)} for p in presets.all_presets()]}


@handler('gamesettings.preset_preview')
def gamesettings_preset_preview(params: dict) -> dict:
    """What a preset would change, as the sentences the confirm dialog shows.

    Without defaults (true or false), a preset whose game default settings or unbound keys would
    reset some of the user's settings first gets ask_defaults: a question and the settings it
    resets. The window asks, then previews again with the answer."""
    intro = {'added': 'Added {} to your presets. ',
             'already': '{} is already in your presets. '}.get(str(params.get('imported', '')), '')
    defaults = params.get('defaults')
    with _lock:
        session = _require()
        try:
            preset = presets.find(str(params.get('id', '')))
        except presets.PresetError as e:
            return {'ok': False, 'message': str(e)}
        intro = intro.format(preset.name)
        if defaults is None:
            extra = presets.unset_changes(session.draft.to_bytes(), session.view.original, preset)
            if extra:
                return {'ok': True, 'ask_defaults': True, 'id': preset.id, 'name': preset.name,
                        'builtin': preset.builtin, 'changes': len(extra), 'lines': [c.text() for c in extra],
                        'prompt': f'{intro}{preset.name} also resets {_plural(len(extra))} of yours. '
                                  f"Reset {'it' if len(extra) == 1 else 'them'} too?"}
        changes, skipped = presets.preview(session.draft.to_bytes(), session.view.original, preset,
                                           defaults=defaults is not False)
    about = f'{preset.description} ' if preset.description else ''
    if changes:
        prompt = f'{intro}Apply {preset.name}? {about}It changes {_plural(len(changes))}:'
    elif defaults is False:
        prompt = f'{intro}{about}Apart from the resets, your settings already match {preset.name}.'
    else:
        prompt = f'{intro}{about}Your settings already match {preset.name}.'
    if skipped:
        prompt += f" {_plural(len(skipped))} in it {'are' if len(skipped) != 1 else 'is'} skipped."
    return {'ok': True, 'id': preset.id, 'name': preset.name, 'builtin': preset.builtin, 'prompt': prompt,
            'changes': len(changes), 'lines': [c.text() for c in changes] + ['Skipped: ' + s for s in skipped]}


@handler('gamesettings.preset_apply')
def gamesettings_preset_apply(params: dict) -> dict:
    with _lock:
        session = _require()
        try:
            preset = presets.find(str(params.get('id', '')))
        except presets.PresetError as e:
            return {'message': str(e), 'reload': False}
        defaults = params.get('defaults') is not False
        changes, _skipped = presets.preview(session.draft.to_bytes(), session.view.original, preset, defaults)
        presets.apply_rows(session.view, preset, defaults)
        if not changes:
            return {'message': f'Nothing changed. Your settings already match {preset.name}.', 'reload': False,
                    'status': _status(session)}
        return {'message': f'Applied {preset.name}: {_plural(len(changes))} changed. '
                           'Save to Fortnite to keep them.', 'reload': True, 'status': _status(session)}


@handler('gamesettings.preset_import')
def gamesettings_preset_import(params: dict) -> dict:
    try:
        preset, already = presets.import_file(str(params.get('path', '')))
    except presets.PresetError as e:
        return {'ok': False, 'message': str(e)}
    except OSError:
        return {'ok': False, 'message': 'FA11y couldn\'t add that preset to your presets.'}
    return {'ok': True, 'id': preset.id, 'name': preset.name, 'imported': 'already' if already else 'added'}


@handler('gamesettings.preset_export_options')
def gamesettings_preset_export_options(_params: dict) -> dict:
    """The sections a preset can be made from, and how many unsaved changes there are."""
    with _lock:
        session = _require()
        return {'groups': presets.export_groups(session.view),
                'changes': len(presets.rows_from_changes(session.view))}


@handler('gamesettings.preset_export')
def gamesettings_preset_export(params: dict) -> dict:
    """Make a preset from the unsaved changes (changes: true) or the chosen sections (groups), keep
    it among the user's presets, and write it to path when one is given."""
    name = str(params.get('name', '')).strip()[:presets.NAME_LENGTH]
    if not name:
        return {'ok': False, 'message': 'Give the preset a name.'}
    with _lock:
        session = _require()
        rows = (presets.rows_from_changes(session.view) if params.get('changes')
                else presets.rows_from_groups(session.view, [str(g) for g in params.get('groups') or []]))
    if not rows:
        return {'ok': False, 'message': 'There are no settings to put in the preset.'}
    if not params.get('replace') and presets.user_preset_named(name) is not None:
        return {'ok': False, 'exists': True, 'message': f'You already have a preset named {name}. Replace it?'}
    try:
        stored = presets.save_user(presets.Preset(name, rows), replace=True)
    except (presets.PresetError, OSError):
        return {'ok': False, 'message': 'FA11y couldn\'t save the preset.'}
    path = str(params.get('path') or '')
    if not path:
        return {'ok': True, 'id': stored.id, 'message': f'Saved {name} to your presets, with {_plural(len(rows))}.'}
    try:
        with open(path, 'wb') as f:
            f.write(presets.to_bytes(stored))
    except OSError:
        return {'ok': True, 'id': stored.id,
                'message': f'Saved {name} to your presets, but FA11y couldn\'t write {path}.'}
    return {'ok': True, 'id': stored.id,
            'message': f'Saved {name}, with {_plural(len(rows))}, to your presets and to {path}.'}


@handler('gamesettings.preset_delete')
def gamesettings_preset_delete(params: dict) -> dict:
    try:
        preset = presets.find(str(params.get('id', '')))
        presets.delete_user(preset)
    except presets.PresetError as e:
        return {'ok': False, 'message': str(e)}
    return {'ok': True, 'message': f'Deleted {preset.name}.'}
