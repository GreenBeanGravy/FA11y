from pathlib import Path

from lib.managers.poi_data_manager import CoordinateSystem


MAPS_DIR = Path("data/maps")


def _read_locations(filename):
    rows = []
    for line in (MAPS_DIR / filename).read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, screen, world = line.split("|")
        rows.append((
            name,
            tuple(map(int, screen.split(","))),
            tuple(map(float, world.split(","))),
        ))
    return rows


def test_main_map_coordinate_transform_matches_calibration_points():
    coordinate_system = CoordinateSystem(str(MAPS_DIR / "map_main_pois.txt"))

    for _name, expected_screen, world in _read_locations("map_main_pois.txt"):
        actual_screen = coordinate_system.world_to_screen(*world)
        assert abs(actual_screen[0] - expected_screen[0]) <= 1
        assert abs(actual_screen[1] - expected_screen[1]) <= 1


def test_main_map_landmarks_transform_to_expected_screen_positions():
    coordinate_system = CoordinateSystem(str(MAPS_DIR / "map_main_pois.txt"))
    landmarks = _read_locations("map_main_landmarks.txt")

    assert len(landmarks) == 24
    for _name, expected_screen, world in landmarks:
        actual_screen = coordinate_system.world_to_screen(*world)
        assert abs(actual_screen[0] - expected_screen[0]) <= 1
        assert abs(actual_screen[1] - expected_screen[1]) <= 1


def test_main_map_loot_has_current_items_and_no_sprites():
    loot = set(
        (MAPS_DIR / "map_main_loot.txt").read_text(encoding="utf-8").splitlines()
    )

    assert not any("sprite" in item.lower() for item in loot)
    assert {
        "Assault Rifle",
        "Ranger Assault Rifle",
        "Minigun",
        "Tactical Pistol",
        "Drum Gun",
        "8-Bit Shotgun",
        "Pump Shotgun",
        "Oni Shotgun",
        "Flare Gun",
        "Chug Splash",
        "Small Shield Potion",
        "Shield Potion",
        "Chug Jug",
        "Med Kit",
        "Bandage",
        "Midas Flopper",
        "Sonic Power Sneakers",
        "Midas' Masterpiece",
        "Mega Buster",
    } <= loot

    stale_mythics = {
        "Bigfoot's Flex SMG",
        "9mm Baba Yaga",
        "Striker Pump Shotgun",
        "Stinger SMG",
        "Hunting Rifle",
        "Wolfe's Maven Auto Shotgun",
        "The Voidblade's Burst Rifle",
        "Dark Voyager's Chaos Rifle",
        "Reacher Extending Shotgun",
        "Poison Ivy's Ranger Pistol",
        "Dark Voyager's Obliterator",
    }
    assert loot.isdisjoint(stale_mythics)


def test_removed_boss_and_vault_objects_are_not_shipped():
    game_objects = (
        MAPS_DIR / "map_main_gameobjects.txt"
    ).read_text(encoding="utf-8")

    assert "Boss Rift Spawn" not in game_objects
    assert "Harley Quinn," not in game_objects
    assert "Catwoman," not in game_objects
    assert "Poison Ivy," not in game_objects
