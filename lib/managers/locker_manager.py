"""
Locker logic for FA11y, without any window code.

What the Locker shows (categories, filtering, sorting, details), what it does
(favorites through the Locker API, equipping by mouse automation in Fortnite,
loadouts) and the tables behind it. The wx view (lib/guis/locker_gui.py) and
the hub page's requests (lib/shell/handlers/locker.py) both call this.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, Dict, List, Optional, Tuple

from accessible_output2.outputs.auto import Auto

logger = logging.getLogger(__name__)
speaker = Auto()


def apply_favorite_flags(cosmetics: List[dict], favorite_ids) -> int:
    """Stamp Epic-side favorite status onto cosmetic dicts.

    favorite_ids is the set fetch_owned_cosmetics collects from the athena
    profile (bare lowercase cosmetic IDs). None means favorites haven't
    been fetched this session, so existing flags are left untouched.
    Returns the number of favorites marked.
    """
    if favorite_ids is None:
        return 0
    count = 0
    for cosmetic in cosmetics:
        fav = cosmetic.get("id", "").lower() in favorite_ids
        cosmetic["favorite"] = fav
        if fav:
            count += 1
    return count


# Map backend types to friendly names and slot info
COSMETIC_TYPE_MAP = {
    # Character cosmetics
    "AthenaCharacter": {"name": "Outfit", "category": "Character", "slot": 1},
    "AthenaBackpack": {"name": "Back Bling", "category": "Character", "slot": 2},
    "AthenaPickaxe": {"name": "Pickaxe", "category": "Character", "slot": 3},
    "AthenaGlider": {"name": "Glider", "category": "Character", "slot": 4},
    "CosmeticShoes": {"name": "Kicks", "category": "Character", "slot": 5},  # Fixed: was AthenaShoes
    "AthenaSkyDiveContrail": {"name": "Contrail", "category": "Character", "slot": 6},
    "SparksAura": {"name": "Aura", "category": "Character", "slot": None},  # New

    # Emotes and expressions
    "AthenaDance": {"name": "Emote", "category": "Emotes", "slot": None},  # Multiple slots
    "AthenaSpray": {"name": "Spray", "category": "Emotes", "slot": None},  # New
    "AthenaEmoji": {"name": "Emoji", "category": "Emotes", "slot": None},  # New
    "AthenaToy": {"name": "Toy", "category": "Emotes", "slot": None},  # New

    # Sidekicks/Pets (all consolidated into "Pet" category)
    "AthenaPetCarrier": {"name": "Pet", "category": "Sidekicks", "slot": 1},
    "AthenaPet": {"name": "Pet", "category": "Sidekicks", "slot": None},
    "CosmeticCompanion": {"name": "Companion", "category": "Sidekicks", "slot": None},
    "CosmeticMimosa": {"name": "Sidekick", "category": "Sidekicks", "slot": None},

    # Wraps
    "AthenaItemWrap": {"name": "Wrap", "category": "Wraps", "slot": None},  # Multiple slots

    # Lobby
    "AthenaLoadingScreen": {"name": "Loading Screen", "category": "Lobby", "slot": 3},
    "AthenaMusicPack": {"name": "Music Pack", "category": "Lobby", "slot": 2},
    "SparksSong": {"name": "Jam Track", "category": "Lobby", "slot": None},  # Multiple slots
    "SparksSong_Lobby": {"name": "Lobby Track", "category": "Lobby", "slot": 2},  # Virtual type: jam track in lobby music slot
    "BannerToken": {"name": "Banner", "category": "Lobby", "slot": None},

    # Vehicles
    "VehicleCosmetics_Body": {"name": "Car Body", "category": "Cars", "slot": 1},
    "VehicleCosmetics_Skin": {"name": "Car Skin", "category": "Cars", "slot": None},
    "VehicleCosmetics_Wheel": {"name": "Wheels", "category": "Cars", "slot": None},
    "VehicleCosmetics_Booster": {"name": "Booster", "category": "Cars", "slot": None},
    "VehicleCosmetics_DriftTrail": {"name": "Drift Trail", "category": "Cars", "slot": None},

    # Instruments (Festival)
    "SparksGuitar": {"name": "Guitar", "category": "Instruments", "slot": None},
    "SparksBass": {"name": "Bass", "category": "Instruments", "slot": None},
    "SparksDrums": {"name": "Drums", "category": "Instruments", "slot": None},
    "SparksKeyboard": {"name": "Keytar", "category": "Instruments", "slot": None},
    "SparksMicrophone": {"name": "Microphone", "category": "Instruments", "slot": None},

    # LEGO
    "JunoBuildingProp": {"name": "Decor Bundle", "category": "LEGO", "slot": None},
    "JunoBuildingSet": {"name": "Build Set", "category": "LEGO", "slot": None}
}

# The category menu: All Cosmetics first, then grouped by type
CATEGORIES = [
    "All Cosmetics",
    # Character
    "Outfit", "Back Bling", "Pickaxe", "Glider", "Kicks", "Contrail", "Aura",
    # Emotes & Expressions
    "Emote", "Spray", "Emoji", "Toy",
    # Sidekicks/Pets
    "Pet", "Companion",
    # Wraps
    "Wrap",
    # Lobby
    "Loading Screen", "Music Pack", "Jam Track", "Lobby Track", "Banner",
    # Vehicles
    "Car Body", "Car Skin", "Wheels", "Booster", "Drift Trail",
    # Instruments (Festival)
    "Guitar", "Bass", "Drums", "Keytar", "Microphone",
    # LEGO
    "Decor Bundle", "Build Set"
]

SORT_OPTIONS = [
    "Rarity (Highest First)",
    "Rarity (Lowest First)",
    "Name (A-Z)",
    "Name (Z-A)",
    "Type",
    "Newest First",
    "Oldest First",
    "Favorites First"
]

# Slot coordinates for automation
SLOT_COORDS = {
    1: (260, 400),
    2: (420, 400),
    3: (570, 400),
    4: (720, 400),
    5: (260, 560),
    6: (420, 560),
    7: (560, 550),
    8: (720, 550)
}

# Emote wheel slot coordinates (circular layout)
EMOTE_SLOT_COORDS = {
    1: (450, 390),
    2: (600, 450),
    3: (650, 590),
    4: (600, 740),
    5: (450, 800),
    6: (300, 740),
    7: (250, 600),
    8: (300, 450)
}

# Category positions in Fortnite UI
CATEGORY_COORDS = {
    'Character': (110, 280),
    'Emotes': (110, 335),
    'Sidekicks': (110, 390),
    'Wraps': (110, 445),
    'Lobby': (110, 500),
    'Cars': (110, 555),
    'Instruments': (110, 610),
    'Music': (110, 665)
}

# Mapping from Locker Service slot templates to UI automation (category, slot)
SLOT_TEMPLATE_TO_AUTOMATION = {
    # Character
    "LoadoutSlot_Character": ("Character", 1),
    "LoadoutSlot_Backpack": ("Character", 2),
    "LoadoutSlot_Pickaxe": ("Character", 3),
    "LoadoutSlot_Glider": ("Character", 4),
    "LoadoutSlot_Shoes": ("Character", 5),
    "LoadoutSlot_Contrails": ("Character", 6),
    # Emotes
    "LoadoutSlot_Emote_0": ("Emotes", 1),
    "LoadoutSlot_Emote_1": ("Emotes", 2),
    "LoadoutSlot_Emote_2": ("Emotes", 3),
    "LoadoutSlot_Emote_3": ("Emotes", 4),
    "LoadoutSlot_Emote_4": ("Emotes", 5),
    "LoadoutSlot_Emote_5": ("Emotes", 6),
    "LoadoutSlot_Emote_6": ("Emotes", 7),
    "LoadoutSlot_Emote_7": ("Emotes", 8),
    # Wraps
    "LoadoutSlot_Wrap_0": ("Wraps", 1),
    "LoadoutSlot_Wrap_1": ("Wraps", 2),
    "LoadoutSlot_Wrap_2": ("Wraps", 3),
    "LoadoutSlot_Wrap_3": ("Wraps", 4),
    "LoadoutSlot_Wrap_4": ("Wraps", 5),
    "LoadoutSlot_Wrap_5": ("Wraps", 6),
    "LoadoutSlot_Wrap_6": ("Wraps", 7),
    # Lobby / Platform
    "LoadoutSlot_LobbyMusic": ("Lobby", 2),
    "LoadoutSlot_LoadingScreen": ("Lobby", 3),
    # Vehicles
    "LoadoutSlot_Vehicle_Body": ("Cars", 1),
    "LoadoutSlot_Vehicle_Skin": ("Cars", 2),
    "LoadoutSlot_Vehicle_Wheel": ("Cars", 3),
    "LoadoutSlot_Vehicle_DriftSmoke": ("Cars", 4),
    "LoadoutSlot_Vehicle_Booster": ("Cars", 5),
    # Instruments
    "LoadoutSlot_Guitar": ("Instruments", 1),
    "LoadoutSlot_Bass": ("Instruments", 2),
    "LoadoutSlot_Drum": ("Instruments", 3),
    "LoadoutSlot_Keyboard": ("Instruments", 4),
    "LoadoutSlot_Microphone": ("Instruments", 5),
    # Jam Tracks
    "LoadoutSlot_JamSong0": ("Lobby", None),
    "LoadoutSlot_JamSong1": ("Lobby", None),
    "LoadoutSlot_JamSong2": ("Lobby", None),
    "LoadoutSlot_JamSong3": ("Lobby", None),
    "LoadoutSlot_JamSong4": ("Lobby", None),
    "LoadoutSlot_JamSong5": ("Lobby", None),
    "LoadoutSlot_JamSong6": ("Lobby", None),
    "LoadoutSlot_JamSong7": ("Lobby", None),
}

# Friendly names for loadout schema types
LOADOUT_SCHEMA_NAMES = {
    "CosmeticLoadout:LoadoutSchema_Character": "Character",
    "CosmeticLoadout:LoadoutSchema_Emotes": "Emotes",
    "CosmeticLoadout:LoadoutSchema_Platform": "Lobby",
    "CosmeticLoadout:LoadoutSchema_Sparks": "Instruments",
    "CosmeticLoadout:LoadoutSchema_Wraps": "Wraps",
    "CosmeticLoadout:LoadoutSchema_Jam": "Jam Tracks",
    "CosmeticLoadout:LoadoutSchema_Vehicle": "Vehicle (Sedan)",
    "CosmeticLoadout:LoadoutSchema_Vehicle_SUV": "Vehicle (SUV)",
    "CosmeticLoadout:LoadoutSchema_Mimosa": "Companion",
    "CosmeticLoadout:LoadoutSchema_Moments": "Moments",
}

# The names the equipped list uses (the schema without its prefix)
EQUIPPED_SCHEMA_NAMES = {
    "Character": "Character",
    "Emotes": "Emotes",
    "Platform": "Lobby",
    "Sparks": "Instruments",
    "Wraps": "Wraps",
    "Jam": "Jam Tracks",
    "Vehicle": "Vehicle (Sedan)",
    "Vehicle_SUV": "Vehicle (SUV)",
    "Mimosa": "Companion",
    "Moments": "Moments",
}

# What "Save current as loadout" offers: (name, schema or None for all)
SAVE_LOADOUT_CHOICES = [
    ("All Categories", None),
    ("Character", "CosmeticLoadout:LoadoutSchema_Character"),
    ("Emotes", "CosmeticLoadout:LoadoutSchema_Emotes"),
    ("Lobby", "CosmeticLoadout:LoadoutSchema_Platform"),
    ("Wraps", "CosmeticLoadout:LoadoutSchema_Wraps"),
    ("Instruments", "CosmeticLoadout:LoadoutSchema_Sparks"),
    ("Jam Tracks", "CosmeticLoadout:LoadoutSchema_Jam"),
    ("Vehicle (Sedan)", "CosmeticLoadout:LoadoutSchema_Vehicle"),
]

SPECIAL_RARITIES = ["marvel", "dc", "starwars", "icon", "gaminglegends"]

LOADOUT_FILTERS_FIXED = ["All", "Multi-Category Only"]

# Messages the views show when something fails
EQUIP_FAILED_MESSAGE = "Failed to equip cosmetic. Make sure Fortnite is open and in the locker."


# --- What the lists show -------------------------------------------------------------------

def friendly_type(cosmetic_type: str) -> str:
    return COSMETIC_TYPE_MAP.get(cosmetic_type, {}).get("name", cosmetic_type)


def rarity_display(cosmetic: dict) -> str:
    """Rarity as shown, with the series suffix for licensed series."""
    rarity_raw = cosmetic.get("rarity", "common").lower()
    if rarity_raw in SPECIAL_RARITIES:
        return f"{rarity_raw.title()} series"
    return rarity_raw.title()


def season_text(cosmetic: dict) -> str:
    return f"C{cosmetic.get('introduction_chapter', '?')}S{cosmetic.get('introduction_season', '?')}"


def category_cosmetics(cosmetics_data: List[dict], category_name: str, owned_only: bool = False,
                       owned_ids: Optional[set] = None) -> List[dict]:
    """The cosmetics of one category (or all), owned ones only if asked, highest rarity first."""
    owned_ids = owned_ids or set()
    filtered = []
    for cosmetic in cosmetics_data:
        if owned_only and cosmetic.get("id", "").lower() not in owned_ids:
            continue
        if category_name == "All Cosmetics":
            filtered.append(cosmetic)
        elif category_name == "Lobby Track":
            # Lobby Track shows Jam Track items (SparksSong) but equips to lobby music slot
            if cosmetic.get("type", "") == "SparksSong":
                filtered.append(cosmetic)
        elif friendly_type(cosmetic.get("type", "")) == category_name:
            filtered.append(cosmetic)
    return sorted(filtered, key=lambda x: (-x.get("rarity_value", 0), x.get("name", "")))


def filter_cosmetics(cosmetics: List[dict], favorites_only: bool = False, search: str = "") -> List[dict]:
    """Apply the Favorites Only toggle and the search box."""
    filtered = list(cosmetics)
    if favorites_only:
        filtered = [c for c in filtered if c.get("favorite", False)]
    if search:
        needle = search.lower()
        filtered = [
            c for c in filtered
            if needle in c.get("name", "").lower()
            or needle in c.get("description", "").lower()
            or needle in c.get("rarity", "").lower()
        ]
    return filtered


def sort_favorites_first(cosmetics: List[dict]) -> List[dict]:
    """Favorites first, then rarity (highest first), then name."""
    return sorted(cosmetics, key=lambda x: (not x.get("favorite", False), -x.get("rarity_value", 0),
                                            x.get("name", "")))


def results_label(count: int, category_name: str, search: str = "", favorites_only: bool = False,
                  favorites_first: bool = False) -> str:
    filter_desc = ""
    if favorites_only:
        filter_desc = " (favorites only)"
    elif favorites_first:
        filter_desc = " (favorites first)"
    if search:
        return f"Showing {count} {category_name} cosmetics matching '{search}'{filter_desc}"
    return f"Showing {count} {category_name} cosmetics{filter_desc}"


def category_options(category_name: str) -> dict:
    """Which special rows a category has: random, randomize (a track at random) and unequip (with its search term)."""
    show_random = category_name not in ("All Cosmetics", "Emote")
    if category_name == "All Cosmetics":
        unequip = None
    elif category_name in ("Outfit", "Pickaxe"):
        unequip = "Default"
    elif category_name == "Glider":
        unequip = "Glider"
    else:
        unequip = "Empty"
    return {
        "random": show_random,
        "randomize": show_random and category_name in ("Jam Track", "Lobby Track"),
        "unequip": unequip,
    }


def special_details(kind: str, unequip_term: Optional[str] = None) -> str:
    if kind == "random":
        return "Random\n\nEquip the Random (shuffle) option for this slot."
    if kind == "randomize":
        return "Randomize Track\n\nPick a random cosmetic from this list and equip it."
    return f"Unequip\n\nSearches for '{unequip_term}' to remove the cosmetic from this slot."


def cosmetic_details(cosmetic: dict) -> str:
    details = [f"Name: {cosmetic.get('name', 'Unknown')}",
               f"Type: {friendly_type(cosmetic.get('type', 'Unknown'))}",
               f"Rarity: {rarity_display(cosmetic)}",
               f"Season: Chapter {cosmetic.get('introduction_chapter', '?')}, "
               f"Season {cosmetic.get('introduction_season', '?')}"]
    if cosmetic.get("description"):
        details.append(f"\nDescription: {cosmetic['description']}")
    if cosmetic.get("favorite"):
        details.append("\n⭐ FAVORITE")
    return "\n".join(details)


def compact_record(cosmetic: dict) -> dict:
    """A cosmetic as the hub page's list wants it (short keys: there can be thousands)."""
    return {
        "i": cosmetic.get("id", ""),
        "n": cosmetic.get("name", "Unknown"),
        "t": friendly_type(cosmetic.get("type", "")),
        "r": rarity_display(cosmetic),
        "k": cosmetic.get("rarity", "common").lower(),
        "v": cosmetic.get("rarity_value", 0),
        "s": season_text(cosmetic),
        "c": cosmetic.get("introduction_chapter", "?"),
        "e": cosmetic.get("introduction_season", "?"),
        "d": cosmetic.get("description", ""),
        "f": bool(cosmetic.get("favorite", False)),
    }


