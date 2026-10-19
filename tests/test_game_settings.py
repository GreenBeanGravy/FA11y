"""The Fortnite Settings page: reading and writing ClientSettings.Sav, the editor's view of it,
uploading to Epic cloud storage, and the page's requests."""
import hashlib
import os
import zlib

import pytest

from lib.shell.handlers import gamesettings
from lib.utilities.client_settings import Raw, SettingsFileError, parse_file, parse_save, walk
from lib.utilities.client_settings_catalog import DEFAULT, RECORD, VOLUME, SettingsView, split_words
from lib.utilities.epic_cloud_settings import CloudSettingsAPI, CloudSettingsError, FILE_NAME
from tests.fixtures.client_settings_sample import sample_bytes

ACCOUNT = '0123456789abcdef0123456789abcdef'


def view_of(data):
    draft, original = parse_file(data), parse_file(data)
    return draft, SettingsView(draft.save, original.save)


# Reading and writing ------------------------------------------------------------------------------

def test_file_round_trips_byte_for_byte():
    data = sample_bytes()
    assert parse_file(data).to_bytes() == data
    plain = sample_bytes(wrapped=False)
    assert parse_file(plain).to_bytes() == plain


def test_cloud_wrapper_is_zlib_level_9_with_size_header():
    data = sample_bytes()
    assert data[:4] == b'ECFD'
    raw = zlib.decompress(data[16:])
    assert int.from_bytes(data[12:16], 'little') == len(raw)
    assert zlib.compress(raw, 9) == data[16:]


def test_nested_partition_and_raw_values_are_kept():
    f = parse_file(sample_bytes())
    paths = dict(walk(f.save.props))
    assert 'SettingRecordPartitionSchemas[0]/PartitionContents/bHasAvailableAudioInputDevices' in paths
    assert isinstance(f.save.get('SeenOnboardingTutorials').value, Raw)


def test_broken_files_raise_settings_errors():
    with pytest.raises(SettingsFileError):
        parse_file(b'ECFD' + b'\0' * 12 + b'not zlib')
    with pytest.raises(SettingsFileError):
        parse_save(b'nope')


# The editor ---------------------------------------------------------------------------------------

def test_schema_has_menu_tabs_and_every_other_setting():
    _, view = view_of(sample_bytes())
    tabs = {t['name']: t for t in view.schema()}
    assert {'Game', 'Audio', 'Accessibility', 'All Settings'} <= set(tabs)
    labels = [s['label'] for g in tabs['Game']['groups'] for s in g['settings']]
    assert 'Toggle Sprint' in labels and 'Auto Open Doors' in labels
    every = [s['key'] for g in tabs['All Settings']['groups'] for s in g['settings']]
    assert 'bAutoClamber' in every
    # Bookkeeping is never offered.
    assert not any(k in every for k in ('bDirty', 'CloudFileState', 'MouseSensitivityDefaultVersion'))


def test_missing_settings_show_game_default_and_present_ones_their_value():
    _, view = view_of(sample_bytes())
    assert view.entry('bToggleSprint', 'x', '')['value'] == 'on'
    assert view.entry('bTargetingToggleable', 'x', '')['value'] == 'off'
    doors = view.entry('bAutoOpenDoorsNonMobile', 'x', '')
    assert doors['value'] == DEFAULT and doors['choices'][0]['label'] == 'Game default (Off)'
    assert view.entry('bAutoClamber', 'x', '')['choices'][0]['label'] == 'Game default'
    assert view.entry('MouseSensitivityX', 'x', '')['kind'] == 'number'
    assert view.entry('HUDScale', 'x', '')['kind'] == 'text'


def test_volumes_are_percents():
    _, view = view_of(sample_bytes())
    volumes = {e['key']: e for e in view._volume_entries()}
    assert volumes['CB_Slider_Music']['value'] == 50
    assert volumes['CB_Slider_Chat']['label'] == 'Voice Chat Volume'


