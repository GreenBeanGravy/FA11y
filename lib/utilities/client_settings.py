"""Read and write Fortnite's synced settings file (ClientSettings.Sav).

This is the file the game's settings menu saves. Epic keeps it in the player's cloud storage; the
game also caches it at ``%LOCALAPPDATA%\\FortniteGame\\Saved\\Cloud\\<account id>\\ClientSettings.Sav``.

Layout:

* A 16-byte ``ECFD`` header (magic, a constant 0xF619, 1, the uncompressed size), then the save
  compressed with zlib at level 9. Compressing again at level 9 gives back the same bytes.
* The save: magic ``e9 9d 18 a2``, file versions, engine version and branch, a custom-version
  table, then Unreal 5.6 tagged properties ending with ``None``. Each tag holds its full type
  tree (name, then that many type parameters, recursively), the value's size and flag bits.
* Fortnite saves only values that differ from its defaults, so a setting at its default is
  simply missing. Adding a tag sets it; removing the tag puts it back to the game's default.
* ``SettingRecordPartitionSchemas`` holds one entry per game mode partition; each entry's
  ``PartitionContents`` byte array is itself a whole nested save.

Values of types this module does not decode keep their raw bytes, so parsing and writing a file
gives back exactly the same bytes (the tests check this).
"""
from __future__ import annotations

import io
import struct
import zlib
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple

SAVE_MAGIC = b'\xe9\x9d\x18\xa2'
CLOUD_MAGIC = b'ECFD'

# EPropertyTagFlags
HAS_ARRAY_INDEX, HAS_GUID, HAS_EXTENSIONS, NATIVE_SERIALIZE, BOOL_TRUE = 0x01, 0x02, 0x04, 0x08, 0x10

SCALARS = {
    'Int8Property': '<b', 'Int16Property': '<h', 'IntProperty': '<i', 'Int64Property': '<q',
    'UInt16Property': '<H', 'UInt32Property': '<I', 'UInt64Property': '<Q',
    'FloatProperty': '<f', 'DoubleProperty': '<d',
}
STRINGS = {'StrProperty', 'NameProperty', 'EnumProperty', 'SoftObjectProperty', 'ObjectProperty',
           'ClassProperty', 'SoftClassProperty'}
# Structs written in binary wherever they appear, with their size in bytes.
NATIVE_STRUCTS = {'Guid': 16, 'LinearColor': 16, 'Color': 4, 'Vector': 24, 'Vector2D': 16,
                  'Vector4': 32, 'Rotator': 24, 'Quat': 32, 'IntPoint': 8, 'IntVector': 12,
                  'DateTime': 8, 'Timespan': 8, 'FrameNumber': 4}


class SettingsFileError(ValueError):
    """The file is not a settings save this module understands."""


class FStr(str):
    """A string that remembers how it was stored: UTF-16 or not, and an empty one as length 0."""

    def __new__(cls, text: str, wide: Optional[bool] = None, empty_zero: bool = False):
        obj = super().__new__(cls, text)
        obj.wide = wide
        obj.empty_zero = empty_zero
        return obj


@dataclass
class TypeName:
    name: str
    params: list = field(default_factory=list)

    def __str__(self) -> str:
        return self.name + ('(' + ','.join(map(str, self.params)) + ')' if self.params else '')


@dataclass
class Prop:
    name: str
    type: TypeName
    flags: int
    value: object
    array_index: int = 0
    guid: bytes = b''
    ext: bytes = b''


@dataclass
class Struct:
    name: str
    props: object          # a list of Prop, or Raw for structs stored in binary


@dataclass
class Raw:
    data: bytes


@dataclass
class Array:
    items: list
    removed: Optional[list] = None   # sets: elements to remove, kept as read


@dataclass
class MapValue:
    items: List[Tuple[object, object]]
    removed: list


@dataclass
class Save:
    header: bytes
    props: List[Prop]
    tail: bytes

    def get(self, name: str) -> Optional[Prop]:
        return next((p for p in self.props if p.name == name and not p.array_index), None)

    def set(self, name: str, type_name: TypeName, value) -> Prop:
        """Set a top-level setting, adding its tag when the file doesn't have it yet."""
        prop = self.get(name)
        if prop is None:
            prop = Prop(FStr(name, False), type_name, 0, value)
            self.props.append(prop)
        else:
            prop.value = value
        return prop

    def remove(self, name: str) -> bool:
        """Remove a top-level setting so the game uses its default. True if it was there."""
        before = len(self.props)
        self.props = [p for p in self.props if not (p.name == name and not p.array_index)]
        return len(self.props) != before


# Reading -----------------------------------------------------------------------------------------