# --- Owned cosmetics ---------------------------------------------------------------------

def placeholder_cosmetic(cosmetic_id: str) -> dict:
    return {
        "id": cosmetic_id,
        "name": f"[Unknown Item] {cosmetic_id[:20]}",
        "description": "This item is owned but not in the Fortnite-API database",
        "type": "Unknown",
        "rarity": "common",
        "rarity_value": 0,
        "introduction_chapter": "?",
        "introduction_season": "?",
        "image_url": "",
        "favorite": False
    }


def apply_owned_ids(cosmetics_data: List[dict], auth, fetched_ids) -> set:
    """Mark what the account owns: add placeholders for owned items the database lacks,
    and stamp favorites from the same profile fetch. Returns the set of owned ids (lowercase)."""
    owned_ids = set(i.lower() for i in fetched_ids)
    logger.info(f"Fetched {len(owned_ids)} owned cosmetic IDs")
    existing_ids = {c.get("id", "").lower() for c in cosmetics_data}
    missing_ids = owned_ids - existing_ids
    if missing_ids:
        logger.info(f"Found {len(missing_ids)} owned items not in database, creating placeholders")
        for missing_id in missing_ids:
            cosmetics_data.append(placeholder_cosmetic(missing_id))
    fav_count = apply_favorite_flags(cosmetics_data, getattr(auth, "favorite_cosmetic_ids", None))
    if fav_count:
        logger.info(f"Pre-marked {fav_count} favorite cosmetics")
    return owned_ids


