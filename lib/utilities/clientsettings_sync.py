"""
High-level ClientSettings.Sav manager for FA11y.

Ties together the parser/serializer (:mod:`clientsettings_parser`) and the
cloud storage client (:mod:`clientsettings_cloud`) to provide a small
practical API for the features FA11y needs:

    - locate local ClientSettings.Sav files (the in-use copy in
      Saved/Config/ as well as per-slot Cloud copies)
    - fetch the cloud copy from the authenticated Epic account
    - compare local vs cloud (a short structured diff)
    - push local -> cloud (so a device's settings become the canonical copy)
    - pull cloud -> local (so this device picks up settings from another)
    - query and mutate keybinds via action name, then re-serialize + upload

The file is locked while Fortnite is running, so local writes are gated on
the game being closed. The cloud sync itself is unaffected by the game.
"""

from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from lib.utilities.clientsettings_cloud import CloudStorage, CloudStorageError
from lib.utilities.clientsettings_parser import (
    ClientSettingsFile,
    Property,
    TypeName,
    find_property,
    get_value,
    parse_file,
    serialize_file,
    set_value,
)
from lib.utilities.epic_auth import EpicAuth

logger = logging.getLogger(__name__)


CLIENT_SETTINGS_FILENAME = "ClientSettings.Sav"


# ---------------------------------------------------------------------------
# Local file discovery
# ---------------------------------------------------------------------------


@dataclass
class LocalClientSettings:
    """Where ClientSettings.Sav lives on this machine."""
    config_path: Path                 # %LOCALAPPDATA%/FortniteGame/Saved/Config/ClientSettings.Sav
    cloud_slot_paths: list[Path] = field(default_factory=list)  # .../Cloud/<slotid>/ClientSettings.Sav

    @property
    def primary(self) -> Path:
        """The file to read/write. Prefers Config/, falls back to a Cloud slot."""
        if self.config_path.exists():
            return self.config_path
        for p in self.cloud_slot_paths:
            if p.exists():
                return p
        return self.config_path  # may not exist


def locate_local() -> LocalClientSettings:
    """Find the local Fortnite save folders. Doesn't require the game to run."""
    localappdata = os.environ.get("LOCALAPPDATA")
    if not localappdata:
        raise RuntimeError("LOCALAPPDATA env var not set")

    base = Path(localappdata) / "FortniteGame" / "Saved"
    config_file = base / "Config" / CLIENT_SETTINGS_FILENAME

    cloud_files: list[Path] = []
    cloud_dir = base / "Cloud"
    if cloud_dir.is_dir():
        for slot in sorted(cloud_dir.iterdir()):
            if slot.is_dir():
                f = slot / CLIENT_SETTINGS_FILENAME
                if f.exists():
                    cloud_files.append(f)

    return LocalClientSettings(config_path=config_file, cloud_slot_paths=cloud_files)


def is_fortnite_running() -> bool:
    """Cheap best-effort check — looks for FortniteClient-Win64-Shipping.exe."""
    try:
        import psutil  # type: ignore
    except ImportError:
        return False
    for p in psutil.process_iter(["name"]):
        try:
            name = p.info.get("name") or ""
            if name.lower().startswith("fortniteclient-win64"):
                return True
        except Exception:
            continue
    return False


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


@dataclass
class SettingsDiff:
    only_local: list[str]
    only_cloud: list[str]
    different: list[dict]    # [{name, local, cloud}]

    def is_empty(self) -> bool:
        return not (self.only_local or self.only_cloud or self.different)

    def summary(self) -> str:
        lines = []
        if self.only_local:
            lines.append(f"only local: {len(self.only_local)}")
        if self.only_cloud:
            lines.append(f"only cloud: {len(self.only_cloud)}")
        if self.different:
            lines.append(f"different:  {len(self.different)}")
        if not lines:
            return "local and cloud are identical"
        return " / ".join(lines)


def _simplify(value: Any) -> Any:
    """Collapse parser-internal dict shapes into something diff-friendly."""
    if isinstance(value, dict):
        if "__value__" in value:
            return _simplify(value["__value__"])
        if value.get("__byte_array__"):
            if "nested_save" in value:
                n = value["nested_save"]
                return {"__nested_save__": {p.tag.name: _simplify(p.value) for p in n.properties}}
            return {"__bytes_len__": len(value["bytes"])}
        if value.get("__array__"):
            return [_simplify(i) for i in value["items"]]
        if value.get("__set__"):
            return [_simplify(i) for i in value["items"]]
        if value.get("__map__"):
            return [{"key": _simplify(e["key"]), "value": _simplify(e["value"])} for e in value["entries"]]
        if "__struct__" in value:
            sname = value["__struct__"]
            if sname in ("Vector2D", "DateTime", "Guid", "GameplayTagContainer"):
                return {k: v for k, v in value.items() if k != "__struct__"} | {"__struct__": sname}
            return {p.tag.name: _simplify(p.value) for p in value.get("__props__", [])}
        return value
    if isinstance(value, bytes):
        return value.hex()
    return value


