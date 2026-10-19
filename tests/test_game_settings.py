"""The Fortnite Settings page: reading and writing ClientSettings.Sav, the editor's view of it,
uploading to Epic cloud storage, and the page's requests."""
import hashlib
import os
import re
import zlib

import pytest

from lib.shell.handlers import gamesettings
from lib.utilities.client_settings import Raw, SettingsFileError, parse_file, parse_save, walk
from lib.utilities import client_settings_binds as binds
from lib.utilities import client_settings_gamepad as pad
from lib.utilities import client_settings_turning as turning
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


def test_keybinds_tab_starts_with_camera_keys():
    _, view = view_of(sample_bytes())
    tab = next(t for t in view.schema() if t['name'] == 'Keybinds')
    assert tab['groups'][0]['heading'] == 'Camera'
    camera = [s['label'] for s in tab['groups'][0]['settings']]
    assert camera[:4] == ['Turn Left', 'Turn Right', 'Look Up', 'Look Down']        # one key each
    assert camera[-4:] == ['Turn Speed', 'Look Up and Down Speed', 'Reset Camera', 'Reset Camera, second key']
    rows = {s['label']: s for g in tab['groups'] for s in g['settings']}
    assert rows['Move Forward']['value'] == 'W' and rows['Move Backward, second key']['value'] == 'Down'
    assert rows['Reset Camera']['value'] == 'None' and rows['Reset Camera']['show_description']
    assert (rows['Reload']['kind'], rows['Reload']['capture'], rows['Reload']['display']) == ('keybind', 'key', 'R')
    assert rows['Reload, second key']['display'] == 'Not bound'
    descriptions = ' '.join(s['description'] for t in view.schema() for g in t['groups'] for s in g['settings'])
    assert 'menu' not in descriptions.lower()


def test_choices_use_the_menu_names():
    _, view = view_of(sample_bytes())
    rows = {s['key']: s for t in view.schema() for g in t['groups'] for s in g['settings']}
    assert [c['label'] for c in rows['BuildingTweakZone']['choices']] == [
        'Game default', 'Off', 'Edit mode', 'Build mode', 'Build or edit']
    combat = [c['label'] for c in rows['CombatTweakZone']['choices']]
    assert combat[1:5] == ['Off', 'Scope', 'Scope or aiming', 'Always on'] and 'Count' not in combat
    assert 'Invalid' not in [c['label'] for c in rows['HitNumbersMode']['choices']]


def test_binding_a_key_changes_both_lists_and_reports_clashes():
    draft, view = view_of(sample_bytes())
    assert view.apply('bind', 'GamepadResetCamera@1#1', 'K') == 'K'
    assert view.apply('bind', 'MoveForward@-1#2', 'NumPadTwo') == 'NumPadTwo'
    assert view.changes() == ['Reset Camera', 'Move Backward, second key']
    data = draft.to_bytes()
    again = parse_file(data)
    assert again.to_bytes() == data
    for sub, value in again.save.get('UserBindingsPerSubGame').value.items:
        keys = {(str(m.props[0].value), m.props[5].value): str(m.props[3].value.props[0].value)
                for m in value.props[0].value.items}
        assert keys[('GamepadResetCamera', 1.0)] == 'K', sub
    view.apply('bind', 'Reload@1#2', 'E')
    assert binds.conflicts(draft.save, 'Reload@1#2') == ['Interact']   # both in Combat
    view.apply('bind', 'GamepadResetCamera@1#2', 'W')
    assert binds.conflicts(draft.save, 'GamepadResetCamera@1#2') == []  # Move Forward is in another section
    view.apply('bind', 'Reload@1#2', 'R')
    assert binds.conflicts(draft.save, 'Reload@1#2') == ['Reload']
    with pytest.raises(ValueError):
        view.apply('bind', 'Reload@1#1', 'NotAKey')
    with pytest.raises(ValueError):
        view.apply('bind', 'NoSuchAction@1#1', 'K')
    assert view.original_value('bind', 'GamepadResetCamera@1#1') == 'None'