class OwnedResult:
    """What switching the "my cosmetics only" filter did.

    messages are what to say, in order. error is a message for a dialog when the owned list couldn't be
    fetched; expired is true when the login has expired. owned_only is the filter's new state.
    """

    def __init__(self, owned_only: bool, owned_ids: set):
        self.owned_only = owned_only
        self.owned_ids = owned_ids
        self.messages: List[str] = []
        self.error: Optional[str] = None
        self.expired = False


def set_owned_only(cosmetics_data: List[dict], auth, owned_ids: set, want_owned: bool) -> OwnedResult:
    """Turn the owned-only filter on or off, fetching the owned ids the first time. Calls the Epic API."""
    result = OwnedResult(want_owned, owned_ids)
    if not want_owned:
        result.messages.append("Disabled: Showing all cosmetics")
        return result

    result.messages.append("Enabled: Show only owned cosmetics")
    if owned_ids:
        return result

    result.messages.append("Fetching owned cosmetics")
    fetched_ids = auth.fetch_owned_cosmetics()
    result.owned_only = False
    if fetched_ids == "AUTH_EXPIRED":
        result.messages.append("Your login has expired. Please log in again.")
        result.expired = True
    elif fetched_ids:
        result.owned_ids = apply_owned_ids(cosmetics_data, auth, fetched_ids)
        result.owned_only = True
        result.messages.append(f"Found {len(result.owned_ids)} owned cosmetics")
    else:
        result.messages.append("Failed to fetch owned cosmetics list")
        result.error = ("Failed to fetch your owned cosmetics from Epic Games. "
                        "Please check your connection and try again.")
    return result