def diff_settings(a: ClientSettingsFile, b: ClientSettingsFile) -> SettingsDiff:
    """Return a structural diff between two parsed save files."""
    a_map = {p.tag.name: _simplify(p.value) for p in a.properties}
    b_map = {p.tag.name: _simplify(p.value) for p in b.properties}

    only_a = sorted(k for k in a_map if k not in b_map)
    only_b = sorted(k for k in b_map if k not in a_map)
    diffs = []
    for k in sorted(a_map.keys() & b_map.keys()):
        if a_map[k] != b_map[k]:
            diffs.append({"name": k, "local": a_map[k], "cloud": b_map[k]})
    return SettingsDiff(only_local=only_a, only_cloud=only_b, different=diffs)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------


class ClientSettingsManager:
    """Orchestrates local <-> cloud operations for ClientSettings.Sav."""

    def __init__(
        self,
        auth: Optional[EpicAuth] = None,
        local: Optional[LocalClientSettings] = None,
        cloud: Optional[CloudStorage] = None,
    ) -> None:
        self.auth = auth or EpicAuth()
        self.local = local or locate_local()
        self.cloud = cloud or CloudStorage(self.auth)

    # ------------------------------ local ----------------------------------

    def read_local(self) -> ClientSettingsFile:
        path = self.local.primary
        if not path.exists():
            raise FileNotFoundError(f"no local ClientSettings.Sav at {path}")
        return parse_file(path.read_bytes())

    def write_local(self, parsed: ClientSettingsFile, *, require_game_closed: bool = True) -> Path:
        """Serialize + write back to the primary local path. Makes a .bak first."""
        if require_game_closed and is_fortnite_running():
            raise RuntimeError(
                "Fortnite is running and holds a lock on ClientSettings.Sav — close it first."
            )
        path = self.local.primary
        data = serialize_file(parsed)
        if path.exists():
            backup = path.with_suffix(path.suffix + f".bak-{int(time.time())}")
            shutil.copy2(path, backup)
            logger.info("backed up existing save to %s", backup)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    # ------------------------------ cloud ----------------------------------

    def read_cloud(self, filename: str = CLIENT_SETTINGS_FILENAME) -> ClientSettingsFile:
        data = self.cloud.download(filename)
        return parse_file(data)

    def push_to_cloud(self, *, source: Optional[Path] = None, filename: str = CLIENT_SETTINGS_FILENAME) -> int:
        """Upload the local file (or a different path) to cloud verbatim."""
        path = Path(source) if source else self.local.primary
        if not path.exists():
            raise FileNotFoundError(f"nothing to upload at {path}")
        # Validate: parse it first so we don't upload a corrupt file.
        try:
            parse_file(path.read_bytes())
        except Exception as e:
            raise CloudStorageError(f"refused to upload — file doesn't parse: {e}") from e
        return self.cloud.upload_from_path(filename, str(path))

    def pull_from_cloud(self, *, filename: str = CLIENT_SETTINGS_FILENAME,
                        dest: Optional[Path] = None, require_game_closed: bool = True) -> Path:
        """Download cloud copy and write it over the local primary file."""
        if require_game_closed and is_fortnite_running():
            raise RuntimeError(
                "Fortnite is running and holds a lock on ClientSettings.Sav — close it first."
            )
        target = Path(dest) if dest else self.local.primary
        data = self.cloud.download(filename)
        # Validate before writing.
        parse_file(data)
        if target.exists():
            backup = target.with_suffix(target.suffix + f".bak-{int(time.time())}")
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target

    def compare(self) -> SettingsDiff:
        """Read local + cloud and return a structural diff."""
        local = self.read_local()
        cloud = self.read_cloud()
        return diff_settings(local, cloud)

    # ------------------------------ accessors -------------------------------

    @staticmethod
    def get(parsed: ClientSettingsFile, name: str) -> Any:
        return get_value(parsed.properties, name)

    @staticmethod
    def set(parsed: ClientSettingsFile, name: str, value: Any) -> bool:
        return set_value(parsed.properties, name, value)

    # ------------------------------ keybinds --------------------------------

    @staticmethod
    def _iter_bindings(parsed: ClientSettingsFile, sub_game: str | None = None) -> list[dict]:
        """Return a flat list of binding dicts from UserBindingsPerSubGame.

        If `sub_game` is provided (e.g. "ESubGame::Athena"), only return that
        group's bindings. Each dict is the parsed StructProperty value for one
        FortActionKeyMapping-like entry and can be mutated in place (then
        re-serialized).
        """
        prop = find_property(parsed.properties, "UserBindingsPerSubGame")
        if prop is None:
            return []

        # Value is a MapProperty wrapper
        container = prop.value
        if isinstance(container, dict) and container.get("__map__"):
            entries = container["entries"]
        else:
            return []

        out = []
        for e in entries:
            sg_name = e["key"]
            if sub_game is not None and sg_name != sub_game:
                continue
            # value is the struct FortUserBindingsPerSubGame-like: has UserActionBindings ArrayProperty
            sv = e["value"]
            if not isinstance(sv, dict):
                continue
            props = sv.get("__props__", [])
            user_bindings = find_property(props, "UserActionBindings")
            if user_bindings is None or not isinstance(user_bindings.value, dict):
                continue
            items = user_bindings.value.get("items", [])
            for item in items:
                if isinstance(item, dict):
                    item["__sub_game__"] = sg_name  # ephemeral hint for callers
                    out.append(item)
        return out

    @staticmethod
    def get_keybinds(parsed: ClientSettingsFile, sub_game: str = "ESubGame::Athena") -> list[dict]:
        """Return a list of {action, group, key1, key2, input_scale, is_axis}."""
        result = []
        for b in ClientSettingsManager._iter_bindings(parsed, sub_game=sub_game):
            props = b.get("__props__", [])
            def pget(name, default=None):
                p = find_property(props, name)
                return p.value if p is not None else default
            k1 = pget("KeyBind1", {})
            k2 = pget("KeyBind2", {})

            # KeyBind{1,2} is a struct with a single NameProperty "KeyName"
            def name_of(kb):
                if isinstance(kb, dict):
                    props2 = kb.get("__props__", [])
                    p = find_property(props2, "KeyName")
                    return p.value if p is not None else None
                return None

            result.append({
                "action": pget("ActionName"),
                "group": pget("ActionGroup"),
                "key1": name_of(k1),
                "key2": name_of(k2),
                "input_scale": pget("InputScale"),
                "is_axis": pget("bIsAxisMapping"),
            })
        return result

    @staticmethod
    def set_keybind(
        parsed: ClientSettingsFile,
        action: str,
        *,
        key1: str | None = None,
        key2: str | None = None,
        sub_game: str = "ESubGame::Athena",
        input_scale: float | None = None,
    ) -> int:
        """Update the named action's KeyBind1/KeyBind2 (and optionally InputScale).

        Returns the number of bindings matched (since some actions have
        multiple entries, e.g. axis mappings).
        """
        hits = 0
        for b in ClientSettingsManager._iter_bindings(parsed, sub_game=sub_game):
            props = b.get("__props__", [])
            action_prop = find_property(props, "ActionName")
            if action_prop is None or action_prop.value != action:
                continue

            if key1 is not None:
                kb1 = find_property(props, "KeyBind1")
                if kb1 is not None and isinstance(kb1.value, dict):
                    kb1_props = kb1.value.get("__props__", [])
                    kn = find_property(kb1_props, "KeyName")
                    if kn is not None:
                        kn.value = key1
            if key2 is not None:
                kb2 = find_property(props, "KeyBind2")
                if kb2 is not None and isinstance(kb2.value, dict):
                    kb2_props = kb2.value.get("__props__", [])
                    kn = find_property(kb2_props, "KeyName")
                    if kn is not None:
                        kn.value = key2
            if input_scale is not None:
                p = find_property(props, "InputScale")
                if p is not None:
                    p.value = float(input_scale)
            hits += 1
        return hits

    # ------------------------------ apply -----------------------------------

    def apply_changes(
        self,
        parsed: ClientSettingsFile,
        *,
        push_cloud: bool = True,
        write_local: bool = True,
        require_game_closed: bool = True,
    ) -> dict:
        """Persist edits: optionally write local, optionally push to cloud.

        Returns a small dict describing what happened.
        """
        out: dict[str, Any] = {}
        if write_local:
            path = self.write_local(parsed, require_game_closed=require_game_closed)
            out["local_path"] = str(path)
        if push_cloud:
            data = serialize_file(parsed)
            self.cloud.upload(CLIENT_SETTINGS_FILENAME, data)
            out["cloud_uploaded_bytes"] = len(data)
        return out
