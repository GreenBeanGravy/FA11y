"""Keyboard and mouse bindings and mouse sensitivity in Fortnite's settings file, as the settings
editor shows them.

Bindings live in UserBindingsPerSubGame: a map from game mode (ESubGame) to a list of
FortActionKeyMapping {ActionName, ActionGroup, KeyBind1 {KeyName}, KeyBind2 {KeyName},
InputScale, ...}. The Battle Royale list (ESubGame::Athena) is what Fortnite's Keyboard Controls
menu edits; the ESubGame::Invalid list holds the same actions and is kept in step with it. An
action with an axis (Move Forward and Move Backward) appears once per direction, told apart by
InputScale. "None" means no key.

The list also holds actions Fortnite's keyboard menu never shows, such as the controller's reset
camera. The game keeps keys given to them and answers them: Reset Camera on a keyboard key
recenters the camera in game. Reset Camera is listed under Camera, first, with the turn keys
(client_settings_turning); the gyro actions come last.

Mouse sensitivity is stored as a factor: the menu's X-Axis Sensitivity percent is the stored
MouseSensitivityX times 400 (stored 0.0025 shows as 1.0%). The game takes values below the menu
slider's lowest step and keeps them when it saves. Targeting and Scope Sensitivity are stored as
fractions (0.87 shows as 87%).
"""
from __future__ import annotations

import math
import re
from typing import Dict, Iterator, List, Optional, Tuple

from lib.utilities.client_settings import FStr, MapValue, Save, Struct

BIND, SENS = 'bind', 'sens'
BINDINGS = 'UserBindingsPerSubGame'
MENU_LIST, SHARED_LIST = 'ESubGame::Athena', 'ESubGame::Invalid'
UNBOUND = 'None'

# (key, label, stored properties, menu percent per stored unit, lowest, highest)
SENSITIVITY = [
    ('x', 'X-Axis Sensitivity', ('MouseSensitivityX', 'UpgradedMouseSensitivityX'), 400.0, 0.01, 1000.0),
    ('y', 'Y-Axis Sensitivity', ('MouseSensitivityY', 'UpgradedMouseSensitivityY'), 400.0, 0.01, 1000.0),
    ('targeting', 'Targeting Sensitivity', ('TargetingSlow',), 100.0, 0.01, 1000.0),
    ('scope', 'Scope Sensitivity', ('ScopedSlow',), 100.0, 0.01, 1000.0),
]
SENS_DESCRIPTIONS = {
    'x': 'Mouse sensitivity left and right, in percent, from 0.01 to 1000. Low values suit high-DPI mice.',
    'y': 'Mouse sensitivity up and down, in percent, from 0.01 to 1000. Low values suit high-DPI mice.',
    'targeting': 'Mouse sensitivity while aiming down sights, as a percent of the normal sensitivity.',
    'scope': 'Mouse sensitivity while looking through a scope, as a percent of the normal sensitivity.',
}

