"""Controller settings in Fortnite's settings file, as the settings editor shows them.

* Look sensitivity lives in the struct GamepadUserOptions {Basic, Advanced}: Basic holds the
  preset (Slow ... Insane) and build and edit multipliers, Advanced the speeds the menu's
  Advanced Options show (Look Horizontal Speed, Turning Horizontal Boost and so on, as whole
  percents), turned on by Basic.bUseAdvancedOptions. Like everything in the file, the struct
  only holds what differs from the game's defaults, so it is often missing; it is added when a
  value is set and its entries removed again for Game default.
* Controller bindings are CustomGamepadActionBindings, the same FortActionKeyMapping list the
  keyboard uses with gamepad key names. They are only used with the Custom preset
  (InputPresetNameForAthena = ConfigCustom_Athena), so changing one switches to it.
"""
from __future__ import annotations

import ctypes
import math
from typing import Dict, List, Optional, Tuple

from lib.utilities.client_settings import FStr, Prop, Save, Struct, TypeName
from lib.utilities.client_settings_binds import (UNBOUND, _field, _key_prop, _scale, bind_id, group_heading,
                                                 parse_bind_id)

LOOK, PAD_BIND, PAD_PRESET = 'look', 'padbind', 'padpreset'
USER_OPTIONS = 'GamepadUserOptions'
LOCAL_OPTIONS = 'LocalGamepadUserOptions'
PAD_BINDINGS = 'CustomGamepadActionBindings'
PRESET = 'InputPresetNameForAthena'
CUSTOM_PRESET = 'ConfigCustom_Athena'
FG = '/Script/FortniteGame'
DEFAULT = 'default'

SENSITIVITY_ENUM = 'EFortGamepadSensitivity'
SENSITIVITY_PRESETS = ['Slow', 'SlowPlus', 'SlowPlusPlus', 'Normal', 'NormalPlus', 'NormalPlusPlus', 'Fast',
                       'FastPlus', 'FastPlusPlus', 'Insane']
CURVE_ENUM = 'EFortGamepadLookInputCurve'
UINT_HIGH = 10000          # the menu stops at 100 (or less); larger values are accepted for testing

# (struct, field, label, kind, description). kind: 'bool', 'uint', 'float', or an enum name.
LOOK_OPTIONS: List[Tuple[str, str, str, str, str]] = [
    ('Basic', 'LookSensitivityPreset', 'Look Sensitivity', SENSITIVITY_ENUM,
     'How fast the right stick turns the camera, from Slow to Insane.'),
    ('Basic', 'LookSensitivityPresetAds', 'Look Sensitivity (Targeting)', SENSITIVITY_ENUM,
     'How fast the right stick turns the camera while aiming down sights.'),
    ('Basic', 'LookBuildModeMultiplier', 'Build Mode Sensitivity Multiplier', 'float',
     'Turning speed in build mode, as a multiplier of the normal speed.'),
    ('Basic', 'LookEditModeMultiplier', 'Edit Mode Sensitivity Multiplier', 'float',
     'Turning speed in edit mode, as a multiplier of the normal speed.'),
    ('Basic', 'bUseAdvancedOptions', 'Use Advanced Options', 'bool',
     'Use the speeds below instead of the Look Sensitivity presets. Needed for any of them to count.'),
    ('Advanced', 'LookHorizontalSpeed', 'Look Horizontal Speed', 'uint',
     'Turning speed left and right, in percent. The menu stops at 100; higher values are allowed here.'),
    ('Advanced', 'LookVerticalSpeed', 'Look Vertical Speed', 'uint',
     'Turning speed up and down, in percent.'),
    ('Advanced', 'LookHorizontalSpeedAds', 'Targeting Horizontal Speed', 'uint',
     'Turning speed left and right while aiming down sights, in percent.'),
    ('Advanced', 'LookVerticalSpeedAds', 'Targeting Vertical Speed', 'uint',
     'Turning speed up and down while aiming down sights, in percent.'),
    ('Advanced', 'LookHorizontalBoostSpeed', 'Turning Horizontal Boost', 'uint',
     'Extra speed left and right when the stick is pushed all the way, in percent. Higher values '
     'than the menu allows are accepted here.'),
    ('Advanced', 'LookVerticalBoostSpeed', 'Turning Vertical Boost', 'uint',
     'Extra speed up and down when the stick is pushed all the way, in percent.'),
    ('Advanced', 'LookHorizontalBoostSpeedAds', 'Targeting Horizontal Boost', 'uint',
     'Extra speed left and right while aiming, with the stick all the way, in percent.'),
    ('Advanced', 'LookVerticalBoostSpeedAds', 'Targeting Vertical Boost', 'uint',
     'Extra speed up and down while aiming, with the stick all the way, in percent.'),
    ('Advanced', 'LookBoostAccelerationTime', 'Turning Boost Ramp Time', 'float',
     'How long, in seconds, the boost takes to reach full speed. 0 is instant.'),
    ('Advanced', 'LookBoostAccelerationTimeAds', 'Targeting Boost Ramp Time', 'float',
     'How long, in seconds, the boost takes to reach full speed while aiming.'),
    ('Advanced', 'bInstantBoostWhenBuilding', 'Instant Boost When Building', 'bool',
     'The boost starts at full speed in build mode.'),
    ('Advanced', 'LookEaseTime', 'Look Ease Time', 'float',
     'How long, in seconds, turning takes to speed up when you push the stick.'),
    ('Advanced', 'LookInputCurve', 'Look Input Curve', CURVE_ENUM,
     'Linear turns at a speed in step with the stick; Exponential is slow near the middle.'),
    ('Advanced', 'ScopedSensitivityMultiplier', 'Scope Sensitivity Multiplier', 'float',
     'Turning speed through a scope, as a multiplier.'),
    ('Advanced', 'AimAssistStrength', 'Aim Assist Strength', 'uint',
     'How strongly aim assist helps, in percent.'),
]
ENUM_CHOICES = {SENSITIVITY_ENUM: SENSITIVITY_PRESETS, CURVE_ENUM: ['Linear', 'Exponential']}

