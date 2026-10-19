"""Turning the camera with keys, through Fortnite's own look axes.

Fortnite's keyboard menu has no turn keys, but its binding list (UserBindingsPerSubGame) accepts
the engine's look axes: an axis mapping named Turn turns left and right, LookUp looks up and
down, exactly as the mouse does. A key on Turn with InputScale -1 turns left while held, +1
right; LookUp -1 looks up, +1 down. Checked in game: keys bound this way turn the player, and the
game keeps them when it saves.

The game has no such entries by default, so they are added (to the Battle Royale list and the
shared list, like other bindings) when the first key is given and removed when the last key is
taken off. The InputScale's size sets how fast holding the key turns, shown as a percent.
"""
from __future__ import annotations

import copy
import math
from typing import Dict, List, Optional, Tuple

from lib.utilities.client_settings import FStr, Save, Struct
from lib.utilities.client_settings_binds import (MENU_LIST, SHARED_LIST, UNBOUND, KEY_LABELS, _field, _key_prop,
                                                 _lists, _scale, key_choices, users_of)

TURN = 'turn'
# (row key, axis, direction, label, description)
DIRECTIONS = [
    ('left', 'Turn', -1.0, 'Turn Left', 'Turns the camera left while you hold the key, as moving the mouse does.'),
    ('right', 'Turn', 1.0, 'Turn Right', 'Turns the camera right while you hold the key, as moving the mouse does.'),
    ('up', 'LookUp', -1.0, 'Look Up', 'Tilts the camera up while you hold the key, as moving the mouse does.'),
    ('down', 'LookUp', 1.0, 'Look Down', 'Tilts the camera down while you hold the key, as moving the mouse does.'),
]
SPEEDS = [('Turn', 'Turn Speed', 'How fast holding Turn Left or Turn Right turns the camera, in percent. '
                                 'X-Axis Sensitivity also changes it. Set a turn key first.'),
          ('LookUp', 'Look Up and Down Speed', 'How fast holding Look Up or Look Down tilts the camera, in '
                                               'percent. Y-Axis Sensitivity also changes it. Set a key first.')]
AXES = {spec[1] for spec in DIRECTIONS}
DEFAULT_SPEED = 100.0
SPEED_LOW, SPEED_HIGH = 1.0, 1000.0


def _direction(key: str):
    for spec in DIRECTIONS:
        if spec[0] == key:
            return spec
    raise ValueError('Unknown setting.')


def _items(save: Save, axis: str, sign: Optional[float] = None) -> List[Tuple[str, Struct]]:
    out = []
    for sub in (MENU_LIST, SHARED_LIST):
        for item in _lists(save).get(sub, []):
            if str(_field(item, 'ActionName').value) != axis:
                continue
            scale = _scale(_field(item, 'InputScale').value)
            if sign is None or math.copysign(1.0, scale) == sign:
                out.append((sub, item))
    return out


def speed(save: Save, axis: str) -> Optional[float]:
    items = _items(save, axis)
    if not items:
        return None
    return round(abs(_scale(_field(items[0][1], 'InputScale').value)) * 100, 1)


def key(save: Save, row: str, slot: int) -> str:
    _row, axis, sign, _label, _desc = _direction(row)
    items = _items(save, axis, sign)
    return str(_key_prop(items[0][1], slot).value) if items else UNBOUND


def rows(save: Save) -> List[dict]:
    """The turn key rows, two keys each, then the two speeds. The Keybinds tab shows them first,
    under Camera."""
    out = []
    for row, _axis, _sign, label_, description in DIRECTIONS:
        for slot in (1, 2):
            current = key(save, row, slot)
            out.append({'id': f'{TURN}/{row}#{slot}', 'section': TURN, 'key': f'{row}#{slot}',
                        'label': label_ if slot == 1 else f'{label_}, second key',
                        'description': description if slot == 1 else '', 'show_description': slot == 1,
                        'kind': 'choice', 'value': current, 'choices': key_choices(current), 'default': None})
    for axis, label_, description in SPEEDS:
        value = speed(save, axis)
        out.append({'id': f'{TURN}/speed:{axis}', 'section': TURN, 'key': f'speed:{axis}', 'label': label_,
                    'description': description, 'show_description': True, 'kind': 'text',
                    'value': '' if value is None else f'{value:g}', 'default': None})
    return out