# --- Favorites -------------------------------------------------------------------------------

def toggle_favorite(auth, cosmetics_data: List[dict], cosmetic: dict) -> str:
    """Flip a cosmetic's favorite flag through the Locker API, speaking as it goes.

    Returns "ok", "missing" (no id or type), "login" (not signed in), "failed" or "error".
    """
    cosmetic_id = cosmetic.get("id", "")
    cosmetic_type = cosmetic.get("type", "")
    name = cosmetic.get("name", "Unknown")

    if not cosmetic_id or not cosmetic_type:
        speaker.speak("Cannot favorite this item. Missing data.")
        return "missing"

    if not auth or not auth.access_token:
        speaker.speak("Please log in to use favorites")
        return "login"

    template_id = f"{cosmetic_type}:{cosmetic_id}"
    current_favorite = cosmetic.get("favorite", False)
    new_favorite = not current_favorite

    try:
        from lib.utilities.epic_auth import get_locker_api
        locker_api = get_locker_api(auth)

        if not locker_api.template_id_map:
            speaker.speak("Loading profile")
            locker_api.load_profile()

        speaker.speak(f"{'Unfavoriting' if current_favorite else 'Favoriting'} {name}")
        success = locker_api.set_favorite(template_id, new_favorite)

        if success:
            cosmetic["favorite"] = new_favorite
            for c in cosmetics_data:
                if c.get("id") == cosmetic_id:
                    c["favorite"] = new_favorite
                    break
            speaker.speak(f"{name} added to favorites" if new_favorite else f"{name} removed from favorites")
            return "ok"
        speaker.speak("Failed to update favorite status")
        return "failed"
    except Exception as e:
        logger.error(f"Error toggling favorite: {e}")
        speaker.speak("Error toggling favorite")
        return "error"


# --- Equipping in Fortnite ------------------------------------------------------------------