class _Reader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data, self.pos = data, pos

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise SettingsFileError(f'read past the end at {self.pos:#x}')
        value = self.data[self.pos:self.pos + n]
        self.pos += n
        return value

    def unpack(self, fmt: str):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))[0]

    def i32(self) -> int:
        return self.unpack('<i')

    def u8(self) -> int:
        return self.take(1)[0]

    def fstring(self) -> FStr:
        n = self.i32()
        if n == 0:
            return FStr('', False, True)
        if n < 0:
            raw = self.take(-n * 2)
            return FStr(raw[:-2].decode('utf-16-le', 'surrogatepass'), True)
        return FStr(self.take(n)[:-1].decode('latin-1'), False)


def _read_typename(r: _Reader) -> TypeName:
    name = r.fstring()
    count = r.i32()
    if not 0 <= count <= 8:
        raise SettingsFileError('bad type name')
    return TypeName(name, [_read_typename(r) for _ in range(count)])


def _enum_param(t: TypeName) -> bool:
    return bool(t.params) and t.params[0].name not in ('None', '')


def _read_header(r: _Reader) -> bytes:
    start = r.pos
    if r.take(4) != SAVE_MAGIC:
        raise SettingsFileError('not a Fortnite settings save')
    r.take(4 + 4 + 4 + 2 + 4)   # file versions, engine version, changelist
    r.fstring()                 # branch
    r.take(4 + 1 + 1)           # custom version format
    count = r.i32()
    r.take(count * 20)          # custom versions: GUID + version
    r.take(1)
    return r.data[start:r.pos]


def _read_props(r: _Reader) -> List[Prop]:
    props = []
    while True:
        name = r.fstring()
        if name == 'None':
            return props
        t = _read_typename(r)
        size = r.i32()
        flags = r.u8()
        prop = Prop(name, t, flags, None)
        if flags & HAS_ARRAY_INDEX:
            prop.array_index = r.i32()
        if flags & HAS_GUID:
            prop.guid = r.take(16)
        if flags & HAS_EXTENSIONS:
            ext = r.u8()
            prop.ext = bytes([ext]) + (r.take(2) if ext & 0x02 else b'')
        body = r.take(size)
        try:
            inner = _Reader(body)
            prop.value = _read_value(inner, t, flags, size, top=True)
            if inner.pos != size:
                prop.value = Raw(body)
        except (SettingsFileError, struct.error, UnicodeDecodeError, IndexError):
            prop.value = Raw(body)
        props.append(prop)


def _read_value(r: _Reader, t: TypeName, flags: int = 0, size: int = 0, top: bool = False):
    kind = t.name
    if kind == 'BoolProperty':
        return bool(flags & BOOL_TRUE) if top else bool(r.u8())
    if kind in SCALARS:
        return r.unpack(SCALARS[kind])
    if kind in STRINGS:
        return r.fstring()
    if kind == 'ByteProperty':
        return r.fstring() if _enum_param(t) else r.u8()
    if kind == 'StructProperty':
        struct_name = t.params[0].name if t.params else ''
        if top and flags & NATIVE_SERIALIZE:
            return Raw(r.take(size))
        if struct_name in NATIVE_STRUCTS:
            return Struct(struct_name, Raw(r.take(NATIVE_STRUCTS[struct_name])))
        return Struct(struct_name, _read_props(r))
    if kind == 'ArrayProperty':
        count = r.i32()
        item = t.params[0]
        if item.name == 'ByteProperty' and not _enum_param(item):
            data = r.take(count)
            if data[:4] == SAVE_MAGIC:
                try:
                    return parse_save(data)
                except (SettingsFileError, struct.error, UnicodeDecodeError, IndexError):
                    pass
            return bytes(data)
        return Array([_read_value(r, item) for _ in range(count)])
    if kind == 'SetProperty':
        item = t.params[0]
        removed = [_read_value(r, item) for _ in range(r.i32())]
        return Array([_read_value(r, item) for _ in range(r.i32())], removed)
    if kind == 'MapProperty':
        key_type, value_type = t.params
        removed = [_read_value(r, key_type) for _ in range(r.i32())]
        items = []
        for _ in range(r.i32()):
            key = _read_value(r, key_type)
            items.append((key, _read_value(r, value_type)))
        return MapValue(items, removed)
    if top:
        return Raw(r.take(size))
    raise SettingsFileError(f'cannot read {t} inside a container')


def parse_save(data: bytes) -> Save:
    r = _Reader(data)
    header = _read_header(r)
    props = _read_props(r)
    return Save(header, props, data[r.pos:])


# Writing -----------------------------------------------------------------------------------------

