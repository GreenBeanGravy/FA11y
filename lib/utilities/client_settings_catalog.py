"""Fortnite's own settings (ClientSettings.Sav) as the settings editor shows them.

Settings come from two places:

* A short list of well-known settings, grouped the way Fortnite's settings menu groups them,
  with the names the menu uses.
* Every other editable setting the game defines (lib/data/client_settings_schema_4230.json,
  read from the game's class layout), under All Settings with a name made from the
  property name.

Fortnite only saves settings that differ from its defaults, so a setting can be missing from
the file. Missing on/off settings and choices then show as "Game default", and missing numbers
as an empty box. Choosing "Game default", or clearing the box, takes the setting out of the
file again so the game uses its default.

Volumes live in BusNameVolumesMap (one entry per slider) and are shown as percents. Keyboard
bindings and mouse sensitivity are described in client_settings_binds.
"""
from __future__ import annotations

import json
import math
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from lib.utilities import client_settings_binds as binds
from lib.utilities import client_settings_gamepad as pad
from lib.utilities import client_settings_turning as turning
from lib.utilities.client_settings import FStr, MapValue, Raw, Save, TypeName

SCHEMA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'client_settings_schema_4230.json')
RECORD, VOLUME = 'record', 'volume'
DEFAULT = 'default'
ENUM_PACKAGE = '/Script/FortniteGame'
NUMBER_TYPES = {'IntProperty': True, 'FloatProperty': False, 'DoubleProperty': False}
AUTOMATIC_HEADING = 'Automatic Actions (Not in Fortnite\'s PC Menu)'