def focus_fortnite_window() -> bool:
    """Focus the Fortnite window before automation"""
    try:
        import win32gui
        import win32con

        def callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if "fortnite" in title.lower():
                    windows.append((hwnd, title))
            return True

        windows = []
        win32gui.EnumWindows(callback, windows)

        if windows:
            hwnd = windows[0][0]
            logger.info(f"Found Fortnite window: {windows[0][1]}")

            # Restore if minimized
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.2)

            # Bring to foreground
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.3)
            return True
        else:
            logger.warning("Fortnite window not found")
            return False
    except ImportError:
        # pywin32 not available, try alternative method
        try:
            import ctypes
            user32 = ctypes.windll.user32

            # EnumWindows callback
            EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))

            def callback(hwnd, lParam):
                length = user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)

                if "fortnite" in buff.value.lower() and user32.IsWindowVisible(hwnd):
                    lParam.contents = ctypes.c_int(hwnd)
                    return False
                return True

            hwnd_result = ctypes.c_int(0)
            user32.EnumWindows(EnumWindowsProc(callback), ctypes.byref(hwnd_result))

            if hwnd_result.value:
                user32.SetForegroundWindow(hwnd_result.value)
                time.sleep(0.3)
                return True
            else:
                logger.warning("Fortnite window not found (ctypes method)")
                return False
        except Exception as e:
            logger.error(f"Error focusing Fortnite window: {e}")
            return False
    except Exception as e:
        logger.error(f"Error focusing Fortnite window: {e}")
        return False


def _slot_coords(category: str, slot: int) -> Optional[Tuple[int, int]]:
    # The emote wheel has its own layout
    return (EMOTE_SLOT_COORDS if category == "Emotes" else SLOT_COORDS).get(slot)


def _open_slot(category: str, slot_coords: Tuple[int, int]) -> None:
    """In the Fortnite locker: open the category and click the slot."""
    from lib.utilities.mouse import move_to, move_to_and_click, get_mouse_position

    # Click locker button
    move_to_and_click(350, 69)
    time.sleep(0.3)

    # Click category
    category_coords = CATEGORY_COORDS.get(category)
    if category_coords:
        move_to_and_click(category_coords[0], category_coords[1])
        time.sleep(0.3)

        current_x, current_y = get_mouse_position()
        move_to(current_x + 500, current_y)
        time.sleep(1.0)

    # Click slot
    move_to_and_click(slot_coords[0], slot_coords[1])
    time.sleep(1.0)


def _search_and_pick(item_name: str) -> None:
    """In the slot's item list: search for the item and click it twice to equip."""
    import pyautogui
    from lib.utilities.mouse import move_to_and_click, click_mouse

    # Click search bar
    move_to_and_click(1030, 210)
    time.sleep(0.5)

    # Type item name
    pyautogui.write(item_name, interval=0.02)
    time.sleep(0.3)
    pyautogui.press('enter')
    time.sleep(0.1)

    # Click item twice to equip
    move_to_and_click(1020, 350)
    time.sleep(0.05)
    click_mouse('left')
    time.sleep(0.1)


def perform_equip_automation(category: str, slot: int, item_name: str) -> bool:
    """Equip an item by name through the Fortnite locker screen."""
    try:
        import pyautogui
        from lib.utilities.mouse import move_to_and_click

        slot_coords = _slot_coords(category, slot)
        if not slot_coords:
            logger.error(f"Unknown slot number: {slot}")
            return False

        if not focus_fortnite_window():
            speaker.speak("Cannot find Fortnite window. Make sure the game is running.")
            return False

        time.sleep(0.5)
        _open_slot(category, slot_coords)
        _search_and_pick(item_name)

        # Press escape to exit
        pyautogui.press('escape')
        time.sleep(1)

        # Click final position (PLAY tab)
        move_to_and_click(130, 69)
        return True

    except Exception as e:
        logger.error(f"Error in automation: {e}")
        return False


def perform_scroll_and_click_automation(category: str, slot: int, click_x: int, click_y: int) -> bool:
    """Scroll an item list to the top and click one position (Random, Unequip)."""
    try:
        import pyautogui
        from lib.utilities.mouse import move_to, move_to_and_click, click_mouse, mouse_scroll

        slot_coords = _slot_coords(category, slot)
        if not slot_coords:
            logger.error(f"Unknown slot number: {slot}")
            return False

        if not focus_fortnite_window():
            speaker.speak("Cannot find Fortnite window. Make sure the game is running.")
            return False

        time.sleep(0.5)
        _open_slot(category, slot_coords)

        # Hover over the options area and scroll up to reach the top
        move_to(click_x, click_y)
        scroll_end = time.time() + 0.5
        while time.time() < scroll_end:
            mouse_scroll(127)  # Scroll up aggressively
            time.sleep(0.05)

        time.sleep(0.3)

        # Click the target option
        move_to_and_click(click_x, click_y)
        time.sleep(0.05)
        click_mouse('left')
        time.sleep(0.1)

        # Press escape to exit
        pyautogui.press('escape')
        time.sleep(1)

        # Click PLAY tab
        move_to_and_click(130, 69)
        return True

    except Exception as e:
        logger.error(f"Error in scroll-and-click automation: {e}")
        return False


def type_for_category(category_name: str) -> str:
    """Backend type of a category's cosmetics ("Unknown" if none)."""
    for backend_type, info in COSMETIC_TYPE_MAP.items():
        if info["name"] == category_name:
            return backend_type
    return "Unknown"


def equip_target(category_name: str, cosmetic_type: str) -> Tuple[Optional[str], Optional[int]]:
    """Where in Fortnite's locker something goes: (category, slot). A slot of None needs the user to choose."""
    # Lobby Track: jam tracks equipped to the lobby music slot
    if category_name == "Lobby Track":
        return "Lobby", 2
    info = COSMETIC_TYPE_MAP.get(cosmetic_type, {})
    return info.get("category"), info.get("slot")


def slot_prompt(cosmetic_type: str, name: str) -> Optional[dict]:
    """The question to ask when a type has several slots: {title, message, choices}, or None (use slot 1)."""
    if cosmetic_type == "AthenaDance":
        return {"title": "Select Emote Slot",
                "message": f"Select which emote slot to equip '{name}' to:",
                "choices": ["Emote 1", "Emote 2", "Emote 3", "Emote 4", "Emote 5", "Emote 6", "Emote 7", "Emote 8"]}
    if cosmetic_type == "AthenaItemWrap":
        return {"title": "Select Wrap Slot",
                "message": f"Select which wrap slot to equip '{name}' to:",
                "choices": ["Rifles", "Shotguns", "Submachine Guns", "Snipers", "Pistols", "Utility", "Vehicles"]}
    if cosmetic_type == "SparksSong":
        return {"title": "Select Jam Track Slot",
                "message": f"Select which jam track slot to equip '{name}' to:",
                "choices": ["Jam Track 1", "Jam Track 2", "Jam Track 3", "Jam Track 4"]}
    return None


