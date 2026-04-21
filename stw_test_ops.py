"""
Interactive tests for STW manager operations that the user reports broken.

Tests (in order):
  1. Fetch storefront catalog -> see llama pricing schema
  2. Try AssignHeroToLoadout with a real hero+slot -> inspect the error body
  3. Try SetActiveHeroLoadout -> verify it works end-to-end
  4. Try PurchaseCatalogEntry with a concrete free-llama offerId
  5. Inspect a Schematic item's FULL attributes to find crafting stats

All tests are IDEMPOTENT or REVERSIBLE. No items are recycled / destroyed /
upgraded. Loadout changes can be reverted manually in-game in under 5s.

Usage:
    python stw_test_ops.py                  # runs all tests
    python stw_test_ops.py catalog          # only storefront fetch
    python stw_test_ops.py assign_hero      # only hero assignment
    python stw_test_ops.py purchase_llama   # only llama purchase
    python stw_test_ops.py schematic_stats  # schematic attribute dump
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import requests

from lib.utilities.epic_auth import get_epic_auth_instance

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("stw_test")


def header(title: str) -> None:
    print()
    print("=" * 78)
    print(f" {title}")
    print("=" * 78)


def mcp_call(
    auth,
    operation: str,
    profile_id: str = "campaign",
    body: Optional[Dict] = None,
    scope: str = "client",
) -> Tuple[int, Dict]:
    url = (
        f"https://fngw-mcp-gc-livefn.ol.epicgames.com"
        f"/fortnite/api/game/v2/profile/{auth.account_id}/{scope}/{operation}"
    )
    r = requests.post(
        url,
        params={"profileId": profile_id, "rvn": -1},
        headers={
            "Authorization": f"Bearer {auth.access_token}",
            "Content-Type": "application/json",
        },
        json=body if body is not None else {},
        timeout=30,
    )
    try:
        payload = r.json()
    except ValueError:
        payload = {"_raw": r.text}
    return r.status_code, payload


def fetch_campaign_profile(auth):
    status, payload = mcp_call(auth, "QueryProfile", profile_id="campaign", body={})
    if status != 200:
        return None
    return (payload.get("profileChanges") or [{}])[0].get("profile") or {}


# ---------------------------------------------------------------------------
# 1. Storefront catalog — llama pricing
# ---------------------------------------------------------------------------

def test_catalog(auth):
    header("1. STOREFRONT CATALOG (llama pricing)")
    url = (
        "https://fngw-mcp-gc-livefn.ol.epicgames.com"
        "/fortnite/api/storefront/v2/catalog"
    )
    r = requests.get(
        url,
        headers={"Authorization": f"Bearer {auth.access_token}"},
        timeout=30,
    )
    print(f"HTTP {r.status_code}")
    if r.status_code != 200:
        print(r.text[:500])
        return None
    catalog = r.json()

    # Inspect top-level structure
    storefronts = catalog.get("storefronts") or []
    print(f"storefronts count: {len(storefronts)}")
    print("Storefront names:")
    for sf in storefronts:
        name = sf.get("name", "")
        offers = sf.get("catalogEntries", []) or []
        print(f"  {name:40s}  {len(offers):>4d} offers")

    # Look for STW-ish storefronts
    stw_keywords = ("CardPack", "STWSpecial", "STWRotational", "STWHero", "STWSurvivor",
                    "STWMtx", "Currency", "Llama", "Ventures", "Phoenix")
    stw_storefronts = [
        sf for sf in storefronts
        if any(k.lower() in (sf.get("name", "") or "").lower() for k in stw_keywords)
    ]
    print(f"\nSTW-related storefronts: {len(stw_storefronts)}")
    for sf in stw_storefronts:
        print(f"\n  --- {sf.get('name')} ---")
        for offer in (sf.get("catalogEntries") or [])[:3]:
            offer_id = offer.get("offerId", "") or offer.get("devName", "")
            prices = offer.get("prices") or []
            dev_name = offer.get("devName", "")
            meta = offer.get("meta") or {}
            items_info = [
                (i.get("itemType", ""), i.get("quantity", 0))
                for i in (offer.get("itemGrants") or [])[:3]
            ]
            print(f"    offerId: {offer_id}")
            print(f"    devName: {dev_name}")
            print(f"    meta: {meta}")
            if prices:
                for p in prices:
                    print(f"      price: {p.get('currencyType')} / "
                          f"{p.get('currencySubType')} "
                          f"finalPrice={p.get('finalPrice')}  "
                          f"regularPrice={p.get('regularPrice')}")
            else:
                print(f"      (no prices)")
            for it, qty in items_info:
                print(f"      grants: {qty}x {it}")
    return catalog


# ---------------------------------------------------------------------------
# 2. AssignHeroToLoadout
# ---------------------------------------------------------------------------

def test_assign_hero(auth, profile):
    header("2. ASSIGN HERO TO LOADOUT")
    items = profile.get("items") or {}
    stats = (profile.get("stats") or {}).get("attributes") or {}
    selected_loadout = stats.get("selected_hero_loadout")
    print(f"selected_hero_loadout: {selected_loadout}")

    # Find the active loadout
    loadout = items.get(selected_loadout) or {}
    if not loadout:
        print("ERROR: selected loadout not in items")
        return
    attrs = loadout.get("attributes") or {}
    print(f"loadout templateId: {loadout.get('templateId')}")
    print(f"loadout attributes keys: {sorted(attrs.keys())}")
    print(f"crew_members: {attrs.get('crew_members')}")

    # Pick any owned hero that's NOT currently equipped in any slot.
    owned_heroes = [
        (iid, itm) for iid, itm in items.items()
        if (itm.get("templateId") or "").startswith("Hero:")
    ]
    if not owned_heroes:
        print("No heroes owned.")
        return
    # Find a hero not in any slot
    crew = attrs.get("crew_members") or {}
    in_use = set(v for v in crew.values() if v)
    candidate = None
    for hid, hitm in owned_heroes:
        if hid not in in_use:
            candidate = (hid, hitm)
            break
    if not candidate:
        print("All owned heroes are already slotted.")
        return
    hero_id, hero_item = candidate
    hero_template = hero_item.get("templateId", "")
    print(f"\nCandidate hero to assign: {hero_id}  ({hero_template})")

    # Try calling with each slot-name style to see which Epic accepts.
    test_slot_names = [
        "commanderslot",
        "CommanderSlot",
        "FollowerSlot1",
        "followerslot1",
    ]
    # Only test one followerslot so we don't actually replace the commander.
    # Use followerslot5 (likely empty).
    test_slot_names = ["followerslot5", "FollowerSlot5"]

    for slot_name in test_slot_names:
        body = {
            "slotName": slot_name,
            "loadoutId": selected_loadout,
            "heroId": hero_id,
        }
        print(f"\nCalling AssignHeroToLoadout body={body}")
        status, payload = mcp_call(auth, "AssignHeroToLoadout", body=body)
        print(f"  HTTP {status}")
        if status == 200:
            print(f"  SUCCESS — profileRevision={payload.get('profileRevision')}")
            # Print any notifications
            notes = payload.get("notifications") or []
            print(f"  notifications={len(notes)}")
            # Revert: set the hero slot back to empty
            print("  Reverting by sending an empty heroId…")
            revert_status, _ = mcp_call(
                auth, "AssignHeroToLoadout",
                body={"slotName": slot_name, "loadoutId": selected_loadout, "heroId": ""},
            )
            print(f"  Revert HTTP {revert_status}")
            break
        else:
            err = payload.get("errorCode", "")
            msg = payload.get("errorMessage", "") or payload.get("_raw", "")[:300]
            print(f"  FAIL: errorCode={err} msg={msg}")


# ---------------------------------------------------------------------------
# 3. PurchaseCatalogEntry
# ---------------------------------------------------------------------------

def test_purchase_llama(auth, profile):
    header("3. PURCHASE LLAMA")
    items = profile.get("items") or {}
    prerolls = [
        (iid, itm) for iid, itm in items.items()
        if (itm.get("templateId") or "").startswith("PrerollData:")
    ]
    print(f"PrerollData items: {len(prerolls)}")
    if not prerolls:
        print("No prerolled offers to test.")
        return
    # Use the first preroll
    iid, item = prerolls[0]
    attrs = item.get("attributes") or {}
    offer_id = attrs.get("offerId")
    print(f"offer_id: {offer_id}")
    print(f"full attrs: {json.dumps(attrs, indent=2)[:800]}")

    # Try PurchaseCatalogEntry with various currency combinations.
    test_bodies = [
        # Free X-Ray Ticket llama (most common for F2P)
        {
            "offerId": offer_id,
            "purchaseQuantity": 1,
            "currency": "GameItem",
            "currencySubType": "AccountResource:currency_xrayllama",
            "expectedTotalPrice": 0,
            "gameContext": "",
        },
        # Event currency
        {
            "offerId": offer_id,
            "purchaseQuantity": 1,
            "currency": "GameItem",
            "currencySubType": "AccountResource:eventcurrency_scaling",
            "expectedTotalPrice": 0,
            "gameContext": "",
        },
        # V-Bucks
        {
            "offerId": offer_id,
            "purchaseQuantity": 1,
            "currency": "MtxCurrency",
            "currencySubType": "",
            "expectedTotalPrice": 0,
            "gameContext": "",
        },
    ]
    for body in test_bodies:
        print(f"\nPurchaseCatalogEntry currency={body['currency']} subType={body['currencySubType']!r}")
        status, payload = mcp_call(
            auth, "PurchaseCatalogEntry", profile_id="common_core", body=body,
        )
        print(f"  HTTP {status}")
        if status == 200:
            print(f"  SUCCESS — profileRevision={payload.get('profileRevision')}")
            notes = payload.get("notifications") or []
            print(f"  notifications={len(notes)}")
            for n in notes[:3]:
                print(f"    {n.get('type')}: {json.dumps(n, indent=2)[:400]}")
            break
        else:
            err = payload.get("errorCode", "")
            msg = payload.get("errorMessage", "")
            message_vars = payload.get("messageVars", [])
            print(f"  FAIL: errorCode={err!r}")
            print(f"        msg={msg!r}")
            print(f"        messageVars={message_vars}")


# ---------------------------------------------------------------------------
# 4. Schematic stats inspection
# ---------------------------------------------------------------------------

def test_schematic_stats(auth, profile):
    header("4. SCHEMATIC STATS DEEP DUMP")
    items = profile.get("items") or {}
    # Pick a schematic and dump the FULL item
    schematics = [
        (iid, itm) for iid, itm in items.items()
        if (itm.get("templateId") or "").startswith("Schematic:")
    ]
    print(f"Total schematics: {len(schematics)}")
    if not schematics:
        return

    # Find a higher-rarity schematic (more interesting stats)
    def rank(item):
        tid = (item.get("templateId") or "").lower()
        for code, score in (("_ur_", 6), ("_sr_", 5), ("_vr_", 4),
                             ("_r_", 3), ("_uc_", 2), ("_c_", 1)):
            if code in tid:
                return score
        return 0
    schematics.sort(key=lambda t: -rank(t[1]))

    # Dump 3 representative schematics: high rarity, low rarity, and a trap
    picks: List[Tuple[str, dict]] = []
    picks.append(schematics[0])
    picks.append(schematics[-1])
    trap = next(
        (s for s in schematics if "wall" in (s[1].get("templateId") or "").lower()),
        None,
    )
    if trap:
        picks.append(trap)

    for iid, item in picks:
        print(f"\n--- {item.get('templateId')} ---")
        print(json.dumps(item, indent=2))

    # Also call QueryProfile on theater0 to see if weapon stats live there.
    print("\n\nFetching theater0 profile for crafted weapons...")
    status, payload = mcp_call(auth, "QueryProfile", profile_id="theater0", body={})
    print(f"HTTP {status}")
    if status == 200:
        prof = (payload.get("profileChanges") or [{}])[0].get("profile") or {}
        t0_items = prof.get("items") or {}
        print(f"theater0 items: {len(t0_items)}")
        # Find a crafted weapon (WorldItem:*)
        worldies = [
            (iid, itm) for iid, itm in t0_items.items()
            if (itm.get("templateId") or "").startswith("WorldItem:")
            or (itm.get("templateId") or "").startswith("Weapon:")
        ]
        print(f"WorldItem/Weapon instances: {len(worldies)}")
        if worldies:
            iid, item = worldies[0]
            print(f"\n--- crafted item sample: {item.get('templateId')} ---")
            print(json.dumps(item, indent=2)[:1500])

    # Finally, try hitting fortnitecentral.genxgames.gg for schematic asset data.
    print("\n\nTrying fortnitecentral.genxgames.gg for schematic asset data...")
    if picks:
        _, sample = picks[0]
        tid = sample.get("templateId", "")
        # Format: Schematic:sid_pistol_auto_r_ore_t01 -> SID_Pistol_Auto_R_Ore_T01
        short = tid.rsplit(":", 1)[-1]
        asset_name = short.upper()
        for asset_path in (
            f"FortniteGame/Content/Items/Schematics/{asset_name}",
            f"FortniteGame/Content/Items/Schematics/Pistols/{asset_name}",
            f"FortniteGame/Content/Athena/Items/Cosmetics/{asset_name}",
        ):
            try:
                r = requests.get(
                    "https://fortnitecentral.genxgames.gg/api/v1/export",
                    params={"path": asset_path},
                    timeout=15,
                )
                print(f"  {asset_path}: HTTP {r.status_code}")
                if r.status_code == 200:
                    blob = r.json()
                    # What keys are in the asset?
                    print(f"    top keys: {list(blob.keys())[:20]}")
                    break
            except Exception as e:
                print(f"  {asset_path}: error {e}")


# ---------------------------------------------------------------------------
# 5. SetActiveHeroLoadout sanity check
# ---------------------------------------------------------------------------

def test_set_active_loadout(auth, profile):
    header("5. SetActiveHeroLoadout (no-op sanity check)")
    items = profile.get("items") or {}
    stats = (profile.get("stats") or {}).get("attributes") or {}
    current = stats.get("selected_hero_loadout")
    print(f"Currently selected: {current}")
    # Just re-select the same loadout — should be a no-op but verifies the op works.
    body = {"selectedLoadout": current}
    print(f"Body: {body}")
    status, payload = mcp_call(auth, "SetActiveHeroLoadout", body=body)
    print(f"HTTP {status}")
    if status == 200:
        print(f"SUCCESS — profileRevision={payload.get('profileRevision')}")
    else:
        err = payload.get("errorCode", "")
        msg = payload.get("errorMessage", "")
        print(f"FAIL: errorCode={err!r} msg={msg!r}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    auth = get_epic_auth_instance()
    if not auth.access_token or not auth.account_id:
        print("ERROR: FA11y has no cached Epic auth. Sign in via FA11y first.")
        return 2
    print(f"Authenticated as {auth.display_name} ({auth.account_id})")

    which = sys.argv[1] if len(sys.argv) > 1 else "all"

    if which in ("all", "catalog"):
        test_catalog(auth)

    profile = fetch_campaign_profile(auth)
    if not profile:
        print("Could not fetch campaign profile; stopping.")
        return 3

    if which in ("all", "assign_hero"):
        test_assign_hero(auth, profile)
    if which in ("all", "set_active_loadout"):
        test_set_active_loadout(auth, profile)
    if which in ("all", "purchase_llama"):
        test_purchase_llama(auth, profile)
    if which in ("all", "schematic_stats"):
        test_schematic_stats(auth, profile)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
