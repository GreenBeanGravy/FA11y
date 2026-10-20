"""Presets for the Fortnite settings page: a name and a list of settings with the values to give them.

A preset changes only the settings it lists. Applying one edits the page's draft, the same as
changing those settings by hand: the user is told what will change first, Discard Changes undoes
it, and nothing reaches the account until Save to Fortnite.

A preset made from sections holds every setting in them, unset ones too (at game default, or a key
that isn't bound). Those would put the user's own settings back to game default, so whoever
applies the preset is asked whether to use them (defaults=False leaves them out).

A preset is a .preset file, UTF-8 JSON:

    {"type": "FA11y Fortnite settings preset", "version": 1, "name": "Turn keys", "description": "",
     "settings": [{"tab": "Keybinds", "label": "Turn Left", "section": "turn", "key": "left#1",
                   "value": "Left"}, ...]}

section, key and value are what the page's controls send (SettingsView.apply), so a preset is
checked the same way an edit is. tab and label are only there for people reading the file.
FA11y's own presets live in lib/data/fortnite_presets (none yet), the user's in
config/fortnite_presets: Export Preset and Import Preset put them there.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from lib.utilities import client_settings_binds as binds
from lib.utilities import client_settings_gamepad as pad
from lib.utilities import client_settings_turning as turning
from lib.utilities.client_settings import Save, parse_file
from lib.utilities.client_settings_catalog import DEFAULT, RECORD, VOLUME, SettingsView

TYPE = 'FA11y Fortnite settings preset'
VERSION = 1
EXTENSION = '.preset'
BUILTIN_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'fortnite_presets')
USER_DIR = os.path.join('config', 'fortnite_presets')
MAX_BYTES = 2_000_000
MAX_SETTINGS = 5000
NAME_LENGTH = 80
SECTIONS = {RECORD, VOLUME, binds.BIND, binds.SENS, pad.LOOK, turning.TURN, pad.PAD_BIND, pad.PAD_PRESET}
# What a row shows when the setting isn't set: the game uses its own default.
UNSET = ('', DEFAULT, binds.UNBOUND, None)
NOT_EDITABLE = "(can't be edited here)"


class PresetError(Exception):
    """A sentence to tell the user."""


@dataclass
class Preset:
    name: str
    settings: List[dict]
    description: str = ''
    path: str = ''
    builtin: bool = False

    @property
    def id(self) -> str:
        return ('fa11y:' if self.builtin else 'user:') + os.path.basename(self.path)


@dataclass
class Change:
    label: str
    tab: str
    before: str
    after: str

    def text(self) -> str:
        return f'{self.label} ({self.tab}): {self.before} to {self.after}'


# Reading and writing ---------------------------------------------------------------------------

def parse(data: bytes, path: str = '', builtin: bool = False) -> Preset:
    """Read a .preset file. Raises PresetError for anything that isn't one."""
    bad = PresetError('That file isn\'t an FA11y preset.')
    if len(data) > MAX_BYTES:
        raise bad
    try:
        doc = json.loads(data.decode('utf-8-sig'))
    except (UnicodeDecodeError, ValueError):
        raise bad from None
    if not isinstance(doc, dict) or doc.get('type') != TYPE:
        raise bad
    version = doc.get('version')
    if not isinstance(version, int) or version > VERSION:
        raise PresetError('That preset was made by a newer FA11y. Update FA11y to use it.')
    name, description, rows = doc.get('name'), doc.get('description', ''), doc.get('settings')
    if not isinstance(name, str) or not name.strip() or not isinstance(description, str):
        raise bad
    if not isinstance(rows, list) or len(rows) > MAX_SETTINGS:
        raise bad
    settings = []
    for row in rows:
        if (not isinstance(row, dict) or row.get('section') not in SECTIONS or not isinstance(row.get('key'), str)
                or not isinstance(row.get('value', ''), (str, int, float, bool, type(None)))):
            raise bad
        settings.append({'tab': str(row.get('tab', '')), 'label': str(row.get('label', row['key'])),
                         'section': row['section'], 'key': row['key'], 'value': row.get('value')})
    return Preset(name.strip()[:NAME_LENGTH], settings, description.strip(), path, builtin)


def to_bytes(preset: Preset) -> bytes:
    doc = {'type': TYPE, 'version': VERSION, 'name': preset.name, 'description': preset.description,
           'settings': [{k: row.get(k) for k in ('tab', 'label', 'section', 'key', 'value')}
                        for row in preset.settings]}
    return (json.dumps(doc, ensure_ascii=False, indent=1) + '\n').encode('utf-8')


def load(path: str, builtin: bool = False) -> Preset:
    try:
        with open(path, 'rb') as f:
            data = f.read(MAX_BYTES + 1)
    except OSError:
        raise PresetError('FA11y couldn\'t open that file.') from None
    return parse(data, path, builtin)


