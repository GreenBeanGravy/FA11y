"""
Diagnostic script for the STW manager.

Uses FA11y's cached Epic auth to hit every endpoint the STW manager talks
to, and dumps the actual schema / counts so bugs in stw_api / stw_world_info
parsers can be fixed against real data instead of guesses.

Run from the FA11y root:

    python stw_diagnose.py          # prints summary + writes logs/stw_diagnose_<ts>.json
    python stw_diagnose.py --dump   # also dumps full campaign profile JSON

Never invokes write operations (no claims, no recycles, no purchases).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime
from typing import Dict, List

# Make sure we're in the FA11y root so relative imports work.
ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import requests

from lib.config.config_manager import config_manager
from lib.utilities.epic_auth import EpicAuth, get_epic_auth_instance

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("stw_diagnose")


def header(title: str) -> None:
    print()
    print("=" * 78)
    print(f" {title}")
    print("=" * 78)


def summarise_items(items: Dict[str, dict], sample_count: int = 3) -> Dict:
    """Group items by top-level templateId prefix; count + sample each."""
    by_prefix: Dict[str, List[dict]] = {}
    for item_id, item in items.items():
        template = item.get("templateId") or ""
        prefix = template.split(":", 1)[0] if ":" in template else "(untyped)"
        by_prefix.setdefault(prefix, []).append({"item_id": item_id, **item})
    summary = {}
    for prefix, bucket in sorted(by_prefix.items(), key=lambda kv: -len(kv[1])):
        summary[prefix] = {
            "count": len(bucket),
            "samples": bucket[:sample_count],
        }
    return summary


def summarise_sub_prefixes(items: Dict[str, dict], top_prefix: str,
                            sample_count: int = 3) -> Dict:
    """Within a prefix (e.g. 'Schematic:'), group by the character class part
    (`Schematic:sid_<type>_<class>_...`). Useful for seeing the second-level
    template shape."""
    sub: Dict[str, List[dict]] = {}
    for item_id, item in items.items():
        template = item.get("templateId") or ""
        if not template.startswith(top_prefix):
            continue
        last = template[len(top_prefix):]
        # Grab the first two "_" segments after the colon.
        key = "_".join(last.lower().split("_")[:2])
        sub.setdefault(key, []).append({"item_id": item_id, **item})
    out = {}
    for k, v in sorted(sub.items(), key=lambda kv: -len(kv[1])):
        out[k] = {
            "count": len(v),
            "samples": v[:sample_count],
        }
    return out


def dump_quest_states(items: Dict[str, dict]) -> Dict:
    """List every Quest: item with its state, for unlocked-zone detection."""
    quests: List[Dict] = []
    state_counter: Counter = Counter()
    zone_hits: Counter = Counter()
    for item_id, item in items.items():
        template = item.get("templateId") or ""
        if not template.startswith("Quest:"):
            continue
        attrs = item.get("attributes") or {}
        state = attrs.get("quest_state", "")
        state_counter[state] += 1
        short = template[len("Quest:"):].lower()
        # Zone heuristic - substring match.
        for zone in ("stonewood", "plankerton", "canny", "twine", "homebase"):
            if zone in short:
                zone_hits[zone] += 1
        quests.append(
            {
                "item_id": item_id,
                "template": template,
                "state": state,
                "attrs_keys": list(attrs.keys()),
            }
        )
    return {
        "total_quests": len(quests),
        "states": dict(state_counter),
        "zone_substring_hits": dict(zone_hits),
        "samples": quests[:30],
    }


def dump_stats_keys(stats_attrs: Dict) -> Dict:
    """List every key in stats.attributes and mark keys likely related to
    zone unlock / progression / homebase."""
    INTEREST = (
        "unlock", "region", "theater", "homebase", "ventures", "phoenix",
        "completed", "tutorial", "daily_rewards", "difficulty",
    )
    interesting = {}
    other = []
    for key, value in sorted(stats_attrs.items()):
        if any(marker in key.lower() for marker in INTEREST):
            interesting[key] = value if not isinstance(value, (dict, list)) else f"<{type(value).__name__}>"
        else:
            other.append(key)
    return {
        "interesting": interesting,
        "all_keys": sorted(stats_attrs.keys()),
    }


def dump_card_pack_items(items: Dict[str, dict]) -> Dict:
    """Look at every item whose templateId could be a llama / card pack.
    Uses broad substring matches since the schema varies across seasons."""
    candidates = []
    for item_id, item in items.items():
        template = (item.get("templateId") or "")
        lower = template.lower()
        if any(marker in lower for marker in (
            "cardpack", "card_pack", "pack:", "llama", "preroll", "offer:",
            "prerolledoffer", "heromegastore",
        )):
            candidates.append({"item_id": item_id, **item})
    return {
        "count": len(candidates),
        "samples": candidates[:10],
    }


def dump_hero_sample(items: Dict[str, dict]) -> Dict:
    """Pick any one Hero item and dump its full JSON so we can see the
    exact shape of stats/attributes."""
    out = {"found": 0, "first_full": None, "attrs_keys": None}
    for item_id, item in items.items():
        if (item.get("templateId") or "").startswith("Hero:"):
            out["found"] += 1
            if out["first_full"] is None:
                out["first_full"] = {"item_id": item_id, **item}
                out["attrs_keys"] = sorted((item.get("attributes") or {}).keys())
    return out


def dump_schematic_sample(items: Dict[str, dict]) -> Dict:
    out = {"found": 0, "first_full": None, "attrs_keys": None}
    for item_id, item in items.items():
        if (item.get("templateId") or "").startswith("Schematic:"):
            out["found"] += 1
            if out["first_full"] is None:
                out["first_full"] = {"item_id": item_id, **item}
                out["attrs_keys"] = sorted((item.get("attributes") or {}).keys())
    return out


def dump_worker_sample(items: Dict[str, dict]) -> Dict:
    out = {"found": 0, "samples": [], "squad_ids_seen": Counter()}
    for item_id, item in items.items():
        if not (item.get("templateId") or "").startswith("Worker:"):
            continue
        out["found"] += 1
        attrs = item.get("attributes") or {}
        sid = attrs.get("squad_id") or ""
        if sid:
            out["squad_ids_seen"][sid] += 1
        if len(out["samples"]) < 4:
            out["samples"].append({"item_id": item_id, **item})
    out["squad_ids_seen"] = dict(out["squad_ids_seen"])
    return out


def fetch_campaign_profile(auth: EpicAuth) -> Dict:
    url = f"https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/game/v2/profile/{auth.account_id}/client/QueryProfile"
    r = requests.post(
        url,
        params={"profileId": "campaign", "rvn": -1},
        headers={
            "Authorization": f"Bearer {auth.access_token}",
            "Content-Type": "application/json",
        },
        json={},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    return (payload.get("profileChanges") or [{}])[0].get("profile") or {}


def fetch_common_core_profile(auth: EpicAuth) -> Dict:
    url = f"https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/game/v2/profile/{auth.account_id}/client/QueryProfile"
    r = requests.post(
        url,
        params={"profileId": "common_core", "rvn": -1},
        headers={
            "Authorization": f"Bearer {auth.access_token}",
            "Content-Type": "application/json",
        },
        json={},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    return (payload.get("profileChanges") or [{}])[0].get("profile") or {}


def fetch_world_info(auth: EpicAuth) -> Dict:
    url = "https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/world/info"
    r = requests.get(
        url,
        params={"lang": "en-US"},
        headers={"Authorization": f"Bearer {auth.access_token}"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", action="store_true",
                        help="Also write the full campaign profile JSON")
    args = parser.parse_args()

    # Ensure EpicAuth singleton loads cached token.
    auth = get_epic_auth_instance()
    if not auth.access_token or not auth.account_id:
        print("ERROR: FA11y has no cached Epic auth. Run FA11y and sign in first.")
        return 2

    print(f"Authenticated as {auth.display_name or '?'} ({auth.account_id})")

    # --- Campaign profile ---------------------------------------------
    header("CAMPAIGN PROFILE")
    try:
        campaign = fetch_campaign_profile(auth)
    except requests.HTTPError as e:
        print(f"HTTP error fetching campaign profile: {e} / body: {e.response.text[:500] if e.response else ''}")
        return 3
    items = (campaign.get("items") or {})
    stats_attrs = (campaign.get("stats") or {}).get("attributes") or {}
    print(f"campaign.items total: {len(items)}")
    print(f"campaign.stats.attributes keys: {len(stats_attrs)}")

    # --- Item prefixes ------------------------------------------------
    header("ITEM COUNT BY PREFIX")
    prefix_summary = summarise_items(items, sample_count=0)
    for prefix, info in prefix_summary.items():
        print(f"  {prefix:25s}  {info['count']:>6d}")

    # --- Heroes -------------------------------------------------------
    header("HERO SAMPLE (for friendly-name / level extraction)")
    hero_info = dump_hero_sample(items)
    print(f"Hero count: {hero_info['found']}")
    print(f"Hero attributes keys: {hero_info['attrs_keys']}")
    if hero_info["first_full"]:
        print("Sample hero (full JSON):")
        print(json.dumps(hero_info["first_full"], indent=2)[:1200])

    # --- Schematics ---------------------------------------------------
    header("SCHEMATIC SAMPLE")
    schem_info = dump_schematic_sample(items)
    print(f"Schematic count: {schem_info['found']}")
    print(f"Schematic attributes keys: {schem_info['attrs_keys']}")
    if schem_info["first_full"]:
        print("Sample schematic (full JSON):")
        print(json.dumps(schem_info["first_full"], indent=2)[:1200])

    # --- Survivors / Workers ------------------------------------------
    header("WORKER (survivor/defender) SAMPLE")
    worker_info = dump_worker_sample(items)
    print(f"Worker count: {worker_info['found']}")
    print(f"Distinct squad_id values: {len(worker_info['squad_ids_seen'])}")
    for sid, cnt in list(worker_info["squad_ids_seen"].items())[:15]:
        print(f"  {sid:60s}  {cnt}")
    if worker_info["samples"]:
        print("Sample worker:")
        print(json.dumps(worker_info["samples"][0], indent=2)[:1200])

    # --- Quest-based zone unlock detection ----------------------------
    header("QUEST STATE ANALYSIS (zone unlock detection)")
    quest_info = dump_quest_states(items)
    print(f"Total Quest: items: {quest_info['total_quests']}")
    print(f"Quest state counts: {quest_info['states']}")
    print(f"Zone substring hits across ALL quests (any state): {quest_info['zone_substring_hits']}")

    # The key question: what 'Claimed' or 'Completed' quests mention each zone?
    claimed_or_completed = [q for q in quest_info["samples"]
                            if q["state"] in ("Claimed", "Completed")]
    print(f"\nFirst 15 Claimed/Completed quests:")
    for q in claimed_or_completed[:15]:
        print(f"  [{q['state']:10s}] {q['template']}")

    # --- Stats.attributes keys ---------------------------------------
    header("CAMPAIGN stats.attributes (interesting subset)")
    stats_info = dump_stats_keys(stats_attrs)
    for k, v in stats_info["interesting"].items():
        print(f"  {k:45s}  {v!r}")

    # --- Llama / card pack candidates --------------------------------
    header("LLAMA / CARDPACK CANDIDATES")
    llama_info = dump_card_pack_items(items)
    print(f"Total candidates: {llama_info['count']}")
    if llama_info["samples"]:
        print(json.dumps(llama_info["samples"][0], indent=2)[:1500])

    # --- World info --------------------------------------------------
    header("WORLD INFO (/world/info)")
    try:
        world = fetch_world_info(auth)
    except requests.HTTPError as e:
        print(f"HTTP error: {e}")
        world = None
    if world is not None:
        theaters = world.get("theaters", []) or []
        missions = world.get("missions", []) or []
        alerts = world.get("missionAlerts", []) or []
        print(f"theaters: {len(theaters)}")
        print(f"missions (by theater): {len(missions)} buckets")
        print(f"missionAlerts (by theater): {len(alerts)} buckets")

        if theaters:
            print("\nTheaters (uniqueId / displayName / theaterSlot):")
            for t in theaters[:8]:
                name = (t.get("displayName") or {})
                if isinstance(name, dict):
                    name = name.get("sourceString") or "-"
                print(f"  slot={t.get('theaterSlot')!r:5}  id={(t.get('uniqueId') or '')[:10]}...  name={name!r}")
        # Dump one missionAlerts bucket
        if alerts:
            print("\nFirst missionAlerts bucket keys:")
            print(json.dumps(alerts[0], indent=2)[:1200])
        if missions:
            print("\nFirst missions bucket sample mission:")
            bucket = missions[0]
            mlist = bucket.get("missions") or []
            if mlist:
                print(json.dumps(mlist[0], indent=2)[:1200])

    # --- common_core for V-Bucks and gift boxes (quick) --------------
    header("COMMON_CORE (V-Bucks / purchases)")
    try:
        common = fetch_common_core_profile(auth)
    except requests.HTTPError as e:
        print(f"HTTP error: {e}")
        common = None
    if common:
        cc_items = common.get("items") or {}
        cc_stats = (common.get("stats") or {}).get("attributes") or {}
        print(f"common_core.items total: {len(cc_items)}")
        # Look for currency items
        for item_id, item in list(cc_items.items())[:20]:
            tid = item.get("templateId") or ""
            qty = item.get("quantity", 0)
            if "mtx" in tid.lower() or "voucher" in tid.lower() or "currency" in tid.lower():
                print(f"  {tid}  quantity={qty}")

    # --- Write full dump ----------------------------------------------
    if args.dump:
        os.makedirs("logs", exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dump_path = os.path.join("logs", f"stw_diagnose_{stamp}.json")
        with open(dump_path, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "campaign": campaign,
                    "common_core": common,
                    "world_info": world,
                },
                fh,
                indent=2,
                default=str,
            )
        print(f"\nWrote full dump: {dump_path}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
