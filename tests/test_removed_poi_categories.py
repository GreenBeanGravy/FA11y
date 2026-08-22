from lib.app import constants
from lib.app.poi_navigation import CATEGORY_DISPLAY_NAMES


def test_boss_and_vault_categories_are_removed():
    assert "Boss Spawns" not in CATEGORY_DISPLAY_NAMES.values()
    assert "Main Vaults" not in CATEGORY_DISPLAY_NAMES.values()
    assert not hasattr(constants, "POI_CATEGORY_BOSS")
    assert not hasattr(constants, "POI_CATEGORY_VAULT")
    assert not hasattr(constants, "BOSS_FIXED_TYPES")
    assert not hasattr(constants, "BOSS_CLOSEST_TYPES")
    assert not hasattr(constants, "MAIN_VAULTS")
    assert not hasattr(constants, "SPECIAL_POI_CLOSEST_VAULT")
