"""Presets on the Fortnite settings page: the .preset file, what one would change, applying it to the
draft, and exporting, importing and deleting the user's presets."""
import json

import pytest

from lib.shell.handlers import gamesettings
from lib.utilities import client_settings_presets as presets
from lib.utilities.client_settings import parse_file
from lib.utilities.client_settings_catalog import SettingsView
from tests.fixtures.client_settings_sample import sample_bytes
from tests.test_game_settings import page  # noqa: F401  (the fixture)

ROWS = [
    {'tab': 'Game', 'label': 'Auto Open Doors', 'section': 'record', 'key': 'bAutoOpenDoorsNonMobile', 'value': 'on'},
    {'tab': 'Keybinds', 'label': 'Turn Left', 'section': 'turn', 'key': 'left#1', 'value': 'Left'},
    {'tab': 'Keybinds', 'label': 'Turn Speed', 'section': 'turn', 'key': 'speed:Turn', 'value': '50'},
    {'tab': 'Controller Binds', 'label': 'Reset Camera', 'section': 'padbind', 'key': 'GamepadResetCamera@1#1',
     'value': 'Gamepad_DPad_Down'},
    {'tab': 'Keybinds', 'label': 'Fly', 'section': 'bind', 'key': 'Fly@1#1', 'value': 'K'},
    {'tab': 'All Settings', 'label': 'Last seen', 'section': 'record', 'key': 'LastSeenVersion', 'value': '1'},
]


@pytest.fixture
def folders(tmp_path, monkeypatch):
    monkeypatch.setattr(presets, 'USER_DIR', str(tmp_path / 'mine'))
    monkeypatch.setattr(presets, 'BUILTIN_DIR', str(tmp_path / 'fa11y'))
    return tmp_path


def test_preset_files_round_trip_and_other_files_are_refused():
    preset = presets.Preset('Turn keys', ROWS, 'For turning with arrows.')
    again = presets.parse(presets.to_bytes(preset))
    assert (again.name, again.description, again.settings) == ('Turn keys', 'For turning with arrows.', ROWS)
    good = json.loads(presets.to_bytes(preset))
    for bad in (b'not json', b'[]', json.dumps({**good, 'type': 'other'}).encode(),
                json.dumps({**good, 'name': ''}).encode(),
                json.dumps({**good, 'settings': [{'section': 'script', 'key': 'x', 'value': 1}]}).encode(),
                json.dumps({**good, 'settings': [{'section': 'record', 'key': 'x', 'value': [1]}]}).encode()):
        with pytest.raises(presets.PresetError, match='isn\'t an FA11y preset'):
            presets.parse(bad)
    with pytest.raises(presets.PresetError, match='newer FA11y'):
        presets.parse(json.dumps({**good, 'version': 99}).encode())


def test_preview_says_what_changes_and_leaves_the_draft_alone():
    draft = parse_file(sample_bytes())
    original = parse_file(sample_bytes()).save
    changes, skipped = presets.preview(draft.to_bytes(), original, presets.Preset('Mine', ROWS))
    texts = [c.text() for c in changes]
    assert 'Auto Open Doors (Game): Game default (Off) to On' in texts
    assert 'Turn Left (Keybinds): Not bound to Left Arrow' in texts
    assert 'Turn Speed (Keybinds): Game default to 50' in texts
    assert 'Controller Preset (Controller Binds): Combat Pro to Custom' in texts   # switched by the button
    assert skipped == ['Fly (Keybinds): isn\'t in your settings.', 'Last seen (All Settings): isn\'t in your settings.']
    assert draft.to_bytes() == sample_bytes()


def test_sections_and_changes_make_presets_that_only_set_things():
    draft = parse_file(sample_bytes())
    view = SettingsView(draft.save, parse_file(sample_bytes()).save)
    groups = {g['id']: g['count'] for g in presets.export_groups(view)}
    assert groups['Game/Movement'] == 1 and 'Keybinds/Camera' not in groups      # nothing bound there yet
    view.apply('turn', 'left#1', 'Left')
    rows = presets.rows_from_groups(view, ['Keybinds/Camera', 'Game/Movement'])
    assert [(r['label'], r['value']) for r in rows] == [('Toggle Sprint', 'on'), ('Turn Left', 'Left'),
                                                        ('Turn Speed', '100')]
    view.apply('record', 'bToggleSprint', 'default')
    changed = [(r['label'], r['value']) for r in presets.rows_from_changes(view)]
    assert changed == [('Toggle Sprint', 'default'), ('Turn Left', 'Left'), ('Turn Speed', '100')]