def _write_fstring(out, text: str) -> None:
    if not isinstance(text, FStr):
        text = FStr(text, any(ord(c) > 255 for c in text), text == '')
    if text == '' and text.empty_zero:
        out.write(struct.pack('<i', 0))
    elif text.wide:
        raw = text.encode('utf-16-le', 'surrogatepass') + b'\0\0'
        out.write(struct.pack('<i', -(len(raw) // 2)))
        out.write(raw)
    else:
        raw = text.encode('latin-1') + b'\0'
        out.write(struct.pack('<i', len(raw)))
        out.write(raw)


def _write_typename(out, t: TypeName) -> None:
    _write_fstring(out, t.name)
    out.write(struct.pack('<i', len(t.params)))
    for param in t.params:
        _write_typename(out, param)


def _write_props(out, props: List[Prop]) -> None:
    for prop in props:
        _write_fstring(out, prop.name)
        _write_typename(out, prop.type)
        body = io.BytesIO()
        _write_value(body, prop.type, prop.value, top=True)
        flags = prop.flags
        if prop.type.name == 'BoolProperty' and not isinstance(prop.value, Raw):
            flags = (flags | BOOL_TRUE) if prop.value else (flags & ~BOOL_TRUE)
        out.write(struct.pack('<i', len(body.getvalue())))
        out.write(bytes([flags]))
        if flags & HAS_ARRAY_INDEX:
            out.write(struct.pack('<i', prop.array_index))
        if flags & HAS_GUID:
            out.write(prop.guid)
        if flags & HAS_EXTENSIONS:
            out.write(prop.ext)
        out.write(body.getvalue())
    _write_fstring(out, FStr('None', False))


def _write_value(out, t: TypeName, value, top: bool = False) -> None:
    kind = t.name
    if isinstance(value, Raw):
        out.write(value.data)
    elif kind == 'BoolProperty':
        if not top:
            out.write(bytes([1 if value else 0]))
    elif kind in SCALARS:
        out.write(struct.pack(SCALARS[kind], value))
    elif kind in STRINGS:
        _write_fstring(out, value)
    elif kind == 'ByteProperty':
        if _enum_param(t):
            _write_fstring(out, value)
        else:
            out.write(bytes([value]))
    elif kind == 'StructProperty':
        if isinstance(value.props, Raw):
            out.write(value.props.data)
        else:
            _write_props(out, value.props)
    elif kind == 'ArrayProperty':
        if isinstance(value, Save):
            data = dump_save(value)
            out.write(struct.pack('<i', len(data)))
            out.write(data)
        elif isinstance(value, (bytes, bytearray)):
            out.write(struct.pack('<i', len(value)))
            out.write(value)
        else:
            out.write(struct.pack('<i', len(value.items)))
            for item in value.items:
                _write_value(out, t.params[0], item)
    elif kind == 'SetProperty':
        for group in (value.removed or [], value.items):
            out.write(struct.pack('<i', len(group)))
            for item in group:
                _write_value(out, t.params[0], item)
    elif kind == 'MapProperty':
        key_type, value_type = t.params
        out.write(struct.pack('<i', len(value.removed)))
        for key in value.removed:
            _write_value(out, key_type, key)
        out.write(struct.pack('<i', len(value.items)))
        for key, item in value.items:
            _write_value(out, key_type, key)
            _write_value(out, value_type, item)
    else:
        raise SettingsFileError(f'cannot write {t}')


def dump_save(save: Save) -> bytes:
    out = io.BytesIO()
    out.write(save.header)
    _write_props(out, save.props)
    out.write(save.tail)
    return out.getvalue()


# The cloud file ----------------------------------------------------------------------------------

@dataclass
class SettingsFile:
    """A ClientSettings.Sav: the save plus the cloud wrapper it came in (None if unwrapped)."""
    save: Save
    wrapper: Optional[Tuple[int, int]]

    def to_bytes(self) -> bytes:
        raw = dump_save(self.save)
        if self.wrapper is None:
            return raw
        tag, version = self.wrapper
        return struct.pack('<4sIII', CLOUD_MAGIC, tag, version, len(raw)) + zlib.compress(raw, 9)


def parse_file(data: bytes) -> SettingsFile:
    if data[:4] == CLOUD_MAGIC:
        if len(data) < 16:
            raise SettingsFileError('the settings file is cut short')
        _, tag, version, size = struct.unpack_from('<4sIII', data)
        try:
            raw = zlib.decompress(data[16:])
        except zlib.error as e:
            raise SettingsFileError('the settings file could not be decompressed') from e
        if len(raw) != size:
            raise SettingsFileError('the settings file size does not match its header')
        return SettingsFile(parse_save(raw), (tag, version))
    return SettingsFile(parse_save(data), None)


def walk(props: List[Prop], prefix: str = '') -> Iterator[Tuple[str, Prop]]:
    """Every leaf setting as (path, prop). Paths look like ``Name``, ``Name/Inner`` or ``Name[3]/Inner``."""
    for prop in props:
        path = prefix + prop.name + (f'#{prop.array_index}' if prop.array_index else '')
        yield from _walk_value(path, prop, prop.value)


def _walk_value(path: str, prop: Prop, value) -> Iterator[Tuple[str, Prop]]:
    if isinstance(value, Save):
        yield from walk(value.props, path + '/')
    elif isinstance(value, Struct) and isinstance(value.props, list):
        yield from walk(value.props, path + '/')
    elif isinstance(value, Array) and value.items and isinstance(value.items[0], Struct):
        for i, item in enumerate(value.items):
            yield from _walk_value(f'{path}[{i}]', prop, item)
    else:
        yield path, prop