def test_sensitivity_uses_the_menu_percent_and_goes_below_its_lowest_step():
    draft, view = view_of(sample_bytes())
    rows = {s['label']: s for t in view.schema() if t['name'] == 'Mouse and Keyboard'
            for g in t['groups'] for s in g['settings']}
    assert rows['X-Axis Sensitivity']['value'] == 1.0 and rows['Targeting Sensitivity']['value'] == 87.0
    assert 'Y-Axis Sensitivity' not in rows                         # not in this file
    assert view.apply('sens', 'x', '0.5') == 0.5
    assert draft.save.get('MouseSensitivityX').value == pytest.approx(0.00125)
    assert draft.save.get('UpgradedMouseSensitivityX').value == pytest.approx(0.00125)
    assert view.changes() == ['X-Axis Sensitivity']
    for bad in ('0', '-1', 'fast', '5000'):
        with pytest.raises(ValueError):
            view.apply('sens', 'x', bad)
    all_settings = {s['key'] for t in view.schema() if t['name'] == 'All Settings'
                    for g in t['groups'] for s in g['settings']}
    assert not {'MouseSensitivityX', 'UpgradedMouseSensitivityX', 'UserBindingsPerSubGame'} & all_settings


def test_set_warns_when_a_key_is_already_used(page):
    gamesettings.gamesettings_schema({})
    result = gamesettings.gamesettings_set({'section': 'bind', 'key': 'Reload@1#2', 'value': 'R'})
    assert result['message'] == 'Also used by Reload.' and result['display'] == 'R'
    assert 'message' not in gamesettings.gamesettings_set({'section': 'bind', 'key': 'Reload@1#2', 'value': 'T'})
    reset = gamesettings.gamesettings_reset({'section': 'bind', 'key': 'Reload@1#2', 'label': 'Reload, second key'})
    assert (reset['value'], reset['display']) == ('None', 'Not bound')
    pad_row = gamesettings.gamesettings_set({'section': 'padbind', 'key': 'Fire@1#1', 'value': 'Gamepad_DPad_Up'})
    assert pad_row['display'] == 'D-pad Up'


def test_force_walk_and_jog_are_left_off():
    _, view = view_of(sample_bytes())
    keys = {s['key'] for t in view.schema() if t['name'] == 'Keybinds' for g in t['groups'] for s in g['settings']}
    assert not any(k.startswith(('ForceWalk', 'ForceJog')) for k in keys)


def test_controller_binds_tab_only_with_a_controller():
    draft, original = parse_file(sample_bytes()), parse_file(sample_bytes())
    assert 'Controller Binds' not in [t['name'] for t in SettingsView(draft.save, original.save).schema()]
    view = SettingsView(draft.save, original.save, controller=True)
    tab = next(t for t in view.schema() if t['name'] == 'Controller Binds')
    rows = {s['label']: s for g in tab['groups'] for s in g['settings']}
    assert rows['Controller Preset']['value'] == 'ConfigF_Athena'
    assert [c['label'] for c in rows['Controller Preset']['choices']] == [
        'Old School', 'Quick Builder', 'Combat Pro', 'Builder Pro', 'Custom']
    assert rows['Jump']['value'] == 'Gamepad_FaceButton_Bottom'
    assert [g['heading'] for g in tab['groups']][:2] == ['Camera', 'Preset']
    assert (rows['Jump']['kind'], rows['Jump']['capture'], rows['Jump']['display']) == ('keybind', 'controller', 'A (Cross)')
    assert rows['Reset Camera']['display'] == 'Not bound'