# Gamepad key names and how to say them (Xbox name, then PlayStation).
PAD_KEYS: List[Tuple[str, str]] = [
    ('Gamepad_FaceButton_Bottom', 'A (Cross)'), ('Gamepad_FaceButton_Right', 'B (Circle)'),
    ('Gamepad_FaceButton_Left', 'X (Square)'), ('Gamepad_FaceButton_Top', 'Y (Triangle)'),
    ('Gamepad_LeftShoulder', 'Left Bumper (L1)'), ('Gamepad_RightShoulder', 'Right Bumper (R1)'),
    ('Gamepad_LeftTrigger', 'Left Trigger (L2)'), ('Gamepad_RightTrigger', 'Right Trigger (R2)'),
    ('Gamepad_LeftThumbstick', 'Left Stick Click (L3)'), ('Gamepad_RightThumbstick', 'Right Stick Click (R3)'),
    ('Gamepad_DPad_Up', 'D-pad Up'), ('Gamepad_DPad_Down', 'D-pad Down'),
    ('Gamepad_DPad_Left', 'D-pad Left'), ('Gamepad_DPad_Right', 'D-pad Right'),
    ('Gamepad_Special_Left', 'View (Share / Touchpad)'), ('Gamepad_Special_Right', 'Menu (Options)'),
]
PAD_KEY_LABELS = {UNBOUND: 'Not bound', 'Virtual_Accept': 'Accept button', 'Virtual_Back': 'Back button',
                  **dict(PAD_KEYS)}

PAD_LABELS = {
    'GamepadJump': 'Jump', 'Fire': 'Fire', 'Target': 'Aim', 'UseOrReload': 'Reload / Interact',
    'GamepadSprint': 'Sprint', 'CrouchOrRepair': 'Crouch / Repair', 'GamepadResetCamera': 'Reset Camera',
    'GamepadSelectNextWeapon': 'Next Weapon', 'GamepadSelectPreviousWeapon': 'Previous Weapon',
    'GamepadSwitchModeOrEditBuilding': 'Switch Mode / Edit', 'GamepadToggleHarvestWeaponOrAltInteract':
    'Harvesting Tool / Alternate Interact', 'GamepadToggleFullScreenMap': 'Map',
    'GamepadToggleInventory': 'Inventory', 'GamepadEmotePickerOrReplayLastEmoteHold': 'Emote (Tap) / Repeat (Hold)',
    'GamepadSquadQuickChatPicker': 'Squad Comms', 'PlaceMapMarkerInWorld': 'Place Marker',
    'PushToTalk': 'Push to Talk', 'ToggleMapCursor_Gamepad': 'Map Cursor', 'MapZoomIn_Gamepad': 'Map Zoom In',
    'MapZoomOut_Gamepad': 'Map Zoom Out',
}

