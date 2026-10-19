"""A small made-up ClientSettings.Sav in the game's format, for tests and the UI's fake core.

It has a few settings of each kind the editor handles (on/off, a number, a choice, volumes,
keyboard bindings, mouse sensitivity), a struct, a partition holding a nested save, and a value
stored in binary that the reader keeps as raw bytes. No real account's settings are in the repository.
"""
from __future__ import annotations

import io
import struct

from lib.utilities.client_settings import (Array, FStr, MapValue, NATIVE_SERIALIZE, Prop, Raw, Save,
                                           SAVE_MAGIC, SettingsFile, Struct, TypeName, _write_fstring)


def header() -> bytes:
    out = io.BytesIO()
    out.write(SAVE_MAGIC)
    out.write(struct.pack('<iii', 522, 1018, 6))
    out.write(struct.pack('<H', 0))
    out.write(struct.pack('<i', 59086525))
    _write_fstring(out, FStr('++Fortnite+Release-42.40', False))
    out.write(struct.pack('<i', 95))
    out.write(bytes([1, 3]))
    out.write(struct.pack('<i', 1))                      # one custom version
    out.write(bytes(range(16)) + struct.pack('<i', 44))
    out.write(b'\0')
    return out.getvalue()


def _name(text: str) -> FStr:
    return FStr(text, False)


FG = '/Script/FortniteGame'


def _enum(enum: str) -> TypeName:
    return TypeName('EnumProperty', [TypeName(enum, [TypeName(FG)]), TypeName('ByteProperty')])


def _key(name: str) -> Struct:
    return Struct('Key', [Prop(_name('KeyName'), TypeName('NameProperty'), 0, _name(name))])


def _mapping(action: str, group: str, key1: str, key2: str = 'None', scale: float = 1.0, axis: bool = False) -> Struct:
    key_type = TypeName('StructProperty', [TypeName('Key', [TypeName('/Script/InputCore')])])
    return Struct('FortActionKeyMapping', [
        Prop(_name('ActionName'), TypeName('NameProperty'), 0, _name(action)),
        Prop(_name('ActionGroup'), _enum('EFortInputActionGroup'), 0, _name('EFortInputActionGroup::' + group)),
        Prop(_name('SubGameUsedIn'), _enum('ESubGame'), 0, _name('ESubGame::Invalid')),
        Prop(_name('KeyBind1'), key_type, 0, _key(key1)),
        Prop(_name('KeyBind2'), key_type, 0, _key(key2)),
        Prop(_name('InputScale'), TypeName('FloatProperty'), 0, scale),
        Prop(_name('bIsAxisMapping'), TypeName('BoolProperty'), 0x10 if axis else 0, axis),
    ])


def bindings() -> Prop:
    """Keyboard bindings: the menu's list (Athena) and the shared list (Invalid), as the game keeps them."""
    def actions():
        return Struct('UserActionBindings', [Prop(_name('UserActionBindings'), TypeName('ArrayProperty', [
            TypeName('StructProperty', [TypeName('FortActionKeyMapping', [TypeName(FG)])])]), 0, Array([
                _mapping('MoveForward', 'Movement', 'W', 'Up', 1.0, True),
                _mapping('MoveForward', 'Movement', 'S', 'Down', -1.0, True),
                _mapping('Reload', 'Combat', 'R'),
                _mapping('Use', 'CombatAndAthenaLTMAbilities', 'E'),
                _mapping('GamepadResetCamera', 'AllModes', 'None'),
            ]))])
    value = MapValue([(_name('ESubGame::Invalid'), actions()), (_name('ESubGame::Athena'), actions())], [])
    return Prop(_name('UserBindingsPerSubGame'), TypeName('MapProperty', [
        _enum('ESubGame'), TypeName('StructProperty', [TypeName('UserActionBindings', [TypeName(FG)])])]), 0, value)


def sample_save() -> Save:
    partition = Save(header(), [Prop(_name('bHasAvailableAudioInputDevices'), TypeName('BoolProperty'), 0x10, True)],
                     b'')
    schema = Struct('FortClientSettingRecordPartitionSchema', [
        Prop(_name('PartitionVersion'), TypeName('IntProperty'), 0, 0),
        Prop(_name('ResolvingPartitionName'), TypeName('NameProperty'), 0, _name('PilgrimPartition')),
        Prop(_name('PartitionContents'), TypeName('ArrayProperty', [TypeName('ByteProperty')]), 0, partition),
    ])
    volumes = MapValue([(_name('CB_Slider_Main'), 1.0), (_name('CB_Slider_Music'), 0.5),
                        (_name('CB_Slider_Chat'), 0.23)], [])
    props = [
        Prop(_name('SettingRecordPartitionSchemas'), TypeName('ArrayProperty', [TypeName('StructProperty', [
            TypeName('FortClientSettingRecordPartitionSchema', [TypeName('/Script/FortniteGame')])])]), 0,
             Array([schema])),
        Prop(_name('BusNameVolumesMap'), TypeName('MapProperty', [TypeName('NameProperty'), TypeName('FloatProperty')]),
             0, volumes),
        Prop(_name('MouseSensitivityX'), TypeName('FloatProperty'), 0, 0.0025),
        Prop(_name('UpgradedMouseSensitivityX'), TypeName('FloatProperty'), 0, 0.0025),
        Prop(_name('TargetingSlow'), TypeName('FloatProperty'), 0, 0.87),
        bindings(),
        Prop(_name('bToggleSprint'), TypeName('BoolProperty'), 0x10, True),
        Prop(_name('bTargetingToggleable'), TypeName('BoolProperty'), 0, False),
        Prop(_name('CombatTweakZone'), TypeName('EnumProperty', [
            TypeName('EActiveCombatMode', [TypeName('/Script/FortniteGame')]), TypeName('ByteProperty')]), 0,
             _name('EActiveCombatMode::All')),
        Prop(_name('ControllerPlatform'), TypeName('StrProperty'), 0, _name('XboxOne')),
        Prop(_name('SeenOnboardingTutorials'), TypeName('StructProperty', [
            TypeName('GameplayTagContainer', [TypeName('/Script/GameplayTags')])]), NATIVE_SERIALIZE,
             Raw(b'\x01\x00\x00\x00\x05\x00\x00\x00Tag1\x00')),
    ]
    return Save(header(), props, b'\0\0\0\0')


def sample_bytes(wrapped: bool = True) -> bytes:
    return SettingsFile(sample_save(), (0xF619, 1) if wrapped else None).to_bytes()