# (tab, group, property, label, description). The labels are the names Fortnite's settings
# menu uses; descriptions say what the setting does.
CURATED: List[Tuple[str, str, str, str, str]] = [
    ('Game', 'Movement', 'bToggleSprint', 'Toggle Sprint',
     'Pressing sprint once keeps you sprinting until you press it again.'),
    ('Game', 'Movement', 'bAutoOpenDoorsNonMobile', 'Auto Open Doors',
     'Doors open by themselves when you walk into them.'),
    # Fortnite lists these under its touch controls only, but on PC the game reads them too and
    # Epic switches automatic actions on from its server.
    ('Game', AUTOMATIC_HEADING, 'bAutoInteractContainers', 'Auto Open Containers',
     'Chests, ammo boxes and other containers open by themselves when you come near them, '
     'unless you are sprinting.'),
    ('Game', AUTOMATIC_HEADING, 'bAutoInteractRevives', 'Auto Revive Teammate',
     'Standing near a downed teammate starts reviving them.'),
    ('Game', AUTOMATIC_HEADING, 'bAutoInteractZiplines', 'Auto Use Ziplines',
     'Moving onto a zipline or ascender rides it.'),
    ('Game', AUTOMATIC_HEADING, 'bAutoInteractConsumables', 'Auto Consume Forageable Items',
     'You eat apples, mushrooms and other forageables you look at.'),
    ('Game', AUTOMATIC_HEADING, 'bAutoInteractSpawnMachines', 'Auto Use Reboot Vans',
     'You use a reboot van you look at while you carry a reboot card.'),
    ('Game', 'Camera', 'CameraResetAxes', 'Reset Camera Axes',
     'What Reset Camera puts back: Pitch only levels your view, Yaw only turns you to face the way '
     'your character faces, Both does both.'),
    ('Game', 'Camera', 'CameraResetTime', 'Reset Camera Time',
     'How long, in seconds, Reset Camera takes to move the camera back.'),
    ('Game', 'Camera', 'bAutoCenterCamera', 'Auto Center Camera',
     'The camera levels itself while you move. Epic keeps this switched off on PC, so it does '
     'nothing there for now.'),
    ('Game', 'Camera', 'ThirdPersonAutoFollowMode', 'Camera Follow',
     'Whether the camera swings round behind your character as you move: Off, Auto, or Lazy (slowly).'),
    ('Game', 'Camera', 'bMovingTurnsCamera', 'Moving Turns Camera',
     'Moving sideways turns the camera with you. Epic keeps this switched off on PC, so it does '
     'nothing there for now.'),
    ('Game', 'Combat', 'bTargetingToggleable', 'Toggle Targeting',
     'Pressing aim once keeps you aiming down sights until you press it again.'),
    ('Game', 'Combat', 'bAutoPickupWeaponsConsolePC', 'Auto Pickup Weapons',
     'Weapons you walk over are picked up when you have a free slot.'),
    ('Game', 'Combat', 'bAutoSortConsumablesToRight', 'Auto Sort Consumables to Right',
     'Healing items and other consumables move to the right end of your inventory.'),
    ('Game', 'Combat', 'bUseHoldToSwapPickup', 'Hold to Swap Pickup',
     'Holding interact swaps the item you look at with the one in your hand.'),
    ('Game', 'Combat', 'bAutoEquipBetterItems', 'Auto Equip Better Items',
     'A better version of the item in your hand is equipped as you pick it up.'),
    ('Game', 'Building', 'bTurboBuild', 'Turbo Building',
     'Holding the build button keeps placing pieces.'),
    ('Game', 'Building', 'bAutoChangeMaterial', 'Auto Material Change',
     'Building switches material when the one you use runs out.'),
    ('Game', 'Building', 'bDisablePreEditsWhenPlacingBuilding', 'Disable Pre-Edit Option',
     'Pieces are placed without the edit you had chosen beforehand.'),
    ('Game', 'Building', 'bEditConfirmOnReleaseEnabled', 'Confirm Edit on Release',
     'Letting go of the edit button confirms the edit.'),
    ('Game', 'Building', 'EditButtonHoldTime', 'Edit Hold Time',
     'How long, in seconds, you hold the edit button to start editing.'),
    ('Mouse and Keyboard', 'Sensitivity', 'BuildingMultiplier', 'Building Mode Sensitivity Multiplier',
     'Mouse sensitivity in build mode, as a multiplier of the normal sensitivity.'),
    ('Mouse and Keyboard', 'Sensitivity', 'EditingMultiplier', 'Edit Mode Sensitivity Multiplier',
     'Mouse sensitivity in edit mode, as a multiplier of the normal sensitivity.'),
    ('Controller', 'Sticks', 'GamepadMoveStickDeadZone', 'Left Stick Deadzone',
     'How far the left stick moves before your character does, from 0 to 1.'),
    ('Controller', 'Sticks', 'GamepadLookStickDeadZone', 'Right Stick Deadzone',
     'How far the right stick moves before the camera does, from 0 to 1.'),
    ('Controller', 'Flick Stick', 'bFlickStickEnabled', 'Flick Stick',
     'The right stick turns you straight to the direction you push it: right turns you a quarter turn '
     'right, down turns you around. Turning the stick round while held then turns you smoothly.'),
    ('Controller', 'Flick Stick', 'FlickTime', 'Flick Time',
     'How long, in seconds, a flick takes to turn you.'),
    ('Controller', 'Flick Stick', 'FlickStickWindingSpeed', 'Flick Stick Rotation Speed',
     'How fast turning the held stick round turns you.'),
    ('Controller', 'Flick Stick', 'FlickStickSmoothingThreshold', 'Flick Stick Smoothing',
     'Small stick movements below this are smoothed out.'),
    ('Controller', 'Flick Stick', 'FlickForwardDeadZone', 'Flick Forward Deadzone',
     'How far around straight up the stick counts as straight ahead (no turn).'),
    ('Controller', 'Flick Stick', 'FlickStickDeadZoneFactor', 'Flick Stick Deadzone',
     'How far the stick moves before it starts a flick.'),
    ('Controller', 'Aim', 'bAimAssistEnabled', 'Aim Assist',
     'The game helps keep your aim on targets while you use a controller.'),
    ('Controller', 'Feedback', 'bForceFeedbackEnabled', 'Vibration',
     'The controller vibrates.'),
    ('Audio', 'Sound', 'AllowAudioInBackground', 'Play Sound in Background',
     'Whether you hear the game while another window is in front.'),
    ('Audio', 'Voice Chat', 'VoiceChatSetting', 'Voice Chat',
     'Who you can talk to with voice chat.'),
    ('Audio', 'Voice Chat', 'VoiceChatMethodNoMute', 'Voice Chat Method',
     'Whether your microphone is always on or you push a key to talk.'),
    ('Accessibility', 'Sound', 'bVisualizeAudioSources', 'Visualize Sound Effects',
     'Shows on screen where sounds such as footsteps and gunfire come from. Depending on Epic\'s '
     'server settings, turning it on can also stop game sounds panning, so you no longer hear '
     'which side they come from.'),
    ('Accessibility', 'Subtitles', 'bEnableSubtitles', 'Subtitles',
     'Shows subtitles for speech.'),
    ('Accessibility', 'Subtitles', 'SubtitleTextSize', 'Subtitle Text Size',
     'How big subtitles are.'),
    ('Accessibility', 'Text Chat', 'bEnableTextToSpeech', 'Text to Speech',
     'Reads text chat aloud.'),
    ('Accessibility', 'Text Chat', 'bEnableSpeechToText', 'Speech to Text',
     'Shows other players\' voice chat as text.'),
    ('Accessibility', 'Color', 'ColorBlindMode', 'Color Blind Mode',
     'Changes the game\'s colors for a type of color blindness.'),
    ('Accessibility', 'Color', 'ColorBlindStrength', 'Color Blind Strength',
     'How strongly Color Blind Mode changes colors, from 0 to 10.'),
    ('Game UI', 'HUD', 'HUDScale', 'HUD Scale',
     'How big the on-screen HUD is, as a fraction of its normal size.'),
    ('Game UI', 'HUD', 'bShowQuickbarKeybinds', 'Show Keybinds on Quickbar',
     'Shows the key for each quickbar slot.'),
    ('Game UI', 'Combat', 'HitNumbersMode', 'Damage Numbers',
     'How damage numbers appear when you hit something.'),
    ('Game UI', 'Combat', 'bReticleColorChangeForEnemyEnabled', 'Reticle Changes Color on Enemies',
     'The crosshair changes color while it is over an enemy.'),
    ('Game UI', 'Tutorials', 'bContextTutorialEnabled', 'Context Tutorials',
     'Shows hints about the game as you play.'),
    ('Account and Privacy', 'Privacy', 'bAnonymousMode', 'Hide My Name',
     'Other players see you with a generic name.'),
    ('Account and Privacy', 'Privacy', 'bHideOtherPlayerNames', 'Hide Other Players\' Names',
     'You see other players with generic names.'),
    ('Account and Privacy', 'Replays', 'bReplayRecordingEnabled', 'Record Replays',
     'Saves replays of your Battle Royale matches.'),
    ('Account and Privacy', 'Replays', 'bCreativeModeReplayRecordingEnabled', 'Record Creative Replays',
     'Saves replays of Creative sessions.'),
]

