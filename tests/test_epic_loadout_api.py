"""
Test script for Epic Games Locker Service API.
Exchanges the existing Epic auth token for an EOS Connect token,
then queries the Locker Service for equipped cosmetics and loadout presets.

Run directly: python tests/test_epic_loadout_api.py
"""
import os
import sys
import json
import requests
import base64
import uuid

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.utilities.epic_auth import EpicAuth

DEPLOYMENT_ID = "62a9473a2dca46b29ccf17577fcf42d7"
LOCKER_BASE_URL = "https://fngw-svc-gc-livefn.ol.epicgames.com/api/locker/v4"
EOS_TOKEN_URL = "https://api.epicgames.dev/auth/v1/oauth/token"


def get_eg1_token(auth: EpicAuth) -> str:
    """
    Get an EG1 (JWT) access token. The current token may be opaque (32-char hex).
    We need to refresh with token_type=eg1 to get a JWT that EOS Connect accepts.
    """
    if not auth.refresh_token:
        print("  ERROR: No refresh token available to get EG1 token")
        return None

    credentials = f"{auth.CLIENT_ID}:{auth.CLIENT_SECRET}"
    basic_auth = base64.b64encode(credentials.encode()).decode()

    data = {
        "grant_type": "refresh_token",
        "refresh_token": auth.refresh_token,
        "token_type": "eg1",  # Request JWT format instead of opaque
    }

    response = requests.post(
        auth.OAUTH_TOKEN_URL,
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=data,
        timeout=30,
    )

    if response.status_code == 200:
        token_data = response.json()
        eg1_token = token_data["access_token"]
        print(f"  Got EG1 token (starts with: {eg1_token[:20]}...)")
        print(f"  Token length: {len(eg1_token)}")

        # Update auth with the new token so MCP operations still work
        new_refresh = token_data.get("refresh_token")
        refresh_expires = token_data.get("refresh_expires", token_data.get("refresh_expires_in"))
        auth.access_token = eg1_token
        auth.save_auth(
            eg1_token,
            token_data["account_id"],
            auth.display_name,
            token_data["expires_in"],
            refresh_token=new_refresh,
            refresh_token_expires_in=refresh_expires,
        )
        return eg1_token
    else:
        print(f"  EG1 token refresh failed: {response.status_code}")
        print(f"  Response: {response.text[:500]}")
        return None


def get_eos_connect_token(eg1_token: str, client_id: str, client_secret: str) -> dict:
    """Exchange EG1 access token for EOS Connect token."""
    credentials = f"{client_id}:{client_secret}"
    basic_auth = base64.b64encode(credentials.encode()).decode()

    data = {
        "grant_type": "external_auth",
        "external_auth_type": "epicgames_access_token",
        "external_auth_token": eg1_token,
        "deployment_id": DEPLOYMENT_ID,
        "nonce": str(uuid.uuid4()),
    }

    response = requests.post(
        EOS_TOKEN_URL,
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data=data,
        timeout=30,
    )

    if response.status_code == 200:
        return response.json()
    else:
        print(f"  EOS token exchange failed: {response.status_code}")
        print(f"  Response: {response.text[:500]}")
        return None


def query_locker_items(eos_token: str, account_id: str) -> dict:
    """Query equipped cosmetics and loadout presets from the Locker Service."""
    url = f"{LOCKER_BASE_URL}/{DEPLOYMENT_ID}/account/{account_id}/items"

    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {eos_token}"},
        timeout=30,
    )

    if response.status_code == 200:
        return response.json()
    else:
        print(f"  Locker query failed: {response.status_code}")
        print(f"  Response: {response.text[:500]}")
        return None


def query_cosmetic_data(eos_token: str, account_id: str, limit: int = 10) -> dict:
    """Query cosmetic item data from the Locker Service."""
    url = f"{LOCKER_BASE_URL}/{DEPLOYMENT_ID}/account/{account_id}/cosmetic-data"

    response = requests.get(
        url,
        headers={"Authorization": f"Bearer {eos_token}"},
        params={"limit": limit},
        timeout=30,
    )

    if response.status_code == 200:
        return response.json()
    else:
        print(f"  Cosmetic data query failed: {response.status_code}")
        print(f"  Response: {response.text[:500]}")
        return None