# Key names Fortnite stores (Unreal's FKey names) and how to say them. Escape is left out:
# the game uses it to leave menus.
KEYS: List[Tuple[str, str]] = (
    [(c, c) for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ']
    + [(w, str(i)) for i, w in enumerate(['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven',
                                          'Eight', 'Nine'])]
    + [(f'F{i}', f'F{i}') for i in range(1, 13)]
    + [('SpaceBar', 'Space'), ('Enter', 'Enter'), ('Tab', 'Tab'), ('BackSpace', 'Backspace'),
       ('CapsLock', 'Caps Lock'), ('LeftShift', 'Left Shift'), ('RightShift', 'Right Shift'),
       ('LeftControl', 'Left Control'), ('RightControl', 'Right Control'), ('LeftAlt', 'Left Alt'),
       ('RightAlt', 'Right Alt'), ('Tilde', 'Grave accent'), ('Hyphen', 'Minus'), ('Equals', 'Equals'),
       ('LeftBracket', 'Left bracket'), ('RightBracket', 'Right bracket'), ('Backslash', 'Backslash'),
       ('Semicolon', 'Semicolon'), ('Apostrophe', 'Apostrophe'), ('Comma', 'Comma'), ('Period', 'Period'),
       ('Slash', 'Slash'), ('Insert', 'Insert'), ('Delete', 'Delete'), ('Home', 'Home'), ('End', 'End'),
       ('PageUp', 'Page Up'), ('PageDown', 'Page Down'), ('Up', 'Up Arrow'), ('Down', 'Down Arrow'),
       ('Left', 'Left Arrow'), ('Right', 'Right Arrow')]
    + [(f'NumPad{w}', f'Numpad {i}') for i, w in enumerate(['Zero', 'One', 'Two', 'Three', 'Four', 'Five',
                                                             'Six', 'Seven', 'Eight', 'Nine'])]
    + [('Multiply', 'Numpad Multiply'), ('Add', 'Numpad Plus'), ('Subtract', 'Numpad Minus'),
       ('Decimal', 'Numpad Decimal'), ('Divide', 'Numpad Divide'), ('NumLock', 'Num Lock'),
       ('ScrollLock', 'Scroll Lock'), ('Pause', 'Pause'),
       ('LeftMouseButton', 'Left Mouse Button'), ('RightMouseButton', 'Right Mouse Button'),
       ('MiddleMouseButton', 'Middle Mouse Button'), ('ThumbMouseButton', 'Mouse Button 4'),
       ('ThumbMouseButton2', 'Mouse Button 5'), ('MouseScrollUp', 'Mouse Wheel Up'),
       ('MouseScrollDown', 'Mouse Wheel Down')]
)
KEY_LABELS = dict(KEYS)
KEY_LABELS.update({UNBOUND: 'Not bound', 'Escape': 'Escape'})

# Actions Fortnite's Keyboard Controls menu leaves out (checked against 42.40's menu): Reset
# Camera goes first under Camera, the gyro actions last.
CAMERA_HEADING, GYRO_HEADING = 'Camera', 'Gyro Aiming'
CAMERA = {'GamepadResetCamera': 'Reset Camera'}
GYRO = {
    'GamepadGyroModifier': 'Gyro Modifier',
    'GamepadResetCameraGyroModifier': 'Gyro Modifier: Reset Camera',
    'GamepadToggleHarvestGyroModifier': 'Gyro Modifier: Toggle Harvesting Tool',
    'GamepadToggleCrouchGyroModifier': 'Gyro Modifier: Toggle Crouch',
}
# Actions left off this list: forced walking and jogging speeds, and the look axes, which have
# their own Turning rows (client_settings_turning).
LEFT_OUT = {'ForceJogToggle', 'ForceJogHold', 'ForceWalkToggle', 'ForceWalkHold', 'Turn', 'LookUp'}
NOTES = {
    'GamepadResetCamera': 'Levels the camera with the horizon. With Reset Camera Axes on the Game tab set to Yaw '
                          'or Both, it also turns the camera the way you are moving: hold Move Backward and press '
                          'it to look behind you.',
}
GYRO_NOTE = 'Used with motion aiming, on controllers that have it.'

# Menu names for actions, keyed by (ActionName, InputScale) where an axis has two directions.
LABELS: Dict[object, str] = {
    ('MoveForward', 1.0): 'Move Forward', ('MoveForward', -1.0): 'Move Backward',
    ('MoveRight', -1.0): 'Move Left', ('MoveRight', 1.0): 'Move Right',
    'Jump': 'Jump', 'Sprint': 'Sprint', 'AutoRun': 'Auto Run', 'Crouch': 'Crouch',
    'Fire': 'Weapon Primary (Fire)', 'Target': 'Weapon Secondary (Aim)', 'Reload': 'Reload', 'Use': 'Interact',
    'HotbarKey1': 'Pickaxe (Press) / Gizmos (Hold)', 'HotbarKey2': 'Weapon Slot 1', 'HotbarKey3': 'Weapon Slot 2',
    'HotbarKey4': 'Weapon Slot 3', 'HotbarKey5': 'Weapon Slot 4', 'HotbarKey6': 'Weapon Slot 5',
    'HotbarKeyPocket': 'Pocket Slot', 'CrouchWhileBuilding': 'Crouch While Building (Tap) / Slide (Hold)',
    'HotbarKeyF1': 'Wall', 'HotbarKeyF2': 'Floor', 'HotbarKeyF3': 'Stairs', 'HotbarKeyF4': 'Roof',
    'HotbarKeyF5': 'Trap', 'BuildConfirm': 'Place Building',
    'PerformBuildingImprovementInteraction': 'Repair / Upgrade', 'RotatePrimitiveClockwise': 'Rotate Building',
    'ChangeMaterial': 'Change Building Material', 'PerformBuildingEditInteraction': 'Building Edit',
    'CrouchWhileEditing': 'Crouch While Editing (Tap) / Slide (Hold)', 'EditSelect': 'Select Building Edit',
    'BuildingEditReset': 'Reset Building Edit', 'PerformBuildingResetInteraction': 'Reset Building',
    'HotbarKeySimpleBuild1': 'Simple Build Primary (Traversal)', 'HotbarKeySimpleBuild2': 'Simple Build Secondary (Wall)',
    'ChangeMaterialSimpleBuild': 'Simple Build Change Material',
    'PlaceMapMarkerInWorld': 'Place Marker (Tap) / Squad Comms (Hold)', 'PlaceEnemyMarkerInWorld': 'Place Enemy Marker',
    'PushToTalk': 'Push to Talk', 'SquadQuickChatPicker': 'Squad Requests', 'chat': 'Toggle Text Chat',
    'EmotePicker': 'Emote', 'ReplayLastEmote': 'Repeat Last Emote',
    'TogglePickAxe': 'Toggle Pickaxe (Press) / Gizmos (Hold)', 'TrapPicker': 'Trap Equip / Picker',
    'SwitchQuickbar': 'Switch Mode', 'SlotUp': 'Slot Up', 'SlotDown': 'Slot Down',
    'PickerPreviousWheel': 'Previous Picker Wheel', 'PickerNextWheel': 'Next Picker Wheel',
    'ToggleCursorMode': 'Cursor Mode', 'ToggleFullscreenMap': 'Toggle Map', 'ToggleInventory': 'Toggle Inventory',
    'OpenQuests': 'Open Quests', 'ToggleQuestVOMute': 'Toggle Quest VO Mute',
    'DBNOCarryHoist': 'DBNO Carry', 'DBNOCarryDrop': 'DBNO Place',
    'AlternateInteractCarry': 'Reboot Teammate / Object Carry / Sidegrade', 'AlternateInteractPlace': 'Object Place',
    'OpenAugmentSelection': 'Open Augment Select', 'AugmentReroll': 'Augment Reroll',
    'AugmentSelectionViewSwap': 'Augment View Swap',
    **{f'LockerEmote{i}': f'Locker Emote Slot {i}' for i in range(1, 9)},
    **CAMERA,
    **GYRO,
}
# Fortnite's internal group names and code names, as the menu's section headings.
GROUPS = [
    ('Movement', 'Movement'), ('AllModes', 'Movement and General'), ('Combat', 'Combat'),
    ('CombatAndBuilding', 'Combat'), ('CombatAndAthenaLTMAbilities', 'Combat'),
    ('CombatBuildingAndAthenaLTMAbilities', 'Combat and Building'), ('Building', 'Building'), ('Edit', 'Editing'),
    ('SimpleBuild', 'Simple Build'), ('Picker', 'Picker Wheels'), ('Other', 'Communication, Emotes and Menus'),
    ('DBNOCarry', 'Carrying Players'), ('InteractionStart', 'Carrying Objects'), ('InteractionStop', 'Carrying Objects'),
    ('PlayerAugments', 'Augments'), ('RemoteControl', 'Falcon Scout'), ('Riding', 'Riding'),
    ('Dagwood', 'Vehicles - Cars'), ('Dirtbike', 'Vehicles - Dirt Bike'), ('Sportbike', 'Vehicles - Sport Bike'),
    ('Nevada', 'Vehicles - UFO'), ('Tank', 'Vehicles - Tank'), ('Rock', 'Vehicles - Rocket Racing'),
    ('Biplane', 'Vehicles - X-4 Stormwing'), ('Ostrich', 'Vehicles - B.R.U.T.E.'), ('Meatball', 'Vehicles - Motorboat'),
    ('Hoagie', 'Vehicles - Choppa'), ('ShoppingCart', 'Vehicles - Shopping Cart'), ('Cannon', 'Vehicles - Pirate Cannon'),
    ('GolfCart', 'Vehicles - ATK'), ('QuadCrasher', 'Vehicles - Quadcrasher'), ('Hamsterball', 'Vehicles - Baller'),
    ('Jackal', 'Vehicles - Hoverboard'), ('Tether', 'Tether'), ('AthenaLTMAbilities', 'Limited Time Modes'),
    ('Creative', 'Creative'),
]


def _field(struct: Struct, name: str):
    return next(p for p in struct.props if str(p.name) == name)


def _scale(value) -> float:
    return float(value) if isinstance(value, (int, float)) else 1.0


def _lists(save: Save) -> Dict[str, list]:
    prop = save.get(BINDINGS)
    if prop is None or not isinstance(prop.value, MapValue):
        return {}
    out = {}
    for sub, value in prop.value.items:
        if isinstance(value, Struct) and isinstance(value.props, list) and value.props:
            items = getattr(value.props[0].value, 'items', None)
            if isinstance(items, list):
                out[str(sub)] = items
    return out


def bind_id(action: str, scale: float, slot: int) -> str:
    return f'{action}@{scale:g}#{slot}'


def parse_bind_id(key: str) -> Tuple[str, float, int]:
    m = re.fullmatch(r'(.+)@(-?[0-9.]+)#([12])', key)
    if not m:
        raise ValueError('Unknown setting.')
    return m.group(1), float(m.group(2)), int(m.group(3))


def _matching(save: Save, action: str, scale: float) -> Iterator[Struct]:
    lists = _lists(save)
    for sub in (MENU_LIST, SHARED_LIST):
        for item in lists.get(sub, []):
            if str(_field(item, 'ActionName').value) == action and _scale(_field(item, 'InputScale').value) == scale:
                yield item


def _key_prop(item: Struct, slot: int):
    return _field(_field(item, f'KeyBind{slot}').value, 'KeyName')


def current_key(save: Save, action: str, scale: float, slot: int) -> Optional[str]:
    for item in _matching(save, action, scale):
        return str(_key_prop(item, slot).value)
    return None


def action_label(action: str, scale: float) -> str:
    from lib.utilities.client_settings_catalog import split_words
    from lib.utilities.client_settings_turning import DIRECTIONS
    for _row, axis, sign, label, _desc in DIRECTIONS:
        if action == axis and math.copysign(1.0, scale) == sign:
            return label
    label = LABELS.get((action, scale)) or LABELS.get(action)
    if label:
        return label
    words = split_words(action.replace('.', ' '))
    return words + (' (reverse)' if scale < 0 else '')


def _heading_of(item: Struct) -> str:
    """The section the game's own grouping puts an action in. Keys only clash within one."""
    return group_heading(str(_field(item, 'ActionGroup').value).split('::')[-1])


def users_of(items: list, mine: Struct, slot: int, label=None) -> List[str]:
    """Actions in mine's section that also use the key in mine's slot: other actions in either
    slot, and mine in its other slot. label names an item."""
    label = label or (lambda i: action_label(str(_field(i, 'ActionName').value), _scale(_field(i, 'InputScale').value)))
    key = str(_key_prop(mine, slot).value)
    if not key or key == UNBOUND:
        return []

    def ident(item):
        return str(_field(item, 'ActionName').value), math.copysign(1.0, _scale(_field(item, 'InputScale').value))

    out: List[str] = []
    for item in items:
        if ident(item)[0] in LEFT_OUT - {'Turn', 'LookUp'} or _heading_of(item) != _heading_of(mine):
            continue
        slots = (3 - slot,) if ident(item) == ident(mine) else (1, 2)
        if any(str(_key_prop(item, s).value) == key for s in slots) and label(item) not in out:
            out.append(label(item))
    return out


def group_heading(group: str) -> str:
    for prefix, heading in GROUPS:
        if group == prefix:
            return heading
    for prefix, heading in GROUPS:
        if group.startswith(prefix):
            return heading
    from lib.utilities.client_settings_catalog import split_words
    return split_words(group)


def key_label(name: Optional[str]) -> str:
    return KEY_LABELS.get(name or UNBOUND, name or '')


def key_fields(current: Optional[str]) -> dict:
    """A key row's control: a button that waits for a key or mouse button and shows the key's name.
    The window sends back the Fortnite name of what was pressed."""
    return {'kind': 'keybind', 'capture': 'key', 'value': current or UNBOUND, 'display': key_label(current)}


def bind_groups(save: Save) -> List[Tuple[str, List[dict]]]:
    """The menu list's actions, two key rows each, grouped under the menu's headings: Camera
    first, Gyro Aiming last."""
    groups: Dict[str, List[dict]] = {}
    seen = set()
    for item in _lists(save).get(MENU_LIST, []):
        action = str(_field(item, 'ActionName').value)
        scale = _scale(_field(item, 'InputScale').value)
        if (action, scale) in seen or action in LEFT_OUT:
            continue
        seen.add((action, scale))
        heading = (CAMERA_HEADING if action in CAMERA else GYRO_HEADING if action in GYRO
                   else group_heading(str(_field(item, 'ActionGroup').value).split('::')[-1]))
        label = action_label(action, scale)
        note = GYRO_NOTE if action in GYRO else NOTES.get(action, '')
        for slot in (1, 2):
            key = str(_key_prop(item, slot).value)
            groups.setdefault(heading, []).append({
                'id': f'{BIND}/{bind_id(action, scale, slot)}', 'section': BIND, 'key': bind_id(action, scale, slot),
                'label': label if slot == 1 else f'{label}, second key',
                'description': note if slot == 1 else '', 'show_description': bool(note) and slot == 1,
                **key_fields(key), 'default': None})
    camera = groups.pop(CAMERA_HEADING, None)
    gyro = groups.pop(GYRO_HEADING, None)
    return (([(CAMERA_HEADING, camera)] if camera else []) + list(groups.items())
            + ([(GYRO_HEADING, gyro)] if gyro else []))


def bind_label(key: str) -> str:
    action, scale, slot = parse_bind_id(key)
    label = action_label(action, scale)
    return label if slot == 1 else f'{label}, second key'


def apply_bind(save: Save, key: str, value) -> str:
    action, scale, slot = parse_bind_id(key)
    name = str(value or '').strip() or UNBOUND
    items = list(_matching(save, action, scale))
    if not items:
        raise ValueError('Unknown setting.')
    allowed = set(KEY_LABELS) | {str(_key_prop(i, slot).value) for i in items}
    if name not in allowed:
        raise ValueError('That isn\'t one of the keys.')
    for item in items:
        prop = _key_prop(item, slot)
        old = prop.value
        prop.value = FStr(name, getattr(old, 'wide', False), getattr(old, 'empty_zero', False))
    return name


def bind_values(save: Save) -> Dict[str, str]:
    out = {}
    for _heading, entries in bind_groups(save):
        for e in entries:
            out[e['key']] = e['value']
    return out


def conflicts(save: Save, key: str) -> List[str]:
    """Other actions in the same section that use the key this row now has."""
    action, scale, slot = parse_bind_id(key)
    mine = next(_matching(save, action, scale), None)
    if mine is None:
        return []
    return users_of(_lists(save).get(MENU_LIST, []), mine, slot)


# Sensitivity -------------------------------------------------------------------------------------

def _sens_spec(key: str):
    for spec in SENSITIVITY:
        if spec[0] == key:
            return spec
    raise ValueError('Unknown setting.')


def sens_value(save: Save, key: str) -> Optional[float]:
    _key, _label, props, factor, _low, _high = _sens_spec(key)
    prop = save.get(props[0])
    if prop is None or not isinstance(prop.value, float) or prop.value < 0:
        return None
    return round(prop.value * factor, 3)


def sens_entries(save: Save) -> List[dict]:
    entries = []
    for key, label, props, _factor, low, high in SENSITIVITY:
        value = sens_value(save, key)
        if value is None:
            continue
        entries.append({'id': f'{SENS}/{key}', 'section': SENS, 'key': key, 'label': label,
                        'description': SENS_DESCRIPTIONS[key], 'show_description': True, 'kind': 'number',
                        'value': value, 'min': low, 'max': high, 'step': 0.1, 'decimals': 2, 'default': None})
    return entries


def sens_label(key: str) -> str:
    return _sens_spec(key)[1]


def apply_sens(save: Save, key: str, value) -> float:
    _key, label, props, factor, low, high = _sens_spec(key)
    try:
        percent = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'Enter a percent from {low:g} to {high:g}.') from None
    if not math.isfinite(percent) or not low <= percent <= high:
        raise ValueError(f'Enter a percent from {low:g} to {high:g}.')
    stored = percent / factor
    for name in props:
        prop = save.get(name)
        if prop is not None:
            prop.value = stored
    return round(percent, 3)


SENS_PROPERTIES = {name for spec in SENSITIVITY for name in spec[2]}