VOLUMES = [
    ('CB_Slider_Main', 'Main Volume'), ('CB_Slider_Music', 'Music Volume'),
    ('CB_Slider_LobbyMusic', 'Music - Lobby Volume'), ('CB_Slider_Pilgrim_Music', 'Music - Festival Volume'),
    ('CB_Slider_SFX', 'Gameplay Volume'), ('CB_Slider_Dialogue', 'Dialogue Volume'),
    ('CB_Slider_Chat', 'Voice Chat Volume'), ('CB_Slider_Cinematics', 'Cinematics Volume'),
    ('CB_Slider_PIP', 'Picture in Picture Volume'),
]
# Defaults seen in Fortnite's own menu (42.40) for settings the file didn't hold, shown as
# "Game default (On)". Settings not listed just say "Game default".
KNOWN_DEFAULTS = {'bToggleSprint': True, 'bAutoOpenDoorsNonMobile': False, 'bVisualizeAudioSources': True,
                  'CameraResetAxes': 'ECameraResetAxes::Pitch'}
# Automatic actions default to off on PC and console (the game's Fort.AutoInteract.Default* switches).
KNOWN_DEFAULTS.update({k: False for k in ('bAutoInteractContainers', 'bAutoInteractRevives', 'bAutoInteractZiplines',
                                          'bAutoInteractConsumables', 'bAutoInteractSpawnMachines')})
TABS = ['Game', 'Mouse and Keyboard', 'Keybinds', 'Controller', 'Controller Binds', 'Audio', 'Accessibility', 'Game UI',
        'Account and Privacy', 'All Settings']
VOLUME_MAP = 'BusNameVolumesMap'
# The game's own bookkeeping, not options: versions, migration flags, what was last seen or
# saved, cached state. All Settings leaves these out so they can't be changed by mistake.
INTERNAL = re.compile(r'(Version|Migrat|^bInitial|^Initial|Seen|^Last|Cache|Dirty|Cloud|Save|Count$|Tutorial|'
                      r'Onboarding|Revision|Modal|Viewed|^bHas|^Has|Notified|Attempt|Watched|Recently|Hash|Pending|'
                      r'Old|Calibration|Platform$|PresetName|ConfigName|Region|Culture|Subscription|Store|Experiment|'
                      r'bDid|Copied|bStW|STW|Survivor|bShouldShow|Dummy|MaxCameraShotPresets|ShotIndex)')