def test_edits_change_only_what_was_edited():
    data = sample_bytes()
    draft, view = view_of(data)
    assert view.apply(RECORD, 'bAutoOpenDoorsNonMobile', 'on') == 'on'
    assert view.apply(RECORD, 'ColorBlindMode', 'EColorBlindMode::Tritanope') == 'EColorBlindMode::Tritanope'
    assert view.apply(VOLUME, 'CB_Slider_Music', 75) == 75
    assert view.apply(RECORD, 'bToggleSprint', DEFAULT) == DEFAULT
    assert view.apply(RECORD, 'HUDScale', '0.8') == '0.8'
    back = parse_file(draft.to_bytes())
    before = {p.name: p for p in parse_file(data).save.props}
    after = {p.name: p for p in back.save.props}
    assert set(after) - set(before) == {'bAutoOpenDoorsNonMobile', 'ColorBlindMode', 'HUDScale'}
    assert set(before) - set(after) == {'bToggleSprint'}
    assert after['bAutoOpenDoorsNonMobile'].value is True
    assert str(after['ColorBlindMode'].type) == 'EnumProperty(EColorBlindMode(/Script/FortniteGame),ByteProperty)'
    assert dict((str(k), v) for k, v in after['BusNameVolumesMap'].value.items)['CB_Slider_Music'] == 0.75
    for name in ('SettingRecordPartitionSchemas', 'SeenOnboardingTutorials', 'MouseSensitivityX', 'ControllerPlatform'):
        assert repr(after[name].value) == repr(before[name].value)
    assert sorted(view.changes()) == ['Auto Open Doors', 'Color Blind Mode', 'HUD Scale', 'Music Volume', 'Toggle Sprint']


def test_bad_values_and_bookkeeping_are_refused():
    _, view = view_of(sample_bytes())
    with pytest.raises(ValueError):
        view.apply(RECORD, 'bToggleSprint', 'maybe')
    with pytest.raises(ValueError):
        view.apply(RECORD, 'ColorBlindMode', 'EColorBlindMode::Purple')
    with pytest.raises(ValueError):
        view.apply(RECORD, 'HUDScale', 'big')
    with pytest.raises(ValueError):
        view.apply(RECORD, 'bDirty', 'on')
    with pytest.raises(ValueError):
        view.apply(RECORD, 'SeenOnboardingTutorials', 'x')


def test_reset_puts_back_the_loaded_value():
    _, view = view_of(sample_bytes())
    view.apply(RECORD, 'bToggleSprint', 'off')
    view.apply(RECORD, 'bToggleSprint', view.original_value(RECORD, 'bToggleSprint'))
    assert view.changes() == []


def test_names_are_readable():
    assert split_words('bAutoOpenDoorsNonMobile') == 'Auto open doors non mobile'
    assert split_words('HUDScale') == 'Hud scale'


# Cloud storage ------------------------------------------------------------------------------------

class Response:
    def __init__(self, status, content=b'', data=None):
        self.status_code, self.content, self._data = status, content, data

    def json(self):
        if self._data is None:
            raise ValueError
        return self._data


class FakeCloud:
    """Epic's cloud storage for one account: list, download and upload."""

    def __init__(self, data):
        self.data = data
        self.calls = []
        self.fail_put = False

    def request(self, method, url, timeout=None, headers=None, data=None):
        self.calls.append((method, url))
        assert headers['Authorization'] == 'Bearer token'
        if method == 'GET' and url.endswith(ACCOUNT):
            return Response(200, data=[{'uniqueFilename': FILE_NAME, 'hash': hashlib.sha1(self.data).hexdigest()}])
        if method == 'GET' and url.endswith('/' + FILE_NAME):
            return Response(200, self.data)
        if method == 'PUT':
            if self.fail_put:
                return Response(403, data={'errorCode': 'errors.com.epicgames.forbidden'})
            self.data = data
            return Response(204)
        return Response(404)


class Auth:
    access_token, account_id = 'token', ACCOUNT

    def ensure_valid(self):
        return True

    def refresh_access_token(self):
        return False


def api(cloud, tmp_path, cache=None):
    return CloudSettingsAPI(Auth(), cloud, backup_dir=str(tmp_path / 'backups'), clock=lambda: 0,
                            cache_path=lambda account: cache)