def test_changing_a_controller_button_switches_to_the_custom_preset(page):
    gamesettings.gamesettings_schema({})
    gamesettings._session.view.controller = True
    result = gamesettings.gamesettings_set({'section': 'padbind', 'key': 'GamepadResetCamera@1#1',
                                            'value': 'Gamepad_FaceButton_Bottom'})
    assert result['message'] == ('Controller preset switched to Custom, so this button counts. '
                                 'Also used by Jump.')
    assert result['updates'] == [{'id': 'padpreset/InputPresetNameForAthena', 'value': 'ConfigCustom_Athena'}]
    save = gamesettings._session.draft.save
    assert pad.preset(save) == pad.CUSTOM_PRESET
    assert set(gamesettings._session.view.changes()) == {'Controller Preset', 'Reset Camera'}
    again = gamesettings.gamesettings_set({'section': 'padbind', 'key': 'GamepadResetCamera@1#1',
                                           'value': 'Gamepad_DPad_Left'})
    assert 'message' not in again and 'updates' not in again
    with pytest.raises(ValueError):
        gamesettings.gamesettings_set({'section': 'padbind', 'key': 'Fire@1#1', 'value': 'K'})


def test_controller_look_options_are_added_and_removed():
    draft, view = view_of(sample_bytes())
    rows = {s['label']: s for t in view.schema() if t['name'] == 'Controller'
            for g in t['groups'] for s in g['settings']}
    assert rows['Use Advanced Options']['value'] == 'default' and rows['Turning Horizontal Boost']['value'] == ''
    assert view.apply('look', 'Basic.bUseAdvancedOptions', 'on') == 'on'
    assert view.apply('look', 'Advanced.LookHorizontalBoostSpeed', '250') == '250'   # past the menu's 100
    assert view.apply('look', 'Basic.LookSensitivityPreset', 'EFortGamepadSensitivity::Insane') ==         'EFortGamepadSensitivity::Insane'
    data = draft.to_bytes()
    reread = parse_file(data)
    assert reread.to_bytes() == data
    advanced = next(p for p in reread.save.get('GamepadUserOptions').value.props if str(p.name) == 'Advanced')
    assert [(str(p.name), str(p.type), p.value) for p in advanced.value.props] ==         [('LookHorizontalBoostSpeed', 'UInt32Property', 250)]
    for bad in ('-1', '2.5', '99999'):
        with pytest.raises(ValueError):
            view.apply('look', 'Advanced.LookHorizontalBoostSpeed', bad)
    for key in ('Basic.bUseAdvancedOptions', 'Advanced.LookHorizontalBoostSpeed', 'Basic.LookSensitivityPreset'):
        view.apply('look', key, 'default')
    assert draft.save.get('GamepadUserOptions') is None and view.changes() == []


def test_camera_and_flick_stick_rows():
    _, view = view_of(sample_bytes())
    tabs = {t['name']: t for t in view.schema()}
    camera = next(g for g in tabs['Game']['groups'] if g['heading'] == 'Camera')
    axes = next(s for s in camera['settings'] if s['key'] == 'CameraResetAxes')
    assert [c['label'] for c in axes['choices']] == ['Game default (Pitch)', 'Pitch', 'Yaw', 'Both']
    flick = next(g for g in tabs['Controller']['groups'] if g['heading'] == 'Flick Stick')
    assert flick['settings'][0]['label'] == 'Flick Stick'


def test_tweak_zone_rows_and_no_aim_assist_strength():
    draft, view = view_of(sample_bytes())
    tabs = {t['name']: t for t in view.schema()}
    tweak = next(g for g in tabs['Controller']['groups'] if g['heading'] == 'Tweak Zone')
    rows = {s['key']: s for s in tweak['settings']}
    assert list(rows) == ['CombatTweakZone', 'BuildingTweakZone', 'TweakZoneOverlap', 'TweakZoneScale']
    combat = [c['value'] for c in rows['CombatTweakZone']['choices']]
    assert 'EActiveCombatMode::HipOnly' in combat and 'EActiveCombatMode::NotScope' in combat
    view.apply('record', 'TweakZoneScale', '3')
    assert parse_file(draft.to_bytes()).save.get('TweakZoneScale').value == 3.0
    assert 'Tweak Sensitivity' in view.changes()
    keys = [s['key'] for t in view.schema() for g in t['groups'] for s in g['settings']]
    assert not [k for k in keys if 'AimAssist' in k and 'Strength' in k]
    for k in ('AimAssistStrength', 'AimAssistSlowStrength', 'AimAssistPullStrength'):
        with pytest.raises(ValueError):
            view.apply('look', f'Advanced.{k}', '100')