# Settings with their own rows elsewhere (Keybinds, Controller, Controller Binds).
OWN_PAGES = {binds.BINDINGS, pad.USER_OPTIONS, pad.LOCAL_OPTIONS, pad.PAD_BINDINGS, pad.PRESET}


@lru_cache(maxsize=1)
def load_schema() -> dict:
    with open(SCHEMA_FILE, encoding='utf-8') as f:
        return json.load(f)


def split_words(name: str) -> str:
    """'bAutoOpenDoorsNonMobile' -> 'Auto open doors non mobile'."""
    if re.match(r'b[A-Z]', name):
        name = name[1:]
    words = re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', name).replace('_', ' ').split()
    text = ' '.join(words)
    return text[:1].upper() + text[1:].lower() if text else name


def enum_label(value: str) -> str:
    return split_words(value.split('::')[-1])


def _type_name(spec: dict, existing: Optional[TypeName]) -> TypeName:
    """The tag type for a setting that is not in the file yet."""
    if existing is not None:
        return existing
    kind = spec['type']
    if kind == 'EnumProperty':
        return TypeName('EnumProperty', [TypeName(spec['enum'], [TypeName(ENUM_PACKAGE)]),
                                         TypeName(spec.get('inner', 'ByteProperty'))])
    return TypeName(kind)


