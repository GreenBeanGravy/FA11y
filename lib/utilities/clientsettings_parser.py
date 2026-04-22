"""
Fortnite ClientSettings.Sav parser and serializer.

Handles the current (UE5-era, Fortnite 27+ / 40+) save format. Supports full
read and write, so individual properties (including keybinds, sensitivity,
volumes, etc.) can be modified and the file re-emitted.

Format summary
--------------

Outer envelope (optional):
    If the file begins with ASCII "ECFD":
        [0x00]  "ECFD"                         magic
        [0x04]  uint32 compressed_flags        (purpose unclear; preserved)
        [0x08]  uint32 version                 (= 1)
        [0x0C]  uint32 uncompressed_size
        [0x10]  zlib-compressed inner stream
    Otherwise the file IS the inner stream.

Inner stream header:
    uint32  format_magic                       (0xa2189de9 for 40.20-era)
    uint32  ue4_package_file_version
    uint32  ue5_package_file_version
    uint16  engine_major, uint16 engine_minor, uint16 engine_patch
    uint32  engine_changelist
    FString branch                             ("++Fortnite+Release-40.20")
    int32   post_branch_value                  (custom-version count or -1)
    <custom-version container + other metadata, variable length>
    <tagged property body, terminated by Name == "None">

FPropertyTypeName (recursive):
    FString Name
    int32   NumParams
    [FPropertyTypeName; NumParams]

FPropertyTag (UE5 typed-tag format):
    FString Name
    if Name == "None": body ends
    FPropertyTypeName TypeName
    int32   ValueSize
    uint8   Flags                              (bitfield, see TagFlag.*)
    if Flags & HasArrayIndex:       int32 ArrayIndex
    if Flags & HasPropertyGuid:     16-byte Guid
    if Flags & HasPropertyExtensions: byte + optional payload
    <ValueSize bytes of value>

Values: scalar/struct/array/set/map as documented inline.

PartitionContents arrays hold nested save streams using the same inner
format; they are parsed and serialized recursively.

Round-trip strategy
-------------------

For write support we don't re-emit the "everything before the property body"
region from scratch — that region contains a custom-version table whose
layout varies by engine version and is tedious to implement. Instead we
split every stream into (header_bytes, property_body) at parse time. On
serialize we preserve the original header_bytes and only re-emit the body.
That produces byte-identical output for unmodified files and a
well-formed file for modified ones, without needing to understand anything
about the custom-version container.

The `format_magic` is a per-build constant (not a checksum) so it doesn't
need to be recomputed.
"""

from __future__ import annotations

import argparse
import json
import logging
import struct
import sys
import zlib
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Primitive reader / writer
# ---------------------------------------------------------------------------