class EquipRequest:
    """One thing to equip: a cosmetic, or one of the special rows (random, unequip, randomize)."""

    def __init__(self, category_name: str, kind: str = "cosmetic", cosmetic: Optional[dict] = None,
                 candidates: Optional[List[dict]] = None):
        self.category_name = category_name
        self.kind = kind
        self.cosmetic = cosmetic
        self.candidates = candidates or []


def plan_equip(request: EquipRequest) -> dict:
    """Decide what an equip needs before it runs.

    Returns {"error": message} when it can't go ahead, {"ask": prompt} when the user must pick a slot,
    or {"name", "category", "slot", "cosmetic_type"} (slot may still be None when it needs asking).
    """
    kind = request.kind
    if kind == "randomize":
        if not request.candidates:
            speaker.speak("No cosmetics available to randomize")
            return {"error": "No cosmetics available to randomize."}
        request.cosmetic = random.choice(request.candidates)
        speaker.speak(f"Randomly selected {request.cosmetic.get('name', 'Unknown')}")
        kind = "cosmetic"

    if kind == "cosmetic":
        cosmetic = request.cosmetic
        name = cosmetic.get("name", "Unknown")
        cosmetic_type = cosmetic.get("type", "")
        category, slot = equip_target(request.category_name, cosmetic_type)
        if not category:
            speaker.speak(f"Cannot equip {name}. Unknown category.")
            return {"error": f"Cannot equip {name}.\nUnknown cosmetic category."}
        return {"name": name, "category": category, "slot": slot, "cosmetic_type": cosmetic_type}

    # Random and Unequip act on the category the list is showing
    label = "Random" if kind == "random" else "Unequip"
    backend_type = "SparksSong_Lobby" if request.category_name == "Lobby Track" \
        else type_for_category(request.category_name)
    category, slot = equip_target(request.category_name, backend_type)
    if not category:
        speaker.speak("Cannot equip Random. Unknown category." if kind == "random"
                      else "Cannot unequip. Unknown category.")
        return {"error": "Unknown category."}
    return {"name": label, "category": category, "slot": slot, "cosmetic_type": backend_type}


def run_equip(request: EquipRequest, plan: dict, slot: int) -> Tuple[bool, str]:
    """Equip with the mouse. Blocks until it is done. Returns (success, name)."""
    name = plan["name"]
    category = plan["category"]
    kind = request.kind
    if kind == "randomize":
        kind = "cosmetic"

    try:
        if kind == "random":
            speaker.speak("Equipping Random")
            logger.info(f"Equipping Random to {category} slot {slot}")
            success = perform_scroll_and_click_automation(category, slot, 1175, 385)
        elif kind == "unequip":
            speaker.speak("Unequipping")
            logger.info(f"Unequipping {category} slot {slot}")
            success = perform_scroll_and_click_automation(category, slot, 1020, 350)
        else:
            speaker.speak(f"Equipping {name}")
            logger.info(f"Equipping {name} to {category} slot {slot}")
            success = perform_equip_automation(category, slot, name)
    except Exception as e:
        logger.error(f"Error equipping cosmetic: {e}")
        speaker.speak("Error equipping cosmetic")
        raise

    time.sleep(0.3)
    if success:
        speaker.speak(f"{name} equipped!")
    else:
        speaker.speak("Equip failed")
    return success, name


# --- Equipped cosmetics and loadouts ----------------------------------------------------------

def resolve_item_name(cosmetics_data: List[dict], equipped_id: str) -> str:
    """A friendly cosmetic name from its template id."""
    if not equipped_id:
        return "(empty)"
    item_id = equipped_id.split(":")[-1] if ":" in equipped_id else equipped_id
    for c in cosmetics_data:
        if c.get("id", "").lower() == item_id.lower():
            return c.get("name", item_id)
    return item_id


def equipped_text(auth, cosmetics_data: List[dict]) -> Optional[str]:
    """What the account has equipped right now, as readable text; None when it can't be fetched."""
    equipped = auth.get_equipped_cosmetics()
    if not equipped:
        return None
    lines = []
    for schema, data in equipped.items():
        lines.append(f"--- {EQUIPPED_SCHEMA_NAMES.get(schema, schema)} ---")
        for slot_name, slot_data in data.get("slots", {}).items():
            display_name = slot_name.replace("LoadoutSlot_", "").replace("_", " ")
            equipped_id = slot_data.get("equipped_id", "")
            if equipped_id:
                item_id = equipped_id.split(":")[-1] if ":" in equipped_id else equipped_id
                friendly_item = None
                for c in cosmetics_data:
                    if c.get("id", "").lower() == item_id.lower():
                        friendly_item = c.get("name", item_id)
                        break
                lines.append(f"  {display_name}: {friendly_item or item_id}")
            else:
                lines.append(f"  {display_name}: (empty)")
        lines.append("")
    return "\n".join(lines)


def _local_loadouts() -> list:
    from lib.config.config_manager import config_manager
    try:
        config_manager.register('fa11y_loadouts', 'config/fa11y_loadouts.json', format='json', default=[])
    except Exception:
        pass
    loadouts = config_manager.get('fa11y_loadouts') or []
    return loadouts if isinstance(loadouts, list) else []


def _save_local_loadouts(loadouts: list) -> None:
    from lib.config.config_manager import config_manager
    config_manager.set('fa11y_loadouts', data=loadouts)