class SettingsView:
    """The editor over one loaded settings file: what to show, and applying the user's changes."""

    def __init__(self, save: Save, original: Save, controller: bool = False):
        self.save = save
        self.original = original
        self.controller = controller        # show the Controller Binds tab
        schema = load_schema()
        self.specs: Dict[str, dict] = schema['settings']
        self.enums: Dict[str, List[str]] = schema['enums']
        self.curated = {name for _tab, _group, name, _label, _desc in CURATED}

    # Describing ----------------------------------------------------------------------------------

    def schema(self) -> List[dict]:
        tabs: Dict[str, Dict[str, List[dict]]] = {tab: {} for tab in TABS}
        for tab, group, name, label, description in CURATED:
            if name in self.specs:
                tabs[tab].setdefault(group, []).append(self.entry(name, label, description))
        volumes = self._volume_entries()
        if volumes:
            tabs['Audio'] = {'Volume': volumes, **tabs['Audio']}
        sensitivity = binds.sens_entries(self.save)
        if sensitivity:
            mouse = tabs['Mouse and Keyboard']
            tabs['Mouse and Keyboard'] = {'Sensitivity': sensitivity + mouse.pop('Sensitivity', []), **mouse}
        tabs['Keybinds'] = dict(turning.groups(self.save) + binds.bind_groups(self.save))
        tabs['Controller'].update(pad.look_entries(self.save))
        if self.controller:
            tabs['Controller Binds'] = dict(pad.pad_groups(self.save))
        others = sorted((n for n in self.specs if self._listed_in_all(n)),
                        key=lambda n: split_words(n).lower())
        tabs['All Settings']['Every setting'] = [self.entry(n, split_words(n), '') for n in others]
        return [{'name': tab, 'groups': [{'heading': h, 'settings': s} for h, s in groups.items() if s]}
                for tab, groups in tabs.items() if groups]

    def _listed_in_all(self, name: str) -> bool:
        return (name not in self.curated and not INTERNAL.search(name) and name not in binds.SENS_PROPERTIES
                and name not in OWN_PAGES)

    def search_entries(self) -> List[dict]:
        entries = []
        for tab in self.schema():
            for group in tab['groups']:
                for s in group['settings']:
                    entries.append({'id': s['id'], 'label': s['label'], 'tab': tab['name'], 'tab_name': tab['name'],
                                    'map': None, 'description': s['description'],
                                    'hay': f"{s['label']} {s['key']} {s['description']}".lower(),
                                    'text': f"{s['label']}, {tab['name']}"})
        return entries

    def entry(self, name: str, label: str, description: str) -> dict:
        spec = self.specs[name]
        prop = self.save.get(name)
        value = None if prop is None or isinstance(prop.value, Raw) else prop.value
        out: Dict[str, Any] = {'id': f'{RECORD}/{name}', 'section': RECORD, 'key': name, 'label': label,
                               'description': description, 'show_description': bool(description)}
        kind = spec['type']
        if prop is not None and isinstance(prop.value, Raw):
            out.update(kind='text', value='(can\'t be edited here)')
        elif kind == 'BoolProperty':
            known = KNOWN_DEFAULTS.get(name)
            default_label = 'Game default' + ('' if known is None else (' (On)' if known else ' (Off)'))
            out.update(kind='choice', value=DEFAULT if value is None else ('on' if value else 'off'),
                       choices=[{'value': DEFAULT, 'label': default_label}, {'value': 'on', 'label': 'On'},
                                {'value': 'off', 'label': 'Off'}])
        elif kind == 'EnumProperty':
            names = [n for n in self.enums.get(spec['enum'], []) if n not in ('Num', 'Count', 'MAX')]
            known = KNOWN_DEFAULTS.get(name)
            choices = [{'value': DEFAULT, 'label': 'Game default' + (f' ({enum_label(known)})' if known else '')}]
            choices += [{'value': f"{spec['enum']}::{n}", 'label': split_words(n)} for n in names]
            current = str(value) if value is not None else DEFAULT
            if current != DEFAULT and current not in {c['value'] for c in choices}:
                choices.append({'value': current, 'label': enum_label(current)})
            out.update(kind='choice', value=current, choices=choices)
        elif kind in NUMBER_TYPES and value is not None:
            integer = NUMBER_TYPES[kind]
            out.update(kind='number', value=value if integer else round(float(value), 6),
                       min=-1e9, max=1e9, step=1 if integer else 0.01, decimals=0 if integer else 4)
        else:
            out.update(kind='text', value='' if value is None else _number_text(value))
        out['default'] = None
        return out

    def _volume_entries(self) -> List[dict]:
        volumes = self.save.get(VOLUME_MAP)
        if volumes is None or not isinstance(volumes.value, MapValue):
            return []
        values = {str(k): v for k, v in volumes.value.items}
        names = [k for k, _ in VOLUMES if k in values] + sorted(k for k in values if k not in dict(VOLUMES))
        labels = dict(VOLUMES)
        return [{'id': f'{VOLUME}/{k}', 'section': VOLUME, 'key': k, 'label': labels.get(k, split_words(k)),
                 'description': '', 'show_description': False, 'kind': 'number',
                 'value': int(round(float(values[k]) * 100)), 'min': 0, 'max': 100, 'step': 1, 'decimals': 0,
                 'default': None} for k in names if isinstance(values[k], float)]

    def label(self, section: str, key: str) -> str:
        if section == binds.BIND:
            return binds.bind_label(key)
        if section == binds.SENS:
            return binds.sens_label(key)
        if section == pad.LOOK:
            return pad.look_label(key)
        if section == turning.TURN:
            return turning.label(key)
        if section in (pad.PAD_BIND, pad.PAD_PRESET):
            return pad.pad_entry_label(self.save, section, key)
        if section == VOLUME:
            return dict(VOLUMES).get(key, split_words(key))
        for _tab, _group, name, label, _desc in CURATED:
            if name == key:
                return label
        return split_words(key)

    # Changing ------------------------------------------------------------------------------------

    def apply(self, section: str, key: str, value: Any, save: Optional[Save] = None) -> Any:
        """Set one setting from what its control holds. Returns what the control should show."""
        save = save or self.save
        if section == VOLUME:
            return self._apply_volume(save, key, value)
        if section == binds.BIND:
            return binds.apply_bind(save, key, value)
        if section == binds.SENS:
            return binds.apply_sens(save, key, value)
        if section == pad.LOOK:
            return pad.apply_look(save, key, value)
        if section == turning.TURN:
            return turning.apply(save, key, value)
        if section == pad.PAD_BIND:
            return pad.apply_pad_bind(save, key, value)[0]
        if section == pad.PAD_PRESET:
            return pad.apply_preset(save, value)
        if section != RECORD or key not in self.specs or (key not in self.curated and INTERNAL.search(key)):
            raise ValueError('Unknown setting.')
        spec = self.specs[key]
        prop = save.get(key)
        if prop is not None and isinstance(prop.value, Raw):
            raise ValueError('This setting can\'t be edited here.')
        kind = spec['type']
        text = '' if value is None else str(value).strip()
        if text in ('', DEFAULT):
            save.remove(key)
            return DEFAULT if kind in ('BoolProperty', 'EnumProperty') else ''
        if kind == 'BoolProperty':
            if text not in ('on', 'off'):
                raise ValueError('Choose Game default, On or Off.')
            save.set(key, _type_name(spec, prop.type if prop else None), text == 'on')
            return text
        if kind == 'EnumProperty':
            allowed = {f"{spec['enum']}::{n}" for n in self.enums.get(spec['enum'], [])}
            if prop is not None:
                allowed.add(str(prop.value))
            if text not in allowed:
                raise ValueError('That isn\'t one of the choices.')
            save.set(key, _type_name(spec, prop.type if prop else None), FStr(text, False))
            return text
        if kind in NUMBER_TYPES:
            try:
                number = float(text)
            except ValueError:
                raise ValueError('Enter a number.') from None
            if not math.isfinite(number):
                raise ValueError('Enter a number.')
            if NUMBER_TYPES[kind]:
                if not number.is_integer() or abs(number) >= 2 ** 31:
                    raise ValueError('Enter a whole number.')
                number = int(number)
            save.set(key, _type_name(spec, prop.type if prop else None), number)
            # A text box (a setting that wasn't in the file) gets text back; a number box a number.
            return _number_text(number) if isinstance(value, str) else number
        if kind in ('StrProperty', 'NameProperty'):
            save.set(key, _type_name(spec, prop.type if prop else None),
                     FStr(text, getattr(prop.value, 'wide', False) if prop else False))
            return text
        raise ValueError('This setting can\'t be edited here.')

    def _apply_volume(self, save: Save, key: str, value: Any) -> int:
        volumes = save.get(VOLUME_MAP)
        if volumes is None or not isinstance(volumes.value, MapValue):
            raise ValueError('Unknown setting.')
        try:
            percent = max(0, min(int(round(float(value))), 100))
        except (TypeError, ValueError):
            raise ValueError('Enter a number from 0 to 100.') from None
        for i, (k, v) in enumerate(volumes.value.items):
            if str(k) == key:
                volumes.value.items[i] = (k, percent / 100.0)
                return percent
        raise ValueError('Unknown setting.')

    def original_value(self, section: str, key: str) -> Any:
        """What the setting's control showed when the file was loaded."""
        view = SettingsView(self.original, self.original)
        if section == binds.BIND:
            action, scale, slot = binds.parse_bind_id(key)
            return binds.current_key(self.original, action, scale, slot)
        if section == binds.SENS:
            return binds.sens_value(self.original, key)
        if section == pad.LOOK:
            return pad.look_values(self.original)[key]
        if section == turning.TURN:
            return turning.values(self.original)[key]
        if section == pad.PAD_BIND:
            return pad.pad_values(self.original).get(f'{pad.PAD_BIND}/{key}')
        if section == pad.PAD_PRESET:
            return pad.preset(self.original)
        if section == VOLUME:
            for entry in view._volume_entries():
                if entry['key'] == key:
                    return entry['value']
            raise ValueError('Unknown setting.')
        return view.entry(key, key, '')['value']

    def changes(self) -> List[str]:
        """Labels of the settings that differ from the file as loaded."""
        old, new = SettingsView(self.original, self.original), self
        changed = []
        for name in self.specs:
            if name in binds.SENS_PROPERTIES or name in OWN_PAGES or (name not in self.curated
                                                                       and INTERNAL.search(name)):
                continue
            if old.entry(name, name, '')['value'] != new.entry(name, name, '')['value']:
                changed.append(self.label(RECORD, name))
        for entry in binds.sens_entries(self.save):
            if binds.sens_value(self.original, entry['key']) != entry['value']:
                changed.append(entry['label'])
        old_binds = binds.bind_values(self.original)
        for key, value in binds.bind_values(self.save).items():
            if old_binds.get(key) != value:
                changed.append(binds.bind_label(key))
        old_turn = turning.values(self.original)
        for key, value in turning.values(self.save).items():
            if old_turn[key] != value:
                changed.append(turning.label(key))
        old_look = pad.look_values(self.original)
        for key, value in pad.look_values(self.save).items():
            if old_look[key] != value:
                changed.append(pad.look_label(key))
        old_pad = pad.pad_values(self.original)
        for entry_id, value in pad.pad_values(self.save).items():
            if old_pad.get(entry_id) != value:
                section, _, key = entry_id.partition('/')
                changed.append(pad.pad_entry_label(self.save, section, key))
        old_volumes = {e['key']: e['value'] for e in old._volume_entries()}
        for entry in new._volume_entries():
            if old_volumes.get(entry['key']) != entry['value']:
                changed.append(entry['label'])
        return changed


def _number_text(value) -> str:
    if isinstance(value, float):
        return f'{value:.6f}'.rstrip('0').rstrip('.') or '0'
    return str(value)
