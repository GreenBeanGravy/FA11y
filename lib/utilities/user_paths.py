"""Where FA11y keeps your settings: %APPDATA%\\FA11y\\config, outside the install folder.

The install folder is replaced by updates and may sit in a synced folder (Dropbox, OneDrive),
so everything FA11y saves about you lives in one folder in your Windows profile instead:
config.txt, favorites, custom POIs, sign-in and other caches, the match history index.

FA11Y_CONFIG_DIR overrides the folder (the tests set it to a relative 'config', the old place).
The one file that stays in the install's own config folder is github_token.txt: Updater.exe and
FA11y_Launcher.exe look for it there (installer/internal/ghauth).

An install that still has config\\config.txt next to FA11y.py and nothing in AppData yet has its
config folder moved over once (migrate_install_config). import_config brings in a config.txt or
a config folder from anywhere else (the Import buttons in the configuration menu).
"""
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

APP_DIR_NAME = 'FA11y'
ROOT = Path(__file__).resolve().parents[2]
INSTALL_CONFIG_DIR = ROOT / 'config'
CONFIG_NAME = 'config.txt'
# Files that belong to an install, not to you: never moved or imported.
INSTALL_FILES = frozenset({'github_token.txt'})
# Earlier FA11y versions wrote these relative to the install folder.
_RELATIVE_PREFIXES = ('config/', 'config\\')


def config_dir() -> str:
    """The settings folder, created on first use."""
    override = os.environ.get('FA11Y_CONFIG_DIR')
    if override:
        path = override
    else:
        base = os.environ.get('APPDATA') or os.path.join(os.path.expanduser('~'), 'AppData', 'Roaming')
        path = os.path.join(base, APP_DIR_NAME, 'config')
    os.makedirs(path, exist_ok=True)
    return path


def config_path(*parts: str) -> str:
    """A file or folder inside the settings folder."""
    return os.path.join(config_dir(), *parts)


def config_file() -> str:
    return config_path(CONFIG_NAME)


def resolve(path):
    """'config/name' (the old install-relative form) -> that name in the settings folder.

    Anything else comes back unchanged, so absolute paths and other folders keep working."""
    text = os.fspath(path)
    for prefix in _RELATIVE_PREFIXES:
        if text.startswith(prefix):
            resolved = config_path(*text[len(prefix):].replace('\\', '/').split('/'))
            return Path(resolved) if isinstance(path, Path) else resolved
    return path


def _same_folder(a, b) -> bool:
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except OSError:
        return False


def _move_entries(source: str, target: str, backup: str | None = None) -> list[str]:
    """Move every entry of `source` into `target` except INSTALL_FILES. An entry already in
    `target` is moved into `backup` first (or kept, and the incoming one skipped, without one)."""
    moved = []
    for name in sorted(os.listdir(source)):
        if name in INSTALL_FILES:
            continue
        src, dst = os.path.join(source, name), os.path.join(target, name)
        if os.path.lexists(dst):
            if backup is None:
                continue
            os.makedirs(backup, exist_ok=True)
            shutil.move(dst, os.path.join(backup, name))
        shutil.move(src, dst)
        moved.append(name)
    return moved


def migrate_install_config() -> list[str]:
    """Once: move the install folder's config folder into the settings folder.

    Only while the settings folder has no config.txt and the install folder has one, and never
    with FA11Y_CONFIG_DIR set. Returns the names moved."""
    if os.environ.get('FA11Y_CONFIG_DIR'):
        return []
    target = config_dir()
    source = str(INSTALL_CONFIG_DIR)
    if (os.path.exists(os.path.join(target, CONFIG_NAME)) or _same_folder(source, target)
            or not os.path.isfile(os.path.join(source, CONFIG_NAME))):
        return []
    moved = _move_entries(source, target)
    if moved:
        print(f"Moved your FA11y settings to {target}")
    return moved


class ConfigImportError(ValueError):
    """A config.txt or folder that can't be imported; the message is for the user."""


def find_import_source(path: str) -> tuple[str, bool]:
    """(path to import, is_folder) for a config.txt, a config folder, or an FA11y folder."""
    path = os.path.abspath(os.path.expanduser(str(path or '').strip().strip('"')))
    if os.path.isfile(path):
        if not path.lower().endswith('.txt'):
            raise ConfigImportError('Pick a config.txt file.')
        return path, False
    if os.path.isdir(path):
        if os.path.isfile(os.path.join(path, CONFIG_NAME)):
            return path, True
        inner = os.path.join(path, 'config')
        if os.path.isfile(os.path.join(inner, CONFIG_NAME)):
            return inner, True
        raise ConfigImportError('That folder has no config.txt, and no config folder with one in it.')
    raise ConfigImportError('That file or folder was not found.')


def import_config(path: str) -> dict:
    """Move a config.txt, or every file of a config folder, into the settings folder.

    Files it replaces go to a before_import_<time> folder inside the settings folder. The source
    folder is removed once it is empty. Returns {'moved': [...], 'backup': folder or None}."""
    source, is_folder = find_import_source(path)
    target = config_dir()
    if _same_folder(source if is_folder else os.path.dirname(source), target):
        raise ConfigImportError('Those are already the settings FA11y uses.')
    backup = os.path.join(target, time.strftime('before_import_%Y%m%d_%H%M%S'))
    if is_folder:
        moved = _move_entries(source, target, backup)
        try:
            os.rmdir(source)
        except OSError:
            pass        # not empty (github_token.txt, or something in use): leave it
    else:
        dst = os.path.join(target, CONFIG_NAME)
        if os.path.exists(dst):
            os.makedirs(backup, exist_ok=True)
            shutil.move(dst, os.path.join(backup, CONFIG_NAME))
        shutil.move(source, dst)
        moved = [CONFIG_NAME]
    if CONFIG_NAME not in moved:
        raise ConfigImportError('No config.txt was moved.')
    return {'moved': moved, 'backup': backup if os.path.isdir(backup) else None}