def import_epic_presets_to_local(presets: list) -> None:
    """Auto-import Epic presets to local storage so they can be edited.
    Only imports presets not already in local storage (by name)."""
    try:
        local_loadouts = _local_loadouts()
        existing_local = {ll.get("display_name", "") for ll in local_loadouts}

        by_name = {}
        for p in presets:
            name = p.get("displayName", "") or "(unnamed)"
            by_name.setdefault(name, {})[p.get("loadoutType", "")] = {
                "loadoutSlots": p.get("loadoutSlots", []),
                "shuffleType": p.get("shuffleType", "DISABLED"),
            }

        imported = 0
        for name, categories in by_name.items():
            if name not in existing_local:
                local_loadouts.append({"display_name": name, "categories": categories, "source": "epic_import"})
                imported += 1

        if imported > 0:
            _save_local_loadouts(local_loadouts)
            logger.info(f"Imported {imported} Epic presets to local storage")
    except Exception as e:
        logger.warning(f"Could not import Epic presets: {e}")


def load_loadouts(auth) -> Optional[List[dict]]:
    """Saved loadouts: Epic's presets (merged by name across categories) then the ones saved locally.

    Each is {displayName, categories, source}. None when Epic's data can't be fetched; [] when there are none.
    """
    locker_data = auth.query_locker_items()
    if not locker_data:
        return None
    presets = locker_data.get("loadoutPresets", [])
    if not presets:
        return []

    import_epic_presets_to_local(presets)

    merged: List[dict] = []
    index: Dict[str, int] = {}
    for p in presets:
        name = p.get("displayName", "") or "(unnamed)"
        ltype = p.get("loadoutType", "")
        category = {"loadoutSlots": p.get("loadoutSlots", []), "shuffleType": p.get("shuffleType", "DISABLED")}
        if name in index:
            merged[index[name]]["categories"][ltype] = category
        else:
            index[name] = len(merged)
            merged.append({"displayName": name, "categories": {ltype: category}, "source": "epic"})

    try:
        for ll in _local_loadouts():
            merged.append({
                "displayName": ll.get("display_name", "(unnamed)"),
                "categories": ll.get("categories", {}),
                "source": "local",
            })
    except Exception as e:
        logger.warning(f"Could not load local loadouts: {e}")
    return merged


def loadout_filter_choices() -> List[str]:
    return LOADOUT_FILTERS_FIXED + sorted(set(LOADOUT_SCHEMA_NAMES.values()))


def loadout_type_label(entry: dict) -> str:
    cat_names = [LOADOUT_SCHEMA_NAMES.get(k, k.split("_")[-1]) for k in entry.get("categories", {})]
    if len(cat_names) > 1:
        return " + ".join(sorted(cat_names))
    if cat_names:
        return cat_names[0]
    return "?"


def loadout_label(entry: dict) -> str:
    return f"{entry.get('displayName', '(unnamed)')} [{loadout_type_label(entry)}]"


def filter_loadouts(entries: List[dict], filter_type: str = "All") -> List[dict]:
    schema_key = next((k for k, v in LOADOUT_SCHEMA_NAMES.items() if v == filter_type), None)
    result = []
    for entry in entries:
        cats = entry.get("categories", {})
        if filter_type == "Multi-Category Only":
            if len(cats) < 2:
                continue
        elif filter_type != "All":
            if schema_key and schema_key not in cats:
                continue
        result.append(entry)
    return result


def loadout_detail_text(entry: dict, cosmetics_data: List[dict]) -> str:
    lines = [f"Loadout: {entry.get('displayName', '(unnamed)')}",
             f"Source: {entry.get('source', '?')}",
             f"Categories: {loadout_type_label(entry)}", ""]
    for cat_type, cat_data in entry.get("categories", {}).items():
        lines.append(f"--- {LOADOUT_SCHEMA_NAMES.get(cat_type, cat_type)} ---")
        for slot in cat_data.get("loadoutSlots", []):
            st = slot.get("slotTemplate", "")
            slot_name = st.split(":")[-1].replace("LoadoutSlot_", "").replace("_", " ") if ":" in st else st
            lines.append(f"  {slot_name}: {resolve_item_name(cosmetics_data, slot.get('equippedItemId', ''))}")
        lines.append("")
    return "\n".join(lines)


def loadout_api_prompt(entry: dict) -> str:
    cat_names = ", ".join(LOADOUT_SCHEMA_NAMES.get(k, k) for k in entry.get("categories", {}))
    return (f"Equip loadout '{entry.get('displayName', '(unnamed)')}' via API?\n\n"
            f"Categories: {cat_names}\n\n"
            "This applies instantly on Epic's servers.\n"
            "Changes will appear in-game after restarting or loading into a match.")


def equip_loadout_via_api(auth, entry: dict) -> bool:
    """Apply a loadout on Epic's servers, speaking as the wx view does."""
    name = entry.get("displayName", "(unnamed)")
    cats = entry.get("categories", {})
    speaker.speak(f"Equipping '{name}' via API...")
    put_data = {}
    for cat_type, cat_data in cats.items():
        formatted_slots = []
        for slot in cat_data.get("loadoutSlots", []):
            fs = {
                "slotTemplate": slot["slotTemplate"],
                "itemCustomizations": slot.get("itemCustomizations", []),
            }
            if slot.get("equippedItemId"):
                fs["equippedItemId"] = slot["equippedItemId"]
            formatted_slots.append(fs)
        put_data[cat_type] = {
            "loadoutSlots": formatted_slots,
            "shuffleType": cat_data.get("shuffleType", "DISABLED"),
        }

    if auth.update_active_loadout(put_data):
        speaker.speak(f"Loadout '{name}' equipped via API ({len(cats)} categories)")
        return True
    speaker.speak("Failed to equip loadout")
    return False