def label(key_: str) -> str:
    if key_.startswith('speed:'):
        return {axis: l for axis, l, _desc in SPEEDS}[key_[len('speed:'):]]
    row, _, slot = key_.partition('#')
    text = _direction(row)[3]
    return text if slot == '1' else f'{text}, second key'


def _template(save: Save) -> Struct:
    """An existing axis mapping (Move Right, Move Forward) to copy the layout of a new entry from."""
    for sub in (MENU_LIST, SHARED_LIST):
        for item in _lists(save).get(sub, []):
            if _field(item, 'bIsAxisMapping').value is True and str(_field(item, 'ActionName').value) not in AXES:
                return item
    raise ValueError('Fortnite\'s bindings aren\'t in this settings file.')


def _set_key(item: Struct, slot: int, name: str) -> None:
    prop = _key_prop(item, slot)
    prop.value = FStr(name, getattr(prop.value, 'wide', False), getattr(prop.value, 'empty_zero', False))


def apply(save: Save, key_: str, value):
    if key_.startswith('speed:'):
        return _apply_speed(save, key_[len('speed:'):], value)
    row, _, slot_text = key_.partition('#')
    if slot_text not in ('1', '2'):
        raise ValueError('Unknown setting.')
    slot = int(slot_text)
    _row, axis, sign, _label, _desc = _direction(row)
    name = str(value or '').strip() or UNBOUND
    if name not in KEY_LABELS:
        raise ValueError('That isn\'t one of the keys.')
    items = _items(save, axis, sign)
    if not items and name != UNBOUND:
        template = _template(save)
        size = (speed(save, axis) or DEFAULT_SPEED) / 100.0
        lists = _lists(save)
        for sub in (MENU_LIST, SHARED_LIST):
            if sub not in lists:
                continue
            entry = copy.deepcopy(template)
            _field(entry, 'ActionName').value = FStr(axis, getattr(_field(template, 'ActionName').value, 'wide', False))
            _field(entry, 'InputScale').value = sign * size
            _set_key(entry, 1, UNBOUND)
            _set_key(entry, 2, UNBOUND)
            lists[sub].append(entry)
        items = _items(save, axis, sign)
    for _sub, item in items:
        _set_key(item, slot, name)
    # An entry with no keys left is taken out again.
    for sub, item in items:
        if str(_key_prop(item, 1).value) == UNBOUND and str(_key_prop(item, 2).value) == UNBOUND:
            _lists(save)[sub].remove(item)
    return name


def _apply_speed(save: Save, axis: str, value) -> str:
    if axis not in AXES:
        raise ValueError('Unknown setting.')
    text = str(value if value is not None else '').strip()
    items = _items(save, axis)
    if not items:
        if text == '':
            return ''
        raise ValueError('Give a turn key first, then set its speed.')
    if text == '':
        percent = DEFAULT_SPEED
    else:
        try:
            percent = float(text)
        except ValueError:
            raise ValueError(f'Enter a percent from {SPEED_LOW:g} to {SPEED_HIGH:g}.') from None
        if not math.isfinite(percent) or not SPEED_LOW <= percent <= SPEED_HIGH:
            raise ValueError(f'Enter a percent from {SPEED_LOW:g} to {SPEED_HIGH:g}.')
    for _sub, item in items:
        prop = _field(item, 'InputScale')
        prop.value = math.copysign(percent / 100.0, _scale(prop.value))
    return f'{round(percent, 1):g}'


def values(save: Save) -> Dict[str, str]:
    return {e['key']: e['value'] for e in rows(save)}


def conflicts(save: Save, key_: str) -> List[str]:
    """Other actions in the same section that use the key this turn row now has."""
    row, _, slot = key_.partition('#')
    if slot not in ('1', '2'):
        return []
    _row, axis, sign, _label, _desc = _direction(row)
    items = _items(save, axis, sign)
    if not items:
        return []
    mine = next((item for sub, item in items if sub == MENU_LIST), items[0][1])
    return users_of(_lists(save).get(MENU_LIST, []), mine, int(slot))