PRESETS = [('ConfigD_Athena', 'Old School'), ('ConfigE_Athena', 'Quick Builder'), ('ConfigF_Athena', 'Builder Pro'),
           ('ConfigG_Athena', 'Combat Pro'), ('ConfigH_Athena', 'Preset H'), (CUSTOM_PRESET, 'Custom')]


# Look options ------------------------------------------------------------------------------------

def _struct_type(name: str) -> TypeName:
    return TypeName('StructProperty', [TypeName(name, [TypeName(FG)])])


def _field_type(kind: str) -> TypeName:
    if kind == 'bool':
        return TypeName('BoolProperty')
    if kind == 'uint':
        return TypeName('UInt32Property')
    if kind == 'float':
        return TypeName('FloatProperty')
    return TypeName('EnumProperty', [TypeName(kind, [TypeName(FG)]), TypeName('ByteProperty')])


def _spec(key: str):
    for spec in LOOK_OPTIONS:
        if f'{spec[0]}.{spec[1]}' == key:
            return spec
    raise ValueError('Unknown setting.')


def _inner(save: Save, holder: str, part: str) -> Optional[Struct]:
    prop = save.get(holder)
    if prop is None or not isinstance(prop.value, Struct) or not isinstance(prop.value.props, list):
        return None
    sub = next((p for p in prop.value.props if str(p.name) == part), None)
    if sub is None or not isinstance(sub.value, Struct) or not isinstance(sub.value.props, list):
        return None
    return sub.value


def look_value(save: Save, key: str):
    part, name, _label, _kind, _desc = _spec(key)
    inner = _inner(save, USER_OPTIONS, part)
    if inner is None:
        return None
    prop = next((p for p in inner.props if str(p.name) == name), None)
    return None if prop is None else prop.value


def _display(kind: str, value):
    if value is None:
        return DEFAULT if kind not in ('uint', 'float') else ''
    if kind == 'bool':
        return 'on' if value else 'off'
    if kind == 'float':
        return f'{float(value):.4f}'.rstrip('0').rstrip('.') or '0'
    if kind == 'uint':
        return str(int(value))
    return str(value)


def look_entries(save: Save) -> List[Tuple[str, List[dict]]]:
    groups: Dict[str, List[dict]] = {}
    for part, name, label, kind, description in LOOK_OPTIONS:
        key = f'{part}.{name}'
        value = _display(kind, look_value(save, key))
        entry = {'id': f'{LOOK}/{key}', 'section': LOOK, 'key': key, 'label': label, 'description': description,
                 'show_description': True, 'default': None}
        if kind == 'bool':
            entry.update(kind='choice', value=value, choices=[{'value': DEFAULT, 'label': 'Game default'},
                                                               {'value': 'on', 'label': 'On'},
                                                               {'value': 'off', 'label': 'Off'}])
        elif kind in ENUM_CHOICES:
            from lib.utilities.client_settings_catalog import split_words
            entry.update(kind='choice', value=value, choices=[{'value': DEFAULT, 'label': 'Game default'}] + [
                {'value': f'{kind}::{n}', 'label': split_words(n).replace(' plus', '+')} for n in ENUM_CHOICES[kind]])
        else:
            entry.update(kind='text', value=value)
        heading = 'Look Sensitivity' if part == 'Basic' else 'Advanced Look Options'
        groups.setdefault(heading, []).append(entry)
    return list(groups.items())


def _ensure_inner(save: Save, holder: str, part: str) -> Struct:
    prop = save.get(holder)
    if prop is None:
        prop = save.set(holder, _struct_type('FortGamepadUserOptions'), Struct('FortGamepadUserOptions', []))
    sub = next((p for p in prop.value.props if str(p.name) == part), None)
    if sub is None:
        struct_name = 'FortGamepadBasicOptions' if part == 'Basic' else 'FortGamepadAdvancedOptions'
        sub = Prop(FStr(part, False), _struct_type(struct_name), 0, Struct(struct_name, []))
        # Basic comes before Advanced, as the game writes them.
        prop.value.props.insert(0 if part == 'Basic' else len(prop.value.props), sub)
    return sub.value


def _set_field(inner: Struct, name: str, kind: str, value) -> None:
    prop = next((p for p in inner.props if str(p.name) == name), None)
    if value is None:
        inner.props[:] = [p for p in inner.props if str(p.name) != name]
        return
    if prop is None:
        inner.props.append(Prop(FStr(name, False), _field_type(kind), 0, value))
    else:
        prop.value = value