def main():
    print("=" * 60)
    print("Epic Games Locker Service API Test")
    print("=" * 60)

    # Step 1: Load auth from cache
    print("\n[1] Loading cached authentication...")
    auth = EpicAuth()

    if not auth.access_token or not auth.is_valid:
        print("No valid token. Attempting refresh...")
        if auth.refresh_token:
            if not auth.refresh_access_token():
                print("ERROR: Refresh failed. Please re-login through FA11y.")
                return
        else:
            print("ERROR: No auth available. Please log in through FA11y first.")
            return

    print(f"Authenticated as: {auth.display_name} (ID: {auth.account_id})")
    print(f"Current token format: {'EG1 (JWT)' if auth.access_token.startswith('eg1~') else 'Opaque (hex)'}")

    # Step 2: Get EG1 token if needed
    eg1_token = auth.access_token
    if not eg1_token.startswith("eg1~"):
        print("\n[2] Current token is opaque. Refreshing with token_type=eg1...")
        eg1_token = get_eg1_token(auth)
        if not eg1_token:
            print("ERROR: Could not get EG1 token")
            return
    else:
        print("\n[2] Already have EG1 token, skipping refresh")

    # Step 3: Exchange for EOS Connect token
    print("\n[3] Exchanging EG1 token for EOS Connect token...")
    eos_data = get_eos_connect_token(eg1_token, auth.CLIENT_ID, auth.CLIENT_SECRET)
    if not eos_data:
        print("ERROR: Failed to get EOS Connect token")
        return

    eos_token = eos_data["access_token"]
    product_user_id = eos_data.get("product_user_id", "unknown")
    features = eos_data.get("features", [])
    print(f"EOS token obtained! Product User ID: {product_user_id}")
    print(f"Features: {features}")
    print(f"Expires in: {eos_data.get('expires_in', '?')}s")

    # Step 4: Query locker items (equipped + presets)
    print("\n[4] Querying Locker Service for equipped items and presets...")
    locker_data = query_locker_items(eos_token, product_user_id)
    if not locker_data:
        print("  Retrying with Epic account ID...")
        locker_data = query_locker_items(eos_token, auth.account_id)
    if not locker_data:
        print("ERROR: Failed to query locker items")
        return

    # Parse active loadout group (currently equipped)
    active_loadout = locker_data.get("activeLoadoutGroup", {})
    loadouts = active_loadout.get("loadouts", {})

    print(f"\n  === Currently Equipped (Active Loadout Group) ===")
    print(f"  Loadout categories: {list(loadouts.keys())}")

    for category, loadout_data in loadouts.items():
        slots = loadout_data.get("loadoutSlots", [])
        shuffle = loadout_data.get("shuffleType", "DISABLED")
        print(f"\n  [{category}] (shuffle: {shuffle})")
        for slot in slots:
            slot_template = slot.get("slotTemplate", "")
            equipped = slot.get("equippedItemId", "(empty)")
            customizations = slot.get("itemCustomizations", [])
            slot_name = slot_template.split(":")[-1] if ":" in slot_template else slot_template
            custom_str = ""
            if customizations:
                custom_str = f" [variants: {len(customizations)}]"
            print(f"    {slot_name}: {equipped}{custom_str}")

    # Parse loadout presets (saved loadouts)
    presets = locker_data.get("loadoutPresets", [])
    print(f"\n  === Saved Loadout Presets ({len(presets)}) ===")
    for preset in presets:
        name = preset.get("displayName", "(unnamed)")
        loadout_type = preset.get("loadoutType", "?")
        preset_id = preset.get("presetId", "?")
        preset_index = preset.get("presetIndex", "?")
        print(f"\n  Preset '{name}' (type: {loadout_type}, id: {preset_id}, index: {preset_index})")
        for slot in preset.get("loadoutSlots", []):
            slot_template = slot.get("slotTemplate", "")
            equipped = slot.get("equippedItemId", "(empty)")
            slot_name = slot_template.split(":")[-1] if ":" in slot_template else slot_template
            print(f"    {slot_name}: {equipped}")

    # Loadout group presets
    preset_groups = locker_data.get("loadoutGroupPresets", [])
    if preset_groups:
        print(f"\n  === Loadout Group Presets ({len(preset_groups)}) ===")
        for group in preset_groups:
            print(f"  {json.dumps(group, indent=4)[:500]}")

    # Step 5: Query cosmetic data (sample)
    print(f"\n[5] Querying cosmetic data (sample of 5 items)...")
    cosmetic_data = query_cosmetic_data(eos_token, product_user_id, limit=5)
    if not cosmetic_data:
        print("  Retrying with Epic account ID...")
        cosmetic_data = query_cosmetic_data(eos_token, auth.account_id, limit=5)
    if cosmetic_data:
        items = cosmetic_data.get("cosmeticItems", [])
        print(f"  Got {len(items)} items (sample)")
        for item in items:
            tid = item.get("templateId", "?")
            variants = item.get("ownedVariants", {})
            active = item.get("activeVariants", {})
            extras = []
            if variants:
                extras.append(f"variants={len(variants)}")
            if active:
                extras.append(f"activeVariants={len(active)}")
            extra_str = f" ({', '.join(extras)})" if extras else ""
            print(f"    {tid}{extra_str}")

        has_more = cosmetic_data.get("nextToken")
        print(f"  Has more items: {'yes' if has_more else 'no'}")
    else:
        print("  Could not query cosmetic data")

    # Step 6: Verify MCP operations still work with EG1 token
    print(f"\n[6] Verifying MCP QueryProfile still works with EG1 token...")
    from lib.utilities.epic_auth import LockerAPI
    locker_api = LockerAPI(auth)
    if locker_api.load_profile():
        print(f"  MCP QueryProfile: SUCCESS ({len(locker_api.owned_items)} items)")
    else:
        print(f"  MCP QueryProfile: FAILED")

    print("\n" + "=" * 60)
    print("Test complete! Summary:")
    print(f"  - EG1 token refresh: SUCCESS")
    print(f"  - EOS Connect token exchange: SUCCESS")
    print(f"  - Equipped cosmetics query: {'SUCCESS' if loadouts else 'NO DATA'}")
    print(f"  - Loadout presets: {len(presets)} found")
    print(f"  - Cosmetic data query: {'SUCCESS' if cosmetic_data else 'FAILED'}")
    print(f"  - MCP still works: {'YES' if locker_api.profile_data else 'NO'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