class Reader:
    __slots__ = ("data", "pos")

    def __init__(self, data: bytes, pos: int = 0) -> None:
        self.data = data
        self.pos = pos

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def read(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise EOFError(f"need {n} bytes at 0x{self.pos:x}, have {self.remaining()}")
        v = self.data[self.pos : self.pos + n]
        self.pos += n
        return v

    def u8(self) -> int:
        return self.read(1)[0]

    def i8(self) -> int:
        return struct.unpack("<b", self.read(1))[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.read(2))[0]

    def i16(self) -> int:
        return struct.unpack("<h", self.read(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.read(8))[0]

    def f32(self) -> float:
        return struct.unpack("<f", self.read(4))[0]

    def f64(self) -> float:
        return struct.unpack("<d", self.read(8))[0]

    def fstring(self) -> str:
        n = self.i32()
        if n == 0:
            return ""
        if n > 0:
            raw = self.read(n)
            return raw[:-1].decode("latin-1", errors="replace")
        raw = self.read(-n * 2)
        return raw[:-2].decode("utf-16-le", errors="replace")

    def guid(self) -> bytes:
        return self.read(16)


class Writer:
    __slots__ = ("buf",)

    def __init__(self) -> None:
        self.buf = bytearray()

    def write(self, b: bytes) -> None:
        self.buf.extend(b)

    def u8(self, v: int) -> None:
        self.buf.append(v & 0xFF)

    def i8(self, v: int) -> None:
        self.buf.extend(struct.pack("<b", v))

    def u16(self, v: int) -> None:
        self.buf.extend(struct.pack("<H", v))

    def i16(self, v: int) -> None:
        self.buf.extend(struct.pack("<h", v))

    def u32(self, v: int) -> None:
        self.buf.extend(struct.pack("<I", v & 0xFFFFFFFF))

    def i32(self, v: int) -> None:
        self.buf.extend(struct.pack("<i", v))

    def u64(self, v: int) -> None:
        self.buf.extend(struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF))

    def i64(self, v: int) -> None:
        self.buf.extend(struct.pack("<q", v))

    def f32(self, v: float) -> None:
        self.buf.extend(struct.pack("<f", v))

    def f64(self, v: float) -> None:
        self.buf.extend(struct.pack("<d", v))

    def fstring(self, s: str) -> None:
        if not s:
            self.i32(0)
            return
        # Fortnite always uses ASCII for property names/types. Preserve that
        # when possible; fall back to UTF-16 for non-ASCII strings.
        if all(ord(c) < 128 for c in s):
            data = s.encode("latin-1") + b"\x00"
            self.i32(len(data))
            self.buf.extend(data)
        else:
            data = s.encode("utf-16-le") + b"\x00\x00"
            self.i32(-(len(s) + 1))
            self.buf.extend(data)


# ---------------------------------------------------------------------------
# FPropertyTypeName + FPropertyTag
# ---------------------------------------------------------------------------


class TagFlag:
    NONE = 0x00
    HAS_ARRAY_INDEX = 0x01
    HAS_PROPERTY_GUID = 0x02
    HAS_PROPERTY_EXTENSIONS = 0x04
    HAS_BINARY_OR_NATIVE_SERIALIZE = 0x08
    BOOL_TRUE = 0x10
    SKIPPED_SERIALIZE = 0x20


@dataclass
class TypeName:
    name: str
    params: list["TypeName"] = field(default_factory=list)

    @classmethod
    def read(cls, r: Reader) -> "TypeName":
        name = r.fstring()
        n = r.i32()
        if n < 0 or n > 64:
            raise ValueError(f"bogus TypeName param count {n} at 0x{r.pos - 4:x}")
        params = [cls.read(r) for _ in range(n)]
        return cls(name=name, params=params)

    def write(self, w: Writer) -> None:
        w.fstring(self.name)
        w.i32(len(self.params))
        for p in self.params:
            p.write(w)

    @property
    def struct_name(self) -> str | None:
        return self.params[0].name if self.params else None

    def to_json(self) -> Any:
        if not self.params:
            return self.name
        return {"name": self.name, "params": [p.to_json() for p in self.params]}

    @classmethod
    def from_json(cls, obj: Any) -> "TypeName":
        if isinstance(obj, str):
            return cls(name=obj)
        return cls(
            name=obj["name"],
            params=[cls.from_json(p) for p in obj.get("params", [])],
        )


@dataclass
class PropertyTag:
    name: str
    type_name: TypeName
    flags: int
    array_index: int = 0
    property_guid: bytes | None = None
    extension_payload: bytes = b""
    bool_value: bool = False

    @classmethod
    def read(cls, r: Reader) -> "PropertyTag | None":
        name = r.fstring()
        if name == "None":
            return None
        tn = TypeName.read(r)
        size = r.i32()
        flags = r.u8()

        array_index = 0
        if flags & TagFlag.HAS_ARRAY_INDEX:
            array_index = r.i32()

        guid: bytes | None = None
        if flags & TagFlag.HAS_PROPERTY_GUID:
            guid = r.guid()

        ext_payload = b""
        if flags & TagFlag.HAS_PROPERTY_EXTENSIONS:
            ext_flags = r.u8()
            if ext_flags & 0x01:
                ext_payload = bytes([ext_flags, r.u8()])
            else:
                ext_payload = bytes([ext_flags])

        bool_value = bool(flags & TagFlag.BOOL_TRUE)

        tag = cls(
            name=name,
            type_name=tn,
            flags=flags,
            array_index=array_index,
            property_guid=guid,
            extension_payload=ext_payload,
            bool_value=bool_value,
        )
        tag._value_size = size  # only used during parsing
        return tag

    def write_name_and_type(self, w: Writer) -> int:
        """Write Name + TypeName. Returns offset where Size int32 will go."""
        w.fstring(self.name)
        self.type_name.write(w)
        size_offset = len(w.buf)
        w.i32(0)  # placeholder; patched by caller once value is written
        return size_offset

    def write_trailing_flags(self, w: Writer) -> None:
        """Write Flags + (optional) ArrayIndex/Guid/Extensions."""
        w.u8(self.flags & 0xFF)
        if self.flags & TagFlag.HAS_ARRAY_INDEX:
            w.i32(self.array_index)
        if self.flags & TagFlag.HAS_PROPERTY_GUID:
            if self.property_guid is None:
                raise ValueError("HAS_PROPERTY_GUID set but no guid")
            w.write(self.property_guid)
        if self.flags & TagFlag.HAS_PROPERTY_EXTENSIONS:
            w.write(self.extension_payload)


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


HARDCODED_STRUCTS = {"Vector2D", "DateTime", "Guid", "GameplayTagContainer"}


def _read_hardcoded_struct(r: Reader, struct_name: str) -> dict:
    if struct_name == "Vector2D":
        return {"__struct__": "Vector2D", "X": r.f64(), "Y": r.f64()}
    if struct_name == "DateTime":
        return {"__struct__": "DateTime", "ticks": r.i64()}
    if struct_name == "Guid":
        return {"__struct__": "Guid", "guid": r.guid().hex()}
    if struct_name == "GameplayTagContainer":
        # int32 NumTags + FString*NumTags (native binary serialize)
        n = r.i32()
        if n < 0 or n > 10000:
            raise ValueError(f"absurd GameplayTagContainer count {n}")
        return {"__struct__": "GameplayTagContainer", "Tags": [r.fstring() for _ in range(n)]}
    raise ValueError(f"unknown hardcoded struct: {struct_name}")


def _write_hardcoded_struct(w: Writer, struct_name: str, value: dict) -> None:
    if struct_name == "Vector2D":
        w.f64(float(value["X"])); w.f64(float(value["Y"]))
        return
    if struct_name == "DateTime":
        w.i64(int(value["ticks"]))
        return
    if struct_name == "Guid":
        raw = value["guid"]
        w.write(bytes.fromhex(raw) if isinstance(raw, str) else raw)
        return
    if struct_name == "GameplayTagContainer":
        tags = value["Tags"]
        w.i32(len(tags))
        for t in tags:
            w.fstring(t)
        return
    raise ValueError(f"unknown hardcoded struct: {struct_name}")


@dataclass
class Property:
    """One top-level (or child) property: tag + value."""
    tag: PropertyTag
    value: Any  # python-native for scalars; Property lists for struct/array


@dataclass
class NestedSave:
    """PartitionContents byte arrays that are themselves save streams."""
    header_bytes: bytes
    properties: list[Property]
    trailing: bytes = b""  # bytes after the "None" terminator (usually small padding)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------


FORMAT_MAGIC_40_20 = 0xA2189DE9


def _read_scalar(r: Reader, tn: TypeName) -> Any:
    t = tn.name
    if t == "IntProperty":
        return r.i32()
    if t == "UInt32Property":
        return r.u32()
    if t == "Int64Property":
        return r.i64()
    if t == "UInt64Property":
        return r.u64()
    if t == "Int16Property":
        return r.i16()
    if t == "UInt16Property":
        return r.u16()
    if t == "Int8Property":
        return r.i8()
    if t == "ByteProperty":
        # With an enum param the value is an FString; without it's a raw byte.
        if tn.params:
            return r.fstring()
        return r.u8()
    if t == "EnumProperty":
        return r.fstring()
    if t == "FloatProperty":
        return r.f32()
    if t == "DoubleProperty":
        return r.f64()
    if t == "BoolProperty":
        # Top-level BoolProperty lives in the tag's BOOL_TRUE flag (no value
        # bytes). Inside a Map/Set/Array, BoolProperty is a single byte.
        return bool(r.u8())
    if t == "NameProperty":
        return r.fstring()
    if t == "StrProperty":
        return r.fstring()
    if t == "TextProperty":
        return _read_text(r)
    if t == "ObjectProperty":
        return r.fstring()
    if t == "SoftObjectProperty":
        return r.fstring()
    if t == "StructProperty":
        return _read_struct(r, tn)
    raise ValueError(f"unsupported scalar type {t}")


def _read_text(r: Reader) -> dict:
    flags = r.i32()
    history = r.u8()
    if history == 0xFF:
        return {"history": "None", "flags": flags}
    if history != 0:
        return {"history": f"unsupported={history}", "flags": flags}
    return {
        "history": "Base",
        "flags": flags,
        "namespace": r.fstring(),
        "key": r.fstring(),
        "source": r.fstring(),
    }


def _read_struct(r: Reader, tn: TypeName) -> Any:
    struct_name = tn.struct_name
    if struct_name in HARDCODED_STRUCTS:
        return _read_hardcoded_struct(r, struct_name)
    # Generic: a run of tagged properties ending in "None"
    props = _read_tagged_body(r, context=f"struct[{struct_name}]")
    return {"__struct__": struct_name, "__props__": props}


def _read_array(r: Reader, tn: TypeName) -> Any:
    n = r.i32()
    inner = tn.params[0] if tn.params else TypeName(name="")

    if inner.name == "ByteProperty":
        payload = r.read(n)
        nested = _try_parse_nested_save(payload)
        if nested is not None:
            return {"__byte_array__": True, "nested_save": nested}
        return {"__byte_array__": True, "bytes": payload}

    if inner.name == "StructProperty":
        items = []
        for _ in range(n):
            items.append(_read_struct(r, inner))
        return {"__array__": True, "inner_type": inner, "items": items}

    items = []
    for _ in range(n):
        if inner.name == "BoolProperty":
            items.append(bool(r.u8()))
        else:
            items.append(_read_scalar(r, inner))
    return {"__array__": True, "inner_type": inner, "items": items}


def _read_tagged_body(r: Reader, context: str = "") -> list[Property]:
    out: list[Property] = []
    while True:
        tag_offset = r.pos
        try:
            tag = PropertyTag.read(r)
        except Exception as e:
            raise ValueError(
                f"[{context}] tag-read failed at 0x{tag_offset:x}: {e}. "
                f"Last successful props: {[p.tag.name for p in out[-5:]]}"
            ) from e
        if tag is None:
            return out

        value_bytes = r.read(getattr(tag, "_value_size"))
        if tag.type_name.name == "BoolProperty":
            out.append(Property(tag=tag, value=tag.bool_value))
            continue

        sub = Reader(value_bytes)
        if tag.type_name.name == "ArrayProperty":
            value = _read_array(sub, tag.type_name)
        elif tag.type_name.name == "SetProperty":
            sub.i32()  # ElementsToRemove
            inner = tag.type_name.params[0] if tag.type_name.params else TypeName(name="")
            k = sub.i32()
            value = {
                "__set__": True,
                "inner_type": inner,
                "items": [_read_scalar(sub, inner) for _ in range(k)],
            }
        elif tag.type_name.name == "MapProperty":
            sub.i32()  # NumKeysToRemove
            kn = tag.type_name.params[0] if len(tag.type_name.params) > 0 else TypeName("")
            vn = tag.type_name.params[1] if len(tag.type_name.params) > 1 else TypeName("")
            k = sub.i32()
            entries: list[dict] = []
            for i in range(k):
                try:
                    key_val = _read_scalar(sub, kn)
                    val_val = _read_scalar(sub, vn)
                    entries.append({"key": key_val, "value": val_val})
                except Exception as e:
                    raise ValueError(
                        f"Map '{tag.name}' entry {i}/{k} failed "
                        f"(key_type={kn.to_json()}, value_type={vn.to_json()}): {e}. "
                        f"Value sub-reader at 0x{sub.pos:x}, peek: {sub.data[sub.pos:sub.pos+32].hex()}"
                    ) from e
            value = {
                "__map__": True,
                "key_type": kn,
                "value_type": vn,
                "entries": entries,
            }
        elif tag.type_name.name == "StructProperty":
            value = _read_struct(sub, tag.type_name)
        else:
            value = _read_scalar(sub, tag.type_name)

        if sub.remaining() > 0:
            # Keep unknown trailing bytes so we can round-trip them.
            value = {"__value__": value, "__trailing__": sub.data[sub.pos:]}
        out.append(Property(tag=tag, value=value))


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _write_scalar(w: Writer, tn: TypeName, value: Any) -> None:
    t = tn.name
    if t == "IntProperty":
        w.i32(int(value))
    elif t == "UInt32Property":
        w.u32(int(value))
    elif t == "Int64Property":
        w.i64(int(value))
    elif t == "UInt64Property":
        w.u64(int(value))
    elif t == "Int16Property":
        w.i16(int(value))
    elif t == "UInt16Property":
        w.u16(int(value))
    elif t == "Int8Property":
        w.i8(int(value))
    elif t == "ByteProperty":
        if tn.params:
            w.fstring(str(value))
        else:
            w.u8(int(value))
    elif t == "EnumProperty":
        w.fstring(str(value))
    elif t == "BoolProperty":
        # Inline bool inside Map/Set/Array — single byte.
        w.u8(1 if value else 0)
    elif t == "FloatProperty":
        w.f32(float(value))
    elif t == "DoubleProperty":
        w.f64(float(value))
    elif t == "NameProperty" or t == "StrProperty" or t == "ObjectProperty" or t == "SoftObjectProperty":
        w.fstring(str(value))
    elif t == "TextProperty":
        _write_text(w, value)
    elif t == "StructProperty":
        _write_struct(w, tn, value)
    else:
        raise ValueError(f"unsupported scalar type for write: {t}")


def _write_text(w: Writer, value: dict) -> None:
    w.i32(int(value.get("flags", 0)))
    history = value.get("history", "None")
    if history == "None":
        w.u8(0xFF)
        return
    if history != "Base":
        raise ValueError(f"unsupported text history for write: {history}")
    w.u8(0)
    w.fstring(value.get("namespace", ""))
    w.fstring(value.get("key", ""))
    w.fstring(value.get("source", ""))


def _write_struct(w: Writer, tn: TypeName, value: Any) -> None:
    struct_name = tn.struct_name
    if struct_name in HARDCODED_STRUCTS:
        _write_hardcoded_struct(w, struct_name, value)
        return
    props = value["__props__"]
    _write_tagged_body(w, props)


def _write_array(w: Writer, tn: TypeName, value: Any) -> None:
    if value.get("__byte_array__"):
        if "nested_save" in value:
            nested_bytes = _serialize_save_stream(value["nested_save"])
            w.i32(len(nested_bytes))
            w.write(nested_bytes)
        else:
            raw = value["bytes"]
            w.i32(len(raw))
            w.write(raw)
        return

    inner = value.get("inner_type") or (tn.params[0] if tn.params else TypeName(""))
    if isinstance(inner, dict) or isinstance(inner, str):
        inner = TypeName.from_json(inner)
    items = value["items"]
    w.i32(len(items))
    if inner.name == "StructProperty":
        for it in items:
            _write_struct(w, inner, it)
    elif inner.name == "BoolProperty":
        for it in items:
            w.u8(1 if it else 0)
    else:
        for it in items:
            _write_scalar(w, inner, it)


def _write_tagged_body(w: Writer, props: list[Property]) -> None:
    for p in props:
        _write_property(w, p)
    # terminator
    w.fstring("None")


def _write_property(w: Writer, p: Property) -> None:
    tag = p.tag

    # BoolProperty has no value bytes; bool value lives in the flags.
    if tag.type_name.name == "BoolProperty":
        new_flags = tag.flags & ~TagFlag.BOOL_TRUE
        if bool(p.value):
            new_flags |= TagFlag.BOOL_TRUE
        tag.flags = new_flags
        size_offset = tag.write_name_and_type(w)
        tag.write_trailing_flags(w)
        # Patch size = 0
        struct.pack_into("<i", w.buf, size_offset, 0)
        return

    size_offset = tag.write_name_and_type(w)
    tag.write_trailing_flags(w)

    value_start = len(w.buf)

    value = p.value
    trailing = b""
    if isinstance(value, dict) and "__trailing__" in value:
        trailing = value["__trailing__"]
        value = value["__value__"]

    if tag.type_name.name == "ArrayProperty":
        _write_array(w, tag.type_name, value)
    elif tag.type_name.name == "SetProperty":
        inner = value.get("inner_type") or (tag.type_name.params[0] if tag.type_name.params else TypeName(""))
        if isinstance(inner, dict) or isinstance(inner, str):
            inner = TypeName.from_json(inner)
        w.i32(0)  # ElementsToRemove
        items = value["items"]
        w.i32(len(items))
        for it in items:
            _write_scalar(w, inner, it)
    elif tag.type_name.name == "MapProperty":
        kn = value.get("key_type") or (tag.type_name.params[0] if tag.type_name.params else TypeName(""))
        vn = value.get("value_type") or (tag.type_name.params[1] if len(tag.type_name.params) > 1 else TypeName(""))
        if isinstance(kn, (dict, str)):
            kn = TypeName.from_json(kn)
        if isinstance(vn, (dict, str)):
            vn = TypeName.from_json(vn)
        w.i32(0)  # NumKeysToRemove
        entries = value["entries"]
        w.i32(len(entries))
        for e in entries:
            _write_scalar(w, kn, e["key"])
            _write_scalar(w, vn, e["value"])
    elif tag.type_name.name == "StructProperty":
        _write_struct(w, tag.type_name, value)
    else:
        _write_scalar(w, tag.type_name, value)

    if trailing:
        w.write(trailing)

    value_end = len(w.buf)
    struct.pack_into("<i", w.buf, size_offset, value_end - value_start)


# ---------------------------------------------------------------------------
# Save stream (header + body)
# ---------------------------------------------------------------------------


@dataclass
class SaveStream:
    """A full parsed save stream = opaque header + parsed property body."""
    header_bytes: bytes                      # everything before first property tag
    properties: list[Property]
    trailing: bytes                          # bytes after the "None" terminator


def _looks_like_property_tag(data: bytes, pos: int) -> bool:
    """Does `pos` point at a plausible FPropertyTag or bare 'None' terminator?"""
    if pos + 8 > len(data):
        return False
    try:
        n = struct.unpack_from("<i", data, pos)[0]
    except struct.error:
        return False
    if not (2 <= n <= 200):
        return False
    if pos + 4 + n > len(data):
        return False
    name_bytes = data[pos + 4 : pos + 4 + n]
    if name_bytes[-1] != 0:
        return False
    name = name_bytes[:-1]
    if not all(0x20 <= b < 0x7F for b in name):
        return False
    if not (chr(name[0]).isalpha() or name[0] == ord("_")):
        return False
    if name == b"None":
        return True
    type_pos = pos + 4 + n
    if type_pos + 8 > len(data):
        return False
    tn = struct.unpack_from("<i", data, type_pos)[0]
    if not (6 <= tn <= 60):
        return False
    if type_pos + 4 + tn > len(data):
        return False
    type_bytes = data[type_pos + 4 : type_pos + 4 + tn]
    if type_bytes[-1] != 0:
        return False
    type_str = type_bytes[:-1].decode("latin-1", errors="replace")
    return type_str.endswith("Property")


def _locate_body_start(data: bytes, scan_from: int) -> int:
    limit = min(len(data) - 9, scan_from + 128 * 1024)
    for off in range(scan_from, limit + 1):
        if _looks_like_property_tag(data, off):
            return off
    raise ValueError(f"could not locate property body after 0x{scan_from:x}")


def _parse_save_stream(stream: bytes) -> SaveStream:
    r = Reader(stream)

    # Validate header is the new (UE5-era) format. We don't care about the
    # specific values — we just need to know where the property body starts.
    r.u32()  # format_magic
    r.u32()  # ue4
    r.u32()  # ue5
    r.u16(); r.u16(); r.u16(); r.u32()  # engine version + changelist

    branch = r.fstring()
    r.i32()  # post_branch_value

    if not branch.startswith("++Fortnite+Release-"):
        raise ValueError(f"not a Fortnite save stream (branch={branch!r})")

    # Confirm UE5-era: engine major >= 5. We need the UE5 flag byte layout.
    ue5_major = struct.unpack_from("<H", stream, 12)[0]
    if ue5_major < 5:
        raise ValueError(
            f"old UE4 save format (engine {ue5_major}.x) not supported for write "
            "— this parser only handles UE5-era (Fortnite 27+) saves"
        )

    body_start = _locate_body_start(stream, r.pos)
    header = stream[:body_start]

    r.pos = body_start
    props = _read_tagged_body(r)

    trailing = stream[r.pos:]
    return SaveStream(header_bytes=header, properties=props, trailing=trailing)


def _serialize_save_stream(stream: SaveStream) -> bytes:
    w = Writer()
    w.write(stream.header_bytes)
    _write_tagged_body(w, stream.properties)
    w.write(stream.trailing)
    return bytes(w.buf)


def _try_parse_nested_save(blob: bytes) -> SaveStream | None:
    """PartitionContents byte arrays are themselves save streams."""
    if len(blob) < 32:
        return None
    try:
        ue4 = struct.unpack_from("<I", blob, 4)[0]
        ue5 = struct.unpack_from("<I", blob, 8)[0]
        if not (400 <= ue4 <= 800):
            return None
        if not (800 <= ue5 <= 3000):
            return None
        branch_len = struct.unpack_from("<i", blob, 22)[0]
        if not (4 <= branch_len <= 200):
            return None
        branch = blob[26 : 26 + branch_len - 1]
        if not branch.startswith(b"++"):
            return None
    except struct.error:
        return None

    try:
        return _parse_save_stream(blob)
    except Exception as e:
        logger.debug("nested-save parse failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# ECFD outer envelope
# ---------------------------------------------------------------------------


@dataclass
class ClientSettingsFile:
    """Full parsed ClientSettings.Sav, preserving enough to round-trip."""
    stream: SaveStream
    ecfd_compressed_flags: int | None = None  # bytes 0x04-0x07 of ECFD header
    ecfd_version: int | None = None           # bytes 0x08-0x0b
    was_compressed: bool = False

    @property
    def properties(self) -> list[Property]:
        return self.stream.properties


def _has_ecfd_wrapper(data: bytes) -> bool:
    return data[:4] == b"ECFD"


def parse_file(data: bytes) -> ClientSettingsFile:
    if _has_ecfd_wrapper(data):
        flags = struct.unpack_from("<I", data, 4)[0]
        version = struct.unpack_from("<I", data, 8)[0]
        # data[12:16] is uncompressed_size; we recompute on serialize
        raw = zlib.decompress(data[0x10:])
        stream = _parse_save_stream(raw)
        return ClientSettingsFile(
            stream=stream,
            ecfd_compressed_flags=flags,
            ecfd_version=version,
            was_compressed=True,
        )
    stream = _parse_save_stream(data)
    return ClientSettingsFile(stream=stream, was_compressed=False)


def serialize_file(f: ClientSettingsFile) -> bytes:
    body = _serialize_save_stream(f.stream)
    if not f.was_compressed:
        return body
    # zlib-compress with max compression (matches Fortnite's 0x78 0xDA output).
    compressed = zlib.compress(body, level=9)
    w = Writer()
    w.write(b"ECFD")
    w.u32(f.ecfd_compressed_flags if f.ecfd_compressed_flags is not None else 0)
    w.u32(f.ecfd_version if f.ecfd_version is not None else 1)
    w.u32(len(body))
    w.write(compressed)
    return bytes(w.buf)


# ---------------------------------------------------------------------------
# Convenience accessors
# ---------------------------------------------------------------------------


def find_property(props: list[Property], name: str) -> Property | None:
    for p in props:
        if p.tag.name == name:
            return p
    return None


def get_value(props: list[Property], name: str) -> Any:
    p = find_property(props, name)
    return p.value if p is not None else None


def set_value(props: list[Property], name: str, new_value: Any) -> bool:
    """Replace the scalar value of a named property. Returns True if it was found."""
    p = find_property(props, name)
    if p is None:
        return False
    if isinstance(p.value, dict) and "__trailing__" in p.value:
        p.value = {"__value__": new_value, "__trailing__": p.value["__trailing__"]}
    else:
        p.value = new_value
    return True


# ---------------------------------------------------------------------------
# JSON helpers (human-readable dump)
# ---------------------------------------------------------------------------


def _value_to_json(value: Any) -> Any:
    if isinstance(value, Property):
        return {"name": value.tag.name, "type": value.tag.type_name.to_json(), "value": _value_to_json(value.value)}
    if isinstance(value, list):
        return [_value_to_json(v) for v in value]
    if isinstance(value, dict):
        if value.get("__byte_array__"):
            if "nested_save" in value:
                return {"nested_save": _stream_to_json(value["nested_save"])}
            return {"bytes_hex": value["bytes"].hex(), "bytes_len": len(value["bytes"])}
        if value.get("__array__"):
            return {
                "inner_type": value["inner_type"].to_json() if isinstance(value["inner_type"], TypeName) else value["inner_type"],
                "items": [_value_to_json(i) for i in value["items"]],
            }
        if value.get("__set__"):
            return {
                "inner_type": value["inner_type"].to_json() if isinstance(value["inner_type"], TypeName) else value["inner_type"],
                "items": [_value_to_json(i) for i in value["items"]],
            }
        if value.get("__map__"):
            return {
                "key_type": value["key_type"].to_json() if isinstance(value["key_type"], TypeName) else value["key_type"],
                "value_type": value["value_type"].to_json() if isinstance(value["value_type"], TypeName) else value["value_type"],
                "entries": [{"key": _value_to_json(e["key"]), "value": _value_to_json(e["value"])} for e in value["entries"]],
            }
        if "__struct__" in value:
            struct_name = value["__struct__"]
            if struct_name in HARDCODED_STRUCTS:
                out = {"__struct__": struct_name}
                out.update({k: v for k, v in value.items() if k != "__struct__"})
                return out
            return {
                "__struct__": struct_name,
                "props": {p.tag.name: _value_to_json(p.value) for p in value["__props__"]},
            }
        if "__value__" in value:
            return {"__value__": _value_to_json(value["__value__"]), "__trailing__": value["__trailing__"].hex()}
        return value
    if isinstance(value, bytes):
        return value.hex()
    return value


def _stream_to_json(stream: SaveStream) -> dict:
    return {
        "header_size": len(stream.header_bytes),
        "trailing_size": len(stream.trailing),
        "properties": {p.tag.name: _value_to_json(p.value) for p in stream.properties},
    }


def to_json(f: ClientSettingsFile) -> dict:
    return {
        "was_compressed": f.was_compressed,
        **_stream_to_json(f.stream),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Parse/serialize Fortnite ClientSettings.Sav")
    ap.add_argument("input", help="Path to ClientSettings.Sav")
    ap.add_argument("-o", "--output", help="Output path (JSON unless --rewrite)")
    ap.add_argument("--rewrite", action="store_true",
                    help="Parse then re-serialize as .Sav to verify round-trip.")
    args = ap.parse_args(argv)

    with open(args.input, "rb") as f:
        data = f.read()

    parsed = parse_file(data)

    if args.rewrite:
        re = serialize_file(parsed)
        dst = args.output or (args.input + ".round-trip.sav")
        with open(dst, "wb") as f:
            f.write(re)
        same = re == data
        print(f"Wrote {len(re)} bytes to {dst}. byte-identical={same}", file=sys.stderr)
        if not same:
            # Show where they diverge
            for i in range(min(len(re), len(data))):
                if re[i] != data[i]:
                    print(f"  first diff at offset 0x{i:x}: orig={data[i]:#x} vs new={re[i]:#x}", file=sys.stderr)
                    break
            if len(re) != len(data):
                print(f"  length diff: orig={len(data)} new={len(re)}", file=sys.stderr)
        return 0 if same else 1

    doc = to_json(parsed)
    text = json.dumps(doc, indent=2, default=str)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    raise SystemExit(main())