def _prune(save: Save, holder: str) -> None:
    prop = save.get(holder)
    if prop is None or not isinstance(prop.value, Struct) or not isinstance(prop.value.props, list):
        return
    prop.value.props[:] = [p for p in prop.value.props
                           if not (isinstance(p.value, Struct) and isinstance(p.value.props, list) and not p.value.props)]
    if not prop.value.props:
        save.remove(holder)


def apply_look(save: Save, key: str, value):
    part, name, label, kind, _desc = _spec(key)
    text = '' if value is None else str(value).strip()
    if text in ('', DEFAULT):
        stored = None
    elif kind == 'bool':
        if text not in ('on', 'off'):
            raise ValueError('Choose Game default, On or Off.')
        stored = text == 'on'
    elif kind in ENUM_CHOICES:
        if text not in {f'{kind}::{n}' for n in ENUM_CHOICES[kind]}:
            raise ValueError('That isn\'t one of the choices.')
        stored = FStr(text, False)
    else:
        try:
            number = float(text)
        except ValueError:
            raise ValueError('Enter a number.') from None
        if not math.isfinite(number) or number < 0:
            raise ValueError('Enter a number of 0 or more.')
        if kind == 'uint':
            if not number.is_integer() or number > UINT_HIGH:
                raise ValueError(f'Enter a whole number from 0 to {UINT_HIGH}.')
            stored = int(number)
        else:
            stored = number
    for holder in (USER_OPTIONS, LOCAL_OPTIONS):
        if holder == LOCAL_OPTIONS and save.get(LOCAL_OPTIONS) is None:
            continue           # the game keeps a local copy only sometimes; mirror it when it's there
        if stored is None:
            inner = _inner(save, holder, part)
            if inner is not None:
                _set_field(inner, name, kind, None)
                _prune(save, holder)
        else:
            _set_field(_ensure_inner(save, holder, part), name, kind, stored)
    return _display(kind, stored)


def look_label(key: str) -> str:
    return _spec(key)[2]


def look_values(save: Save) -> Dict[str, str]:
    return {f'{part}.{name}': _display(kind, look_value(save, f'{part}.{name}'))
            for part, name, _label, kind, _desc in LOOK_OPTIONS}


# Controller bindings -----------------------------------------------------------------------------

def _pad_items(save: Save) -> list:
    prop = save.get(PAD_BINDINGS)
    items = getattr(getattr(prop, 'value', None), 'items', None)
    return items if isinstance(items, list) else []


def pad_label(action: str, scale: float) -> str:
    from lib.utilities.client_settings_catalog import split_words
    if action in PAD_LABELS:
        return PAD_LABELS[action]
    name = action[len('Gamepad'):] if action.startswith('Gamepad') else action
    return split_words(name.replace('_Gamepad', '').replace('.', ' ')) + (' (reverse)' if scale < 0 else '')


def pad_key_choices(current: Optional[str]) -> List[dict]:
    choices = [{'value': UNBOUND, 'label': 'Not bound'}] + [{'value': k, 'label': l} for k, l in PAD_KEYS]
    if current and current != UNBOUND and current not in dict(PAD_KEYS):
        choices.append({'value': current, 'label': PAD_KEY_LABELS.get(current, current)})
    return choices


def preset(save: Save) -> str:
    prop = save.get(PRESET)
    return str(prop.value) if prop is not None else ''


def preset_entry(save: Save) -> dict:
    current = preset(save)
    choices = [{'value': k, 'label': l} for k, l in PRESETS]
    if current and current not in dict(PRESETS):
        choices.append({'value': current, 'label': current})
    return {'id': f'{PAD_PRESET}/{PRESET}', 'section': PAD_PRESET, 'key': PRESET, 'label': 'Controller Preset',
            'description': 'Which button layout the game uses. The bindings below only count with Custom; '
                           'changing one switches to Custom.', 'show_description': True, 'kind': 'choice',
            'value': current or DEFAULT, 'choices': choices, 'default': None}