def all_presets(builtin_dir: Optional[str] = None, user_dir: Optional[str] = None) -> List[Preset]:
    """FA11y's presets, then the user's, each by name. Files that can't be read are skipped."""
    out = []
    for folder, builtin in ((BUILTIN_DIR if builtin_dir is None else builtin_dir, True),
                            (USER_DIR if user_dir is None else user_dir, False)):
        if not os.path.isdir(folder):
            continue
        found = []
        for name in os.listdir(folder):
            if name.lower().endswith(EXTENSION):
                try:
                    found.append(load(os.path.join(folder, name), builtin))
                except PresetError:
                    continue
        out += sorted(found, key=lambda p: p.name.lower())
    return out


def find(preset_id: str) -> Preset:
    for preset in all_presets():
        if preset.id == preset_id:
            return preset
    raise PresetError('That preset is gone. It may have been deleted.')


def file_name(name: str) -> str:
    """A file name for a preset name: letters, digits, spaces and a few marks."""
    stem = re.sub(r'[^\w\- ()&\']+', ' ', name).strip()[:60].strip() or 'Preset'
    return stem + EXTENSION


def user_preset_named(name: str) -> Optional[Preset]:
    return next((p for p in all_presets(builtin_dir='') if p.name.lower() == name.lower()), None)


def save_user(preset: Preset, replace: bool = False) -> Preset:
    """Keep a preset among the user's. With replace, one of the same name is overwritten;
    otherwise the name must be free."""
    user_dir = USER_DIR
    existing = user_preset_named(preset.name)
    if existing is not None and not replace:
        raise PresetError(f'You already have a preset named {preset.name}.')
    os.makedirs(user_dir, exist_ok=True)
    if existing is not None:
        path = existing.path
    else:
        path = os.path.join(user_dir, file_name(preset.name))
        n = 2
        while os.path.exists(path):
            path = os.path.join(user_dir, file_name(preset.name)[:-len(EXTENSION)] + f' {n}' + EXTENSION)
            n += 1
    data = to_bytes(preset)
    with open(path, 'wb') as f:
        f.write(data)
    return Preset(preset.name, preset.settings, preset.description, path, False)


def import_file(path: str) -> Tuple[Preset, bool]:
    """Add a .preset file to the user's presets. Returns the stored preset and whether it was
    already there (same settings, under its name or a numbered one). A different preset with the
    same name gets a number."""
    preset = load(path)
    same_name = re.compile(re.escape(preset.name) + r'( \d+)?', re.IGNORECASE)
    for existing in all_presets(builtin_dir=''):
        if same_name.fullmatch(existing.name) and existing.settings == preset.settings:
            return existing, True
    name, n = preset.name, 2
    while user_preset_named(name) is not None:
        name = f'{preset.name} {n}'
        n += 1
    return save_user(Preset(name, preset.settings, preset.description)), False


def delete_user(preset: Preset) -> None:
    if preset.builtin:
        raise PresetError('FA11y\'s own presets can\'t be deleted.')
    try:
        os.remove(preset.path)
    except FileNotFoundError:
        pass
    except OSError:
        raise PresetError(f'FA11y couldn\'t delete {preset.name}.') from None


# Making a preset from the page --------------------------------------------------------------------

def _rows(view: SettingsView) -> List[Tuple[str, str, dict]]:
    """Every row on the page, with its tab and group heading, Controller Binds included."""
    shown = view.controller
    view.controller = True
    try:
        tabs = view.schema()
    finally:
        view.controller = shown
    return [(tab['name'], group['heading'], entry) for tab in tabs for group in tab['groups']
            for entry in group['settings']]


def _editable(entry: dict) -> bool:
    return entry.get('value') != NOT_EDITABLE


def _row(tab: str, entry: dict) -> dict:
    return {'tab': tab, 'label': entry['label'], 'section': entry['section'], 'key': entry['key'],
            'value': entry['value']}


def _plural(n: int) -> str:
    return f"{n} setting{'s' if n != 1 else ''}"


def export_groups(view: SettingsView) -> List[dict]:
    """The page's sections, as {id, label, count, detail}: every setting that can be edited here,
    with how many of them are at game default or not bound."""
    counts: Dict[Tuple[str, str], List[int]] = {}
    for tab, heading, entry in _rows(view):
        if _editable(entry):
            n = counts.setdefault((tab, heading), [0, 0, 0])
            n[0] += 1
            n[1] += entry.get('value') in UNSET and entry.get('value') != binds.UNBOUND
            n[2] += entry.get('value') == binds.UNBOUND
    out = []
    for (tab, heading), (count, default, unbound) in counts.items():
        detail = _plural(count) + (f', {default} at game default' if default else '') + (
            f', {unbound} not bound' if unbound else '')
        out.append({'id': f'{tab}/{heading}', 'label': f'{tab}: {heading}', 'count': count, 'detail': detail})
    return out