def loadout_ui_items(entry: dict, cosmetics_data: List[dict]) -> List[dict]:
    """The items of a loadout that mouse automation can equip: {name, category, slot, slot_key}."""
    items = []
    for cat_data in entry.get("categories", {}).values():
        for slot in cat_data.get("loadoutSlots", []):
            equipped_id = slot.get("equippedItemId", "")
            if not equipped_id:
                continue
            st = slot.get("slotTemplate", "")
            slot_key = st.split(":")[-1] if ":" in st else st
            automation = SLOT_TEMPLATE_TO_AUTOMATION.get(slot_key)
            if not automation:
                continue
            category, slot_num = automation
            if slot_num is None:
                continue
            items.append({
                "name": resolve_item_name(cosmetics_data, equipped_id),
                "category": category,
                "slot": slot_num,
                "slot_key": slot_key,
            })
    return items


def loadout_ui_prompt(entry: dict, items: List[dict]) -> str:
    item_list = "\n".join(f"  • {i['name']} → {i['category']} slot {i['slot']}" for i in items)
    return (f"Equip loadout '{entry.get('displayName', '(unnamed)')}' in-game?\n\n"
            f"This will equip {len(items)} items one by one using mouse automation:\n"
            f"{item_list}\n\n"
            "Make sure Fortnite is open on the lobby screen.\n"
            "Do not move the mouse during automation.")


def perform_loadout_ui_automation(items: List[dict], loadout_name: str) -> None:
    """Equip a list of items one by one using UI automation in Fortnite."""
    try:
        import pyautogui
        from lib.utilities.mouse import move_to_and_click

        if not focus_fortnite_window():
            speaker.speak("Cannot find Fortnite window. Make sure the game is running.")
            return

        time.sleep(0.5)
        succeeded = 0
        failed = 0

        for i, item in enumerate(items):
            item_name = item["name"]
            category = item["category"]
            slot = item["slot"]
            logger.info(f"UI automation: equipping '{item_name}' to {category} slot {slot} ({i+1}/{len(items)})")

            slot_coords = _slot_coords(category, slot)
            if not slot_coords:
                logger.warning(f"No coords for {category} slot {slot}, skipping")
                failed += 1
                continue

            try:
                _open_slot(category, slot_coords)
                _search_and_pick(item_name)

                # Press escape to exit slot picker
                pyautogui.press('escape')
                time.sleep(0.5)
                succeeded += 1
            except Exception as e:
                logger.error(f"Error equipping '{item_name}': {e}")
                failed += 1

        # Return to PLAY tab
        pyautogui.press('escape')
        time.sleep(0.5)
        move_to_and_click(130, 69)

        msg = f"Loadout '{loadout_name}': {succeeded}/{len(items)} items equipped"
        if failed > 0:
            msg += f" ({failed} failed)"
        speaker.speak(msg)
        logger.info(msg)

    except Exception as e:
        logger.error(f"Error in loadout UI automation: {e}")
        speaker.speak("Error during automation")


def is_local_loadout(entry: dict) -> bool:
    return entry.get("source") == "local"


def delete_local_loadout(name: str) -> bool:
    """Remove a locally saved loadout by name."""
    try:
        loadouts = [l for l in _local_loadouts() if l.get("display_name") != name]
        _save_local_loadouts(loadouts)
        speaker.speak(f"Deleted '{name}'")
        return True
    except Exception as e:
        speaker.speak("Error deleting loadout")
        logger.error(f"Error deleting local loadout: {e}")
        return False


def loadout_exists(name: str) -> bool:
    return any(ll.get("display_name", "").lower() == name.lower() for ll in _local_loadouts())


def save_loadout(auth, friendly_name: str, loadout_type: Optional[str], loadout_name: str) -> dict:
    """Save what is equipped now as a local loadout, replacing one with the same name.

    Returns {"ok": True, "message": ...} or {"ok": False, "message": ...}. Speaks as the wx view does.
    """
    speaker.speak(f"Saving loadout '{loadout_name}'...")

    locker_data = auth.query_locker_items()
    if not locker_data:
        speaker.speak("Failed to fetch current loadout data")
        return {"ok": False, "message": "Failed to fetch current loadout data"}

    all_loadouts = locker_data.get("activeLoadoutGroup", {}).get("loadouts", {})
    if loadout_type is None:
        categories_to_save = dict(all_loadouts)
    else:
        cat_data = all_loadouts.get(loadout_type)
        if not cat_data:
            speaker.speak(f"No equipped items found for {friendly_name}")
            return {"ok": False, "message": f"No equipped items found for {friendly_name}"}
        categories_to_save = {loadout_type: cat_data}

    new_loadout = {"display_name": loadout_name, "categories": {}}
    for cat_type, cat_data in categories_to_save.items():
        new_loadout["categories"][cat_type] = {
            "loadoutSlots": cat_data.get("loadoutSlots", []),
            "shuffleType": cat_data.get("shuffleType", "DISABLED"),
        }

    saved = _local_loadouts()
    existing_idx = next((i for i, ll in enumerate(saved)
                         if ll.get("display_name", "").lower() == loadout_name.lower()), None)
    if existing_idx is not None:
        saved[existing_idx] = new_loadout
    else:
        saved.append(new_loadout)
    _save_local_loadouts(saved)

    cat_count = len(categories_to_save)
    slot_count = sum(len(c.get("loadoutSlots", [])) for c in categories_to_save.values())
    speaker.speak(f"Loadout '{loadout_name}' saved! {cat_count} categories, {slot_count} slots.")
    return {"ok": True, "message": (
        f"Loadout '{loadout_name}' saved locally.\n\n"
        f"Categories: {', '.join(LOADOUT_SCHEMA_NAMES.get(k, k) for k in categories_to_save)}\n"
        f"Total slots: {slot_count}")}