def test_apply_a_preset_to_the_page(page, folders):
    gamesettings.gamesettings_schema({})
    stored = presets.save_user(presets.Preset('Mine', ROWS))
    listed = gamesettings.gamesettings_presets({})['presets']
    assert [(p['name'], p['builtin'], p['count']) for p in listed] == [('Mine', False, len(ROWS))]
    shown = gamesettings.gamesettings_preset_preview({'id': stored.id})
    assert shown['prompt'] == 'Apply Mine? It changes 5 settings: 2 settings in it are skipped.'
    assert shown['lines'][-1] == 'Skipped: Last seen (All Settings): isn\'t in your settings.'
    done = gamesettings.gamesettings_preset_apply({'id': stored.id})
    assert done['message'] == 'Applied Mine: 5 settings changed. Save to Fortnite to keep them.' and done['reload']
    assert done['status'].startswith('5 unsaved changes: ')
    again = gamesettings.gamesettings_preset_apply({'id': stored.id})
    assert again['message'] == 'Nothing changed. Your settings already match Mine.' and not again['reload']
    assert gamesettings.gamesettings_action({'id': 'discard'})['message'] == 'Discarded your changes.'


def test_export_import_and_delete(page, folders):
    gamesettings.gamesettings_schema({})
    gamesettings.gamesettings_set({'section': 'turn', 'key': 'right#1', 'value': 'Right'})
    options = gamesettings.gamesettings_preset_export_options({})
    assert options['changes'] == 2 and {'id': 'Game/Movement', 'label': 'Game: Movement', 'count': 1} in options['groups']
    path = folders / 'shared.preset'
    done = gamesettings.gamesettings_preset_export({'name': 'Turning', 'changes': True, 'path': str(path)})
    assert done['ok'] and done['message'] == f'Saved Turning, with 2 settings, to your presets and to {path}.'
    assert presets.load(str(path)).settings == presets.find(done['id']).settings
    clash = gamesettings.gamesettings_preset_export({'name': 'turning', 'groups': ['Game/Movement']})
    assert clash['exists'] and not clash['ok']
    replaced = gamesettings.gamesettings_preset_export({'name': 'turning', 'groups': ['Game/Movement'], 'replace': True})
    assert replaced['message'] == 'Saved turning to your presets, with 1 setting.'
    assert [p['name'] for p in gamesettings.gamesettings_presets({})['presets']] == ['turning']

    imported = gamesettings.gamesettings_preset_import({'path': str(path)})      # same name, other settings
    assert imported['name'] == 'Turning 2' and imported['imported'] == 'added'
    assert gamesettings.gamesettings_preset_import({'path': str(path)})['imported'] == 'already'
    shown = gamesettings.gamesettings_preset_preview({'id': imported['id'], 'imported': 'added'})
    assert shown['prompt'].startswith('Added Turning 2 to your presets. Your settings already match Turning 2.')
    bad = folders / 'bad.preset'
    bad.write_bytes(b'{"type": "something else"}')
    assert gamesettings.gamesettings_preset_import({'path': str(bad)}) == {
        'ok': False, 'message': 'That file isn\'t an FA11y preset.'}

    assert gamesettings.gamesettings_preset_delete({'id': imported['id']})['message'] == 'Deleted Turning 2.'
    assert [p['name'] for p in gamesettings.gamesettings_presets({})['presets']] == ['turning']
    assert not gamesettings.gamesettings_preset_preview({'id': imported['id']})['ok']


def test_fa11y_presets_come_first_and_cannot_be_deleted(folders):
    (folders / 'fa11y').mkdir()
    (folders / 'fa11y' / 'Basics.preset').write_bytes(presets.to_bytes(presets.Preset('Basics', ROWS[:1])))
    (folders / 'fa11y' / 'Broken.preset').write_bytes(b'nope')
    presets.save_user(presets.Preset('Alpha', ROWS[:1]))
    found = presets.all_presets()
    assert [(p.name, p.builtin) for p in found] == [('Basics', True), ('Alpha', False)]
    with pytest.raises(presets.PresetError):
        presets.delete_user(found[0])


def test_controller_buttons_that_match_leave_the_controller_preset_alone():
    draft = parse_file(sample_bytes())
    view = SettingsView(draft.save, parse_file(sample_bytes()).save)
    rows = presets.rows_from_groups(view, [g['id'] for g in presets.export_groups(view) if g['id'].startswith('Controller Binds')])
    assert any(r['section'] == 'padbind' for r in rows) and rows[0]['section'] == 'padpreset'
    changes, _ = presets.preview(draft.to_bytes(), parse_file(sample_bytes()).save, presets.Preset('Same', rows))
    assert changes == []
    moved = [dict(r, value='Gamepad_DPad_Down') if r['key'] == 'GamepadJump@1#1' else r for r in rows]
    changes, _ = presets.preview(draft.to_bytes(), parse_file(sample_bytes()).save, presets.Preset('Moved', moved))
    assert [c.text() for c in changes] == ['Jump (Controller Binds): A (Cross) to D-pad Down']   # preset stays Combat Pro