def rows_from_groups(view: SettingsView, group_ids: List[str]) -> List[dict]:
    """Every setting in the chosen sections, the ones at game default and keys that aren't bound too."""
    wanted = set(group_ids)
    return [_row(tab, entry) for tab, heading, entry in _rows(view)
            if f'{tab}/{heading}' in wanted and _editable(entry)]


def rows_from_changes(view: SettingsView) -> List[dict]:
    """Every setting changed since the file was loaded, including ones put back to game default."""
    before = {entry['id']: entry['value'] for _tab, _heading, entry in _rows(SettingsView(view.original, view.original))}
    return [_row(tab, entry) for tab, _heading, entry in _rows(view)
            if entry['id'] in before and before[entry['id']] != entry['value'] and entry['value'] != NOT_EDITABLE]


# Applying -----------------------------------------------------------------------------------------

def _shown(entry: Optional[dict]) -> str:
    """A row's value as the page says it."""
    if entry is None:
        return 'Game default'
    if 'display' in entry:
        return entry['display']
    value = entry.get('value')
    for choice in entry.get('choices', []):
        if choice['value'] == value:
            return choice['label']
    if value in UNSET:
        return 'Game default'
    if isinstance(value, float):
        return f'{value:.4f}'.rstrip('0').rstrip('.') or '0'
    return str(value)


def unset_rows(preset: Preset) -> List[dict]:
    """The preset's settings at game default and keys that aren't bound."""
    return [row for row in preset.settings if row.get('value') in UNSET]


def unset_kinds(preset: Preset) -> str:
    """What the unset rows are, for a sentence: "settings at game default", "keys that aren't bound" or both."""
    values = {row.get('value') for row in unset_rows(preset)}
    default, unbound = bool(values - {binds.UNBOUND}), binds.UNBOUND in values
    kinds = (['settings at game default'] if default else []) + (['keys that aren\'t bound'] if unbound else [])
    return ' and '.join(kinds)


def _chosen(preset: Preset, defaults: bool) -> Preset:
    if defaults:
        return preset
    return Preset(preset.name, [row for row in preset.settings if row.get('value') not in UNSET],
                  preset.description, preset.path, preset.builtin)


def apply_rows(view: SettingsView, preset: Preset, defaults: bool = True) -> List[str]:
    """Set each listed setting on the view's file (without defaults, leave out the unset ones).
    Returns what was skipped, and why.

    Setting a controller button switches the controller preset to Custom, so buttons that already
    match are left alone and the preset's own Controller Preset row goes last."""
    skipped = []
    rows = sorted(_chosen(preset, defaults).settings, key=lambda r: r['section'] == pad.PAD_PRESET)
    buttons = pad.pad_values(view.save)
    for row in rows:
        if row['section'] == pad.PAD_BIND and buttons.get(f"{pad.PAD_BIND}/{row['key']}") == row['value']:
            continue
        try:
            view.apply(row['section'], row['key'], row['value'])
        except ValueError as e:
            reason = 'isn\'t in your settings' if str(e) == 'Unknown setting.' else str(e).rstrip('.')
            where = f" ({row['tab']})" if row['tab'] else ''
            skipped.append(f"{row['label']}{where}: {reason}.")
    return skipped


def preview(save_bytes: bytes, original: Save, preset: Preset,
            defaults: bool = True) -> Tuple[List[Change], List[str]]:
    """What applying the preset to this file would change, without changing it: every row whose
    value would differ (side effects included, like the controller preset switching to Custom),
    and the settings that would be skipped."""
    copy = parse_file(save_bytes)
    view = SettingsView(copy.save, original)
    before = {entry['id']: entry for _tab, _heading, entry in _rows(view)}
    skipped = apply_rows(view, preset, defaults)
    changes = []
    for tab, _heading, entry in _rows(view):
        old = before.get(entry['id'])
        if old is None or old.get('value') != entry.get('value'):
            changes.append(Change(entry['label'], tab, _shown(old), _shown(entry)))
    return changes, skipped


def unset_changes(save_bytes: bytes, original: Save, preset: Preset) -> List[Change]:
    """What the preset's unset rows would change on top of the rest: the user's own settings they
    would put back to game default, and keys they would unbind."""
    if not unset_rows(preset):
        return []
    kept = {c.text() for c in preview(save_bytes, original, preset, defaults=False)[0]}
    return [c for c in preview(save_bytes, original, preset)[0] if c.text() not in kept]
