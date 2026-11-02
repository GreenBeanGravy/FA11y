"""Settings live in %APPDATA%\\FA11y\\config, moved there once, and can be imported (11/02/2026)."""
import configparser
import os

import pytest

from lib.utilities import user_paths


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    """A fake APPDATA and install folder; no FA11Y_CONFIG_DIR override."""
    monkeypatch.delenv('FA11Y_CONFIG_DIR', raising=False)
    monkeypatch.setenv('APPDATA', str(tmp_path / 'Roaming'))
    install = tmp_path / 'install' / 'config'
    install.mkdir(parents=True)
    monkeypatch.setattr(user_paths, 'INSTALL_CONFIG_DIR', install)
    user_paths.config_dir()
    return tmp_path / 'Roaming' / 'FA11y' / 'config', install


def test_settings_folder_is_in_appdata_and_old_paths_resolve_there(appdata):
    settings, _ = appdata
    assert user_paths.config_dir() == str(settings) and settings.is_dir()
    assert user_paths.resolve('config/epic_auth_cache.json') == str(settings / 'epic_auth_cache.json')
    assert user_paths.resolve('config\\match_history\\x.json') == str(settings / 'match_history' / 'x.json')
    assert user_paths.resolve('lib/data/x.json') == 'lib/data/x.json'


def test_install_config_moves_once_and_the_token_stays(appdata):
    settings, install = appdata
    (install / 'config.txt').write_text('[Toggles]\nMouseKeys = true "x"\n', encoding='utf-8')
    (install / 'FAVORITE_POIS.txt').write_text('[]', encoding='utf-8')
    (install / 'github_token.txt').write_text('token', encoding='utf-8')
    (install / 'match_history').mkdir()
    assert sorted(user_paths.migrate_install_config()) == ['FAVORITE_POIS.txt', 'config.txt', 'match_history']
    assert (settings / 'config.txt').read_text(encoding='utf-8').startswith('[Toggles]')
    assert (settings / 'match_history').is_dir()
    assert (install / 'github_token.txt').exists() and not (settings / 'github_token.txt').exists()
    (install / 'config.txt').write_text('later', encoding='utf-8')
    assert user_paths.migrate_install_config() == []          # AppData already has a config.txt
    assert (install / 'config.txt').read_text(encoding='utf-8') == 'later'


def test_no_move_while_an_override_is_set(appdata, monkeypatch, tmp_path):
    _, install = appdata
    (install / 'config.txt').write_text('x', encoding='utf-8')
    monkeypatch.setenv('FA11Y_CONFIG_DIR', str(tmp_path / 'elsewhere'))
    assert user_paths.migrate_install_config() == []
    assert (install / 'config.txt').exists()


def test_import_a_config_folder_moves_it_and_backs_up_what_it_replaces(appdata, tmp_path):
    settings, _ = appdata
    (settings / 'config.txt').write_text('defaults', encoding='utf-8')
    old = tmp_path / 'FA11y-PacketBeta'
    (old / 'config').mkdir(parents=True)
    (old / 'config' / 'config.txt').write_text('mine', encoding='utf-8')
    (old / 'config' / 'CUSTOM_POI.txt').write_text('poi', encoding='utf-8')
    result = user_paths.import_config(str(old))                # an FA11y folder: its config folder is used
    assert sorted(result['moved']) == ['CUSTOM_POI.txt', 'config.txt']
    assert (settings / 'config.txt').read_text(encoding='utf-8') == 'mine'
    assert open(os.path.join(result['backup'], 'config.txt'), encoding='utf-8').read() == 'defaults'
    assert not (old / 'config').exists()                       # emptied, so removed


def test_import_a_single_config_txt(appdata, tmp_path):
    settings, _ = appdata
    source = tmp_path / 'backup' / 'config.txt'
    source.parent.mkdir()
    source.write_text('mine', encoding='utf-8')
    result = user_paths.import_config(f'"{source}"')
    assert result == {'moved': ['config.txt'], 'backup': None}
    assert (settings / 'config.txt').read_text(encoding='utf-8') == 'mine' and not source.exists()


def test_import_refuses_what_it_cannot_use(appdata, tmp_path):
    settings, _ = appdata
    (tmp_path / 'empty').mkdir()
    for path, words in ((tmp_path / 'empty', 'no config.txt'), (tmp_path / 'missing', 'not found'),
                        (settings, 'already')):
        if path == settings:
            (settings / 'config.txt').write_text('x', encoding='utf-8')
        with pytest.raises(user_paths.ConfigImportError, match=words):
            user_paths.import_config(str(path))


def test_defaults_only_check(tmp_path, monkeypatch):
    from lib.utilities import utilities
    path = tmp_path / 'config.txt'
    monkeypatch.setattr(utilities, 'CONFIG_FILE', str(path))
    assert utilities.config_uses_defaults_only()                # no file yet
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read_string(utilities.DEFAULT_CONFIG)
    path.write_text('[Toggles]\n', encoding='utf-8')
    assert utilities.config_uses_defaults_only(config)
    section = 'Toggles' if config.has_option('Toggles', 'MouseKeys') else config.sections()[0]
    key = 'MouseKeys' if section == 'Toggles' else config.options(section)[0]
    value, _, rest = config.get(section, key).partition('"')
    config.set(section, key, ('false' if value.strip().lower() == 'true' else 'true') + ' "' + rest)
    assert not utilities.config_uses_defaults_only(config)