def pad_groups(save: Save) -> List[Tuple[str, List[dict]]]:
    groups: Dict[str, List[dict]] = {'Preset': [preset_entry(save)]}
    seen = set()
    for item in _pad_items(save):
        action = str(_field(item, 'ActionName').value)
        scale = _scale(_field(item, 'InputScale').value)
        if (action, scale) in seen:
            continue
        seen.add((action, scale))
        heading = group_heading(str(_field(item, 'ActionGroup').value).split('::')[-1])
        label = pad_label(action, scale)
        key = str(_key_prop(item, 1).value)
        groups.setdefault(heading, []).append({
            'id': f'{PAD_BIND}/{bind_id(action, scale, 1)}', 'section': PAD_BIND, 'key': bind_id(action, scale, 1),
            'label': label, 'description': '', 'show_description': False, 'kind': 'choice', 'value': key,
            'choices': pad_key_choices(key), 'default': None})
    return list(groups.items())


def apply_pad_bind(save: Save, key: str, value) -> Tuple[str, bool]:
    """Set a controller button. Returns what to show and whether the preset was switched to Custom."""
    action, scale, slot = parse_bind_id(key)
    name = str(value or '').strip() or UNBOUND
    items = [i for i in _pad_items(save) if str(_field(i, 'ActionName').value) == action
             and _scale(_field(i, 'InputScale').value) == scale]
    if not items:
        raise ValueError('Unknown setting.')
    if name not in PAD_KEY_LABELS and name not in {str(_key_prop(i, slot).value) for i in items}:
        raise ValueError('That isn\'t one of the buttons.')
    for item in items:
        prop = _key_prop(item, slot)
        prop.value = FStr(name, getattr(prop.value, 'wide', False), getattr(prop.value, 'empty_zero', False))
    switched = preset(save) != CUSTOM_PRESET
    if switched:
        apply_preset(save, CUSTOM_PRESET)
    return name, switched


def apply_preset(save: Save, value) -> str:
    text = str(value or '').strip()
    if text not in dict(PRESETS) and text != preset(save):
        raise ValueError('That isn\'t one of the presets.')
    prop = save.get(PRESET)
    save.set(PRESET, TypeName('StrProperty'), FStr(text, getattr(prop.value, 'wide', False) if prop else False))
    return text


def pad_values(save: Save) -> Dict[str, str]:
    out = {}
    for _heading, entries in pad_groups(save):
        for e in entries:
            out[e['id']] = e['value']
    return out


def pad_entry_label(save: Save, section: str, key: str) -> str:
    if section == PAD_PRESET:
        return 'Controller Preset'
    action, scale, _slot = parse_bind_id(key)
    return pad_label(action, scale)


def pad_conflicts(save: Save, key: str) -> List[str]:
    action, scale, slot = parse_bind_id(key)
    for heading, entries in pad_groups(save):
        mine = next((e for e in entries if e['key'] == key and e['section'] == PAD_BIND), None)
        if mine is not None:
            if mine['value'] == UNBOUND:
                return []
            return [e['label'] for e in entries if e['section'] == PAD_BIND and e['key'] != key
                    and e['value'] == mine['value']]
    return []


# Is a controller connected? ----------------------------------------------------------------------

class _XInputState(ctypes.Structure):
    _fields_ = [('packet', ctypes.c_uint32), ('buttons', ctypes.c_uint16), ('lt', ctypes.c_uint8),
                ('rt', ctypes.c_uint8), ('lx', ctypes.c_int16), ('ly', ctypes.c_int16), ('rx', ctypes.c_int16),
                ('ry', ctypes.c_int16)]


class _JoyInfoEx(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint32) for n in ('size', 'flags', 'x', 'y', 'z', 'r', 'u', 'v', 'buttons',
                                               'button_number', 'pov', 'reserved1', 'reserved2')]


def controller_connected() -> bool:
    """True when Windows sees a game controller: an Xbox-style pad through XInput, or any other
    (PlayStation and others) through the joystick API."""
    try:
        for dll in ('xinput1_4', 'xinput1_3', 'xinput9_1_0'):
            try:
                xinput = getattr(ctypes.windll, dll)
                break
            except OSError:
                xinput = None
        if xinput is not None:
            state = _XInputState()
            for i in range(4):
                if xinput.XInputGetState(i, ctypes.byref(state)) == 0:
                    return True
        winmm = ctypes.windll.winmm
        info = _JoyInfoEx()
        info.size = ctypes.sizeof(info)
        info.flags = 0xFF            # JOY_RETURNALL
        for i in range(min(int(winmm.joyGetNumDevs()), 16)):
            if winmm.joyGetPosEx(i, ctypes.byref(info)) == 0:
                return True
    except (AttributeError, OSError):
        pass
    return False