def test_turn_keys_add_look_axis_entries_and_take_them_out_again():
    draft, view = view_of(sample_bytes())
    rows = {s['label']: s for t in view.schema() if t['name'] == 'Keybinds' for g in t['groups']
            for s in g['settings']}
    assert rows['Turn Left']['value'] == 'None' and rows['Turn Speed']['value'] == ''
    with pytest.raises(ValueError):
        view.apply('turn', 'speed:Turn', '50')                 # no turn key yet
    assert view.apply('turn', 'left#1', 'NumPadFour') == 'NumPadFour'
    assert view.apply('turn', 'up#1', 'NumPadEight') == 'NumPadEight'
    assert view.apply('turn', 'speed:Turn', '30') == '30'
    view.apply('turn', 'right#1', 'NumPadSix')                 # a new direction keeps the speed
    data = draft.to_bytes()
    reread = parse_file(data)
    assert reread.to_bytes() == data
    for sub, value in reread.save.get('UserBindingsPerSubGame').value.items:
        axes = sorted((str(m.props[0].value), round(m.props[5].value, 3), str(m.props[3].value.props[0].value))
                      for m in value.props[0].value.items if str(m.props[0].value) in ('Turn', 'LookUp'))
        assert axes == [('LookUp', -1.0, 'NumPadEight'), ('Turn', -0.3, 'NumPadFour'),
                        ('Turn', 0.3, 'NumPadSix')], sub
    assert 'Turn Speed' in view.changes() and 'Look Up' in view.changes()
    view.apply('turn', 'left#1', 'Up')
    assert turning.conflicts(draft.save, 'left#1') == ['Move Forward']    # both in Movement
    assert binds.conflicts(draft.save, 'MoveForward@1#2') == ['Turn Left']
    view.apply('turn', 'left#1', 'NumPadFour')
    with pytest.raises(ValueError):
        view.apply('turn', 'left#2', 'K')
    for row in ('left#1', 'right#1', 'up#1'):
        view.apply('turn', row, 'None')
    assert draft.to_bytes() == sample_bytes() and view.changes() == []


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
    monkeypatch.setattr(gamesettings, '_controller_connected', lambda: False)
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
    assert [a['id'] for a in schema['actions']] == ['upload', 'discard', 'reload', 'restore', 'presets',
                                                    'import_preset', 'export_preset']
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


def test_every_key_the_window_can_capture_is_one_fortnite_accepts():
    """The window names captured keys and controller buttons itself (FortniteKeys.cs, Gamepad.cs); the core
    refuses names it doesn't know, so every one must be in its lists."""
    core = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ui', 'src', 'FA11y.UI', 'Core')
    keys_cs = open(os.path.join(core, 'FortniteKeys.cs'), encoding='utf-8').read()
    names = set(re.findall(r'"([A-Za-z][A-Za-z0-9]+)"', keys_cs)) - {'NumPad', 'F'}
    names |= {f'F{i}' for i in range(1, 13)} | {c for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'}
    names |= {'NumPad' + d for d in ('Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine')}
    assert names - set(binds.KEY_LABELS) == set()
    pad_cs = open(os.path.join(core, 'Gamepad.cs'), encoding='utf-8').read()
    buttons = set(re.findall(r'"(Gamepad_[A-Za-z_]+)"', pad_cs))
    assert len(buttons) == 16 and buttons - set(pad.PAD_KEY_LABELS) == set()