def test_upload_backs_up_checks_and_updates_the_game_cache(tmp_path):
    cloud = FakeCloud(sample_bytes())
    cache = tmp_path / 'Cloud' / ACCOUNT / FILE_NAME
    cache.parent.mkdir(parents=True)
    cache.write_bytes(cloud.data)
    client = api(cloud, tmp_path, str(cache))
    base = client.download()
    draft, view = view_of(base.data)
    view.apply(RECORD, 'bAutoOpenDoorsNonMobile', 'on')
    new = draft.to_bytes()
    assert 'next time it starts' in client.upload(new, base, lambda: False)
    assert cloud.data == new and cache.read_bytes() == new
    backups = os.listdir(tmp_path / 'backups')
    assert len(backups) == 1 and (tmp_path / 'backups' / backups[0]).read_bytes() == base.data


def test_upload_refused_while_fortnite_runs_or_after_the_game_changed_the_file(tmp_path):
    cloud = FakeCloud(sample_bytes())
    client = api(cloud, tmp_path)
    base = client.download()
    with pytest.raises(CloudSettingsError, match='Close Fortnite'):
        client.upload(b'x', base, lambda: True)
    cloud.data = sample_bytes(wrapped=False)          # the game saved something meanwhile
    with pytest.raises(CloudSettingsError, match='changed since'):
        client.upload(b'x', base, lambda: False)
    assert not any(m == 'PUT' for m, _ in cloud.calls)


def test_rejected_upload_is_reported_without_retrying(tmp_path):
    cloud = FakeCloud(sample_bytes())
    cloud.fail_put = True
    client = api(cloud, tmp_path)
    base = client.download()
    with pytest.raises(CloudSettingsError, match='did not allow'):
        client.upload(sample_bytes(wrapped=False), base, lambda: False)
    assert [m for m, _ in cloud.calls].count('PUT') == 1


# The page's requests ------------------------------------------------------------------------------

@pytest.fixture
def page(tmp_path, monkeypatch):
    cloud = FakeCloud(sample_bytes())
    state = {'signed_in': True, 'running': False}
    monkeypatch.setattr(gamesettings, '_signed_in', lambda: state['signed_in'])
    monkeypatch.setattr(gamesettings, '_auth', lambda: Auth())
    monkeypatch.setattr(gamesettings, '_api', lambda: api(cloud, tmp_path))
    monkeypatch.setattr(gamesettings, '_game_running', lambda: state['running'])
    monkeypatch.setattr(gamesettings, '_session', None)
    return cloud, state


def test_signed_out_page_asks_to_sign_in(page):
    _, state = page
    state['signed_in'] = False
    result = gamesettings.gamesettings_schema({})
    assert result['login'] and result['tabs'] == []


def test_edit_then_save_to_fortnite(page):
    cloud, state = page
    schema = gamesettings.gamesettings_schema({})
    assert schema['status'] == 'No unsaved changes.'
    assert [a['id'] for a in schema['actions']] == ['upload', 'discard', 'reload', 'restore']
    result = gamesettings.gamesettings_set({'section': RECORD, 'key': 'bAutoOpenDoorsNonMobile', 'value': 'on'})
    assert result == {'value': 'on', 'status': '1 unsaved change: Auto Open Doors.'}
    state['running'] = True
    assert 'Close Fortnite' in gamesettings.gamesettings_action({'id': 'upload'})['message']
    state['running'] = False
    done = gamesettings.gamesettings_action({'id': 'upload'})
    assert done['reload'] and 'next time it starts' in done['message']
    assert parse_file(cloud.data).save.get('bAutoOpenDoorsNonMobile').value is True
    assert gamesettings.gamesettings_schema({})['status'] == 'No unsaved changes.'
    restored = gamesettings.gamesettings_action({'id': 'restore'})
    assert restored['message'].startswith('Restored') and cloud.data == sample_bytes()


def test_discard_and_reset(page):
    gamesettings.gamesettings_schema({})
    gamesettings.gamesettings_set({'section': VOLUME, 'key': 'CB_Slider_Music', 'value': 10})
    reset = gamesettings.gamesettings_reset({'section': VOLUME, 'key': 'CB_Slider_Music', 'label': 'Music Volume'})
    assert reset['value'] == 50 and reset['status'] == 'No unsaved changes.'
    gamesettings.gamesettings_set({'section': RECORD, 'key': 'bToggleSprint', 'value': 'off'})
    assert gamesettings.gamesettings_action({'id': 'discard'})['message'] == 'Discarded your changes.'
    assert gamesettings.gamesettings_action({'id': 'upload'})['message'] == 'There are no changes to save.'
