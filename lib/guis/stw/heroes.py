"""
Hero loadouts and squad assignment STW sub-dialogs.

Includes:
  - ActiveLoadoutDialog: switch active loadout, assign heroes to slots,
    swap team perk and gadgets.
  - SurvivorSquadsDialog: list the 8 survivor squads and assign survivors
    to slots.
  - DefenderSquadsDialog: list the defender slots and assign defenders.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import wx

from lib.guis.stw.base import StwSubDialog, speak_later
from lib.stw.api import format_template_display, parse_template_name

logger = logging.getLogger(__name__)


# Epic's hero loadout schema uses lowercase keys under attributes.crew_members.
# We display capitalized labels but pass the lowercase keys to the MCP API.
HERO_LOADOUT_SLOTS = [
    ("commanderslot", "Commander"),
    ("followerslot1", "Follower 1"),
    ("followerslot2", "Follower 2"),
    ("followerslot3", "Follower 3"),
    ("followerslot4", "Follower 4"),
    ("followerslot5", "Follower 5"),
]

SURVIVOR_SQUAD_IDS = [
    "squad_attribute_medicine_emtsquad",
    "squad_attribute_medicine_traininteam",
    "squad_attribute_arms_fireteamalpha",
    "squad_attribute_arms_closeassaultsquad",
    "squad_attribute_synthesis_corpsofengineering",
    "squad_attribute_synthesis_thethinktank",
    "squad_attribute_scavenging_gadgeteers",
    "squad_attribute_scavenging_scoutingparty",
]

SURVIVOR_SQUAD_DISPLAY = {
    "squad_attribute_medicine_emtsquad": "EMT Squad (Medicine)",
    "squad_attribute_medicine_traininteam": "Training Team (Medicine)",
    "squad_attribute_arms_fireteamalpha": "Fire Team Alpha (Arms)",
    "squad_attribute_arms_closeassaultsquad": "Close Assault Squad (Arms)",
    "squad_attribute_synthesis_corpsofengineering": "Corps of Engineering (Synthesis)",
    "squad_attribute_synthesis_thethinktank": "Think Tank (Synthesis)",
    "squad_attribute_scavenging_gadgeteers": "Gadgeteers (Scavenging)",
    "squad_attribute_scavenging_scoutingparty": "Scouting Party (Scavenging)",
}


def _to_camel(lower_slot: str) -> str:
    """followerslot1 -> FollowerSlot1 (for older schema compat)."""
    if not lower_slot:
        return ""
    # Manually uppercase the first letter and the letter after 'slot'.
    out = lower_slot.capitalize()
    marker = "slot"
    idx = out.lower().find(marker)
    if idx != -1:
        end = idx + len(marker)
        out = out[:idx] + "Slot" + out[end:]
    return out


# ---------------------------------------------------------------------------
# Shared: hero chooser
# ---------------------------------------------------------------------------

def _select_item_from_list(
    parent,
    title: str,
    prompt: str,
    items: List[Tuple[str, str]],
) -> Optional[str]:
    """Single-select dialog over a [(item_id, display)] list. Returns the
    chosen item_id or None on cancel. Note: an empty-string item_id is a
    valid selection (used for 'clear slot') — only `None` means cancelled."""
    if not items:
        wx.MessageBox("Nothing to choose.", title, wx.OK | wx.ICON_INFORMATION, parent)
        return None
    dlg = wx.SingleChoiceDialog(parent, prompt, title, [d for _id, d in items])
    try:
        if dlg.ShowModal() != wx.ID_OK:
            return None
        selected = dlg.GetSelection()
        if selected < 0 or selected >= len(items):
            return None
        return items[selected][0]
    finally:
        dlg.Destroy()


# ---------------------------------------------------------------------------
# Active loadout
# ---------------------------------------------------------------------------

class ActiveLoadoutDialog(StwSubDialog):
    """Shows the active hero loadout and lets the user swap hero in slots.

    The hero loadouts live as profile items with templateId
    `CampaignHeroLoadout:DefaultCampaignHeroLoadout_A..E`. The active one
    is stored in `stats.selected_hero_loadout` as a profile-item GUID.
    """

    def __init__(self, parent, stw_api):
        self._loadout_choice: Optional[wx.Choice] = None
        self._slot_list: Optional[wx.ListCtrl] = None
        self._loadouts: List[Tuple[str, dict]] = []  # (itemId, item)
        self._active_loadout_id: str = ""
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Active Loadout",
            help_id="SaveTheWorldActiveLoadout",
            default_size=(780, 560),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        intro = wx.StaticText(
            self,
            label=(
                "Switch your active hero loadout, and assign heroes to Commander "
                "and Follower slots. Changes take effect immediately."
            ),
        )
        sizer.Add(intro, 0, wx.ALL | wx.EXPAND, 5)

        top_row = wx.BoxSizer(wx.HORIZONTAL)
        top_row.Add(wx.StaticText(self, label="Active loadout:"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._loadout_choice = wx.Choice(self)
        self._loadout_choice.Bind(wx.EVT_CHOICE, self._on_loadout_choice)
        top_row.Add(self._loadout_choice, 0, wx.RIGHT, 10)
        sizer.Add(top_row, 0, wx.ALL | wx.EXPAND, 5)

        self._slot_list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._slot_list.InsertColumn(0, "Slot", width=140)
        self._slot_list.InsertColumn(1, "Hero", width=320)
        self._slot_list.InsertColumn(2, "Rarity", width=100)
        self._slot_list.InsertColumn(3, "Tier", width=60)
        self._slot_list.InsertColumn(4, "Level", width=60)
        sizer.Add(self._slot_list, 1, wx.EXPAND | wx.ALL, 5)

        # Show team perk and gadgets as a secondary read-only panel.
        self._extras_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
            size=(-1, 80),
        )
        sizer.Add(self._extras_text, 0, wx.EXPAND | wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        assign_btn = wx.Button(self, label="&Assign Hero to Selected Slot")
        assign_btn.Bind(wx.EVT_BUTTON, self._on_assign)
        sizer.Add(assign_btn, 0, wx.ALL, 5)
        clear_btn = wx.Button(self, label="C&lear Loadout")
        clear_btn.Bind(wx.EVT_BUTTON, self._on_clear)
        sizer.Add(clear_btn, 0, wx.ALL, 5)

    # -- Data ---------------------------------------------------------
    def _populate(self) -> None:
        self.stw_api.query_profile()
        items = self.stw_api._items()

        self._loadouts = [
            (iid, itm)
            for iid, itm in items.items()
            if (itm.get("templateId") or "").startswith("CampaignHeroLoadout:")
        ]
        stats = self.stw_api._stats()
        self._active_loadout_id = stats.get("selected_hero_loadout", "") or ""
        logger.info(
            f"ActiveLoadoutDialog: {len(self._loadouts)} loadout(s), "
            f"active={self._active_loadout_id[:8]}..."
        )

        self._loadout_choice.Clear()
        for iid, itm in self._loadouts:
            attrs = itm.get("attributes") or {}
            name = (
                attrs.get("loadout_name")
                or f"Loadout #{attrs.get('loadout_index', '?')}"
            )
            active_marker = " (active)" if iid == self._active_loadout_id else ""
            self._loadout_choice.Append(f"{name}{active_marker}")
        # Select active loadout.
        if self._loadouts:
            for idx, (iid, _) in enumerate(self._loadouts):
                if iid == self._active_loadout_id:
                    self._loadout_choice.SetSelection(idx)
                    break
            else:
                self._loadout_choice.SetSelection(0)
                self._active_loadout_id = self._loadouts[0][0]

        self._refresh_slot_list()

    def _active_loadout_attrs(self) -> Dict:
        for iid, itm in self._loadouts:
            if iid == self._active_loadout_id:
                return itm.get("attributes") or {}
        return {}

    def _refresh_slot_list(self) -> None:
        self._slot_list.DeleteAllItems()
        attrs = self._active_loadout_attrs()
        crew = attrs.get("crew_members") or attrs.get("crew_slots_items") or {}
        items = self.stw_api._items()
        unlocked_follower_count = self.stw_api.get_unlocked_follower_slots()
        logger.info(
            f"ActiveLoadoutDialog: {unlocked_follower_count} follower slots unlocked"
        )
        for idx, (slot_key, slot_label) in enumerate(HERO_LOADOUT_SLOTS):
            hero_id = ""
            if isinstance(crew, dict):
                hero_id = (
                    crew.get(slot_key)
                    or crew.get(slot_key.capitalize())
                    or crew.get(_to_camel(slot_key))
                    or ""
                )
            # Detect whether this slot is unlocked.
            is_locked = False
            if slot_key.startswith("followerslot"):
                try:
                    slot_num = int(slot_key[len("followerslot"):])
                    if slot_num > unlocked_follower_count:
                        is_locked = True
                except ValueError:
                    pass

            if is_locked:
                hero_name = "(locked — complete homebase quest)"
                rarity = ""
                tier = ""
                level = ""
            elif hero_id:
                hero = items.get(hero_id) or {}
                template_id = hero.get("templateId", "")
                parsed = parse_template_name(template_id)
                hero_name = parsed["name"] or template_id
                rarity = parsed["rarity"]
                tier = f"T{parsed['tier']}" if parsed["tier"] else ""
                level = str((hero.get("attributes") or {}).get("level", "") or "")
            else:
                hero_name = "(empty)"
                rarity = ""
                tier = ""
                level = ""

            label = slot_label + (" [LOCKED]" if is_locked else "")
            self._slot_list.InsertItem(idx, label)
            self._slot_list.SetItem(idx, 1, hero_name)
            self._slot_list.SetItem(idx, 2, rarity)
            self._slot_list.SetItem(idx, 3, tier)
            self._slot_list.SetItem(idx, 4, level)

        # Team perk + gadgets panel.
        extras: List[str] = []
        team_perk_id = attrs.get("team_perk")
        if team_perk_id:
            perk_item = items.get(team_perk_id) or {}
            tpl = perk_item.get("templateId", "")
            extras.append(
                f"Team Perk: {format_template_display(tpl) if tpl else team_perk_id}"
            )
        else:
            extras.append("Team Perk: (none)")
        gadgets = attrs.get("gadgets") or []
        if gadgets:
            for g in gadgets:
                if isinstance(g, dict):
                    gad = g.get("gadget", "")
                    slot = g.get("slot_index", "?")
                    extras.append(
                        f"Gadget slot {slot}: {format_template_display(gad) if gad else '(none)'}"
                    )
        else:
            extras.append("Gadgets: (none)")
        self._extras_text.SetValue("\n".join(extras))

    # -- Events -------------------------------------------------------
    def _on_loadout_choice(self, _evt: wx.CommandEvent) -> None:
        idx = self._loadout_choice.GetSelection()
        if idx < 0 or idx >= len(self._loadouts):
            return
        new_id = self._loadouts[idx][0]
        if new_id == self._active_loadout_id:
            return
        ok = self.stw_api.set_active_hero_loadout(new_id)
        if ok:
            self._active_loadout_id = new_id
            speak_later("Loadout switched.")
            self._refresh_slot_list()
        else:
            self.show_error("Could not switch loadout.")

    def _on_assign(self, _evt: wx.CommandEvent) -> None:
        idx = self._slot_list.GetFirstSelected()
        if idx < 0:
            self.show_info("Select a slot first.", caption="No Selection")
            return
        slot_key, slot_label = HERO_LOADOUT_SLOTS[idx]

        # Refuse if the slot is locked.
        unlocked_follower_count = self.stw_api.get_unlocked_follower_slots()
        if slot_key.startswith("followerslot"):
            try:
                slot_num = int(slot_key[len("followerslot"):])
                if slot_num > unlocked_follower_count:
                    self.show_error(
                        f"{slot_label} is locked. You have {unlocked_follower_count} "
                        f"of 5 follower slots unlocked. Complete the \"New Follower "
                        f"Slot\" homebase quest to unlock the next one."
                    )
                    return
            except ValueError:
                pass

        # Build list of candidate heroes. Only assignable (non-overflow).
        heroes = self.stw_api.get_assignable_heroes()
        if not heroes:
            self.show_error(
                "No assignable heroes found. Heroes may be in overflow — "
                "recycle or transform them in-game to clear overflow."
            )
            return

        options: List[Tuple[str, str]] = [("", "(clear slot)")]
        for hero_id, item in heroes:
            tid = item.get("templateId", "")
            level = str((item.get("attributes") or {}).get("level", "") or "")
            options.append((hero_id, format_template_display(tid, level=level)))
        options.sort(key=lambda x: x[1].lower())
        hero_id = _select_item_from_list(
            self, "Assign Hero",
            f"Choose a hero for {slot_label} "
            f"(or \"(clear slot)\" to remove the current hero):",
            options,
        )
        if hero_id is None:
            return  # user cancelled

        ok = self.stw_api.assign_hero_to_loadout(
            slot_name=slot_key,
            loadout_id=self._active_loadout_id,
            hero_id=hero_id or "",
        )
        if ok:
            speak_later("Hero assigned." if hero_id else "Slot cleared.")
            self._populate()
        else:
            # Surface the Epic error verbatim so users know what happened.
            err = self.stw_api.last_error_code or ""
            msg = self.stw_api.last_error_message or ""
            if "overflow" in err:
                self.show_error(
                    "That hero is in inventory overflow. Recycle or transform "
                    "heroes in-game to clear overflow, then try again."
                )
            elif "invalid_parameter" in err and "not unlocked" in msg:
                self.show_error(
                    f"{slot_label} is not unlocked yet. Complete the relevant "
                    f"homebase quest first."
                )
            else:
                self.show_error(
                    f"Could not assign hero.\n\n{err}: {msg}"
                    if err else "Could not assign hero."
                )

    def _on_clear(self, _evt: wx.CommandEvent) -> None:
        if not self._active_loadout_id:
            return
        if not self.confirm(
            "Clear all heroes from this loadout?", "Confirm Clear"
        ):
            return
        ok = self.stw_api.clear_hero_loadout(self._active_loadout_id)
        if ok:
            speak_later("Loadout cleared.")
            self._populate()
        else:
            self.show_error("Could not clear loadout.")


# ---------------------------------------------------------------------------
# Survivor squads
# ---------------------------------------------------------------------------

class SurvivorSquadsDialog(StwSubDialog):
    """List the 8 survivor squads; assign survivors into slots by squad+slotIdx.

    Survivor slot layout per squad:
      slot 0 = leader (Worker:manager_*)
      slots 1..7 = followers (Worker:* other than managers)
    """

    def __init__(self, parent, stw_api):
        self._list: Optional[wx.ListCtrl] = None
        self._squad_summaries: List[Tuple[str, str, Dict]] = []  # (squadId, display, info)
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Survivor Squads",
            help_id="SaveTheWorldSurvivorSquads",
            default_size=(820, 560),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        intro = wx.StaticText(
            self,
            label=(
                "Select a squad to assign survivors. Leader slot (0) takes "
                "manager_* survivors; slots 1-7 take follower survivors."
            ),
        )
        sizer.Add(intro, 0, wx.ALL | wx.EXPAND, 5)

        self._list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._list.InsertColumn(0, "Squad", width=360)
        self._list.InsertColumn(1, "Filled", width=90)
        self._list.InsertColumn(2, "Leader", width=300)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        assign_btn = wx.Button(self, label="&Assign Survivor")
        assign_btn.Bind(wx.EVT_BUTTON, self._on_assign)
        sizer.Add(assign_btn, 0, wx.ALL, 5)
        unassign_all_btn = wx.Button(self, label="&Unassign All Squads")
        unassign_all_btn.Bind(wx.EVT_BUTTON, self._on_unassign_all)
        sizer.Add(unassign_all_btn, 0, wx.ALL, 5)

    # -- Data ---------------------------------------------------------
    def _populate(self) -> None:
        self.stw_api.query_profile()
        items = self.stw_api._items()
        # Build a map squadId -> {slotIdx: (survivor_id, item_dict)}. Note
        # that workers NOT assigned to a squad lack `squad_id` entirely,
        # and unassigned ones have `squad_slot_idx: -1`.
        squad_map: Dict[str, Dict[int, Tuple[str, Dict]]] = {
            sid: {} for sid in SURVIVOR_SQUAD_IDS
        }
        total_workers = 0
        assigned_workers = 0
        for item_id, item in items.items():
            tid = item.get("templateId") or ""
            if not tid.startswith("Worker:"):
                continue
            total_workers += 1
            attrs = item.get("attributes") or {}
            squad_id = attrs.get("squad_id") or ""
            slot_idx = attrs.get("squad_slot_idx")
            if not squad_id or slot_idx is None:
                continue
            if squad_id not in squad_map:
                continue
            try:
                idx_int = int(slot_idx)
            except (TypeError, ValueError):
                continue
            if idx_int < 0:
                continue
            squad_map[squad_id][idx_int] = (item_id, item)
            assigned_workers += 1
        logger.info(
            f"SurvivorSquadsDialog: {assigned_workers}/{total_workers} "
            f"survivors assigned across "
            f"{sum(1 for v in squad_map.values() if v)}/{len(squad_map)} squads"
        )

        self._squad_summaries = []
        self._list.DeleteAllItems()
        for idx, squad_id in enumerate(SURVIVOR_SQUAD_IDS):
            display = SURVIVOR_SQUAD_DISPLAY[squad_id]
            assignments = squad_map.get(squad_id, {})
            filled = len(assignments)
            leader_tuple = assignments.get(0)
            if leader_tuple is None:
                leader_display = "(unassigned)"
            else:
                _lid, leader_item = leader_tuple
                leader_display = format_template_display(
                    leader_item.get("templateId", ""),
                    level=str((leader_item.get("attributes") or {}).get("level", "") or ""),
                )
            self._squad_summaries.append((squad_id, display, assignments))
            self._list.InsertItem(idx, display)
            self._list.SetItem(idx, 1, f"{filled}/8")
            self._list.SetItem(idx, 2, leader_display)

    def _selected(self) -> Optional[Tuple[str, str, Dict]]:
        idx = self._list.GetFirstSelected()
        if idx < 0 or idx >= len(self._squad_summaries):
            return None
        return self._squad_summaries[idx]

    # -- Actions ------------------------------------------------------
    def _on_assign(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected()
        if not sel:
            self.show_info("Select a squad first.", caption="No Selection")
            return
        squad_id, display, _assignments = sel

        # Ask for slot index first.
        slot_dlg = wx.TextEntryDialog(
            self,
            "Slot (0 = leader, 1-7 = follower):",
            f"Assign into {display}",
            value="0",
        )
        try:
            if slot_dlg.ShowModal() != wx.ID_OK:
                return
            try:
                slot_idx = int(slot_dlg.GetValue())
            except ValueError:
                self.show_error("Slot must be a number 0-7.")
                return
        finally:
            slot_dlg.Destroy()
        if slot_idx < 0 or slot_idx > 7:
            self.show_error("Slot must be 0-7.")
            return

        # Ask for survivor.
        survivors = self.stw_api.get_survivors()
        # Filter: leader slot -> managers; followers -> non-managers.
        if slot_idx == 0:
            survivors = [(sid, itm) for sid, itm in survivors
                         if "manager" in (itm.get("templateId") or "").lower()]
        else:
            survivors = [(sid, itm) for sid, itm in survivors
                         if "manager" not in (itm.get("templateId") or "").lower()]

        options = []
        for sid, itm in survivors:
            tid = itm.get("templateId", "")
            level = str((itm.get("attributes") or {}).get("level", "") or "")
            options.append((sid, format_template_display(tid, level=level)))
        options.sort(key=lambda x: x[1].lower())

        survivor_id = _select_item_from_list(
            self,
            f"Assign to slot {slot_idx}",
            f"Choose survivor for {display} slot {slot_idx}:",
            options,
        )
        if not survivor_id:
            return
        ok = self.stw_api.assign_worker_to_squad(
            squad_id=squad_id, character_id=survivor_id, slot_idx=slot_idx
        )
        if ok:
            speak_later("Survivor assigned.")
            self._populate()
        else:
            self.show_error("Could not assign survivor.")

    def _on_unassign_all(self, _evt: wx.CommandEvent) -> None:
        if not self.confirm(
            "Unassign every survivor from every squad? This is destructive "
            "and you'll need to re-build squads manually.",
            "Confirm Unassign All",
        ):
            return
        ok = self.stw_api.unassign_all_squads()
        if ok:
            speak_later("All squads unassigned.")
            self._populate()
        else:
            self.show_error("Could not unassign squads.")


# ---------------------------------------------------------------------------
# Defender squads
# ---------------------------------------------------------------------------

class DefenderSquadsDialog(StwSubDialog):
    """Assign defenders into defender slots. STW has fixed defender slot IDs
    `squad_attribute_<type>_<slot>`; we expose them as a flat list."""

    DEFENDER_SQUAD_IDS = [
        "squad_attribute_medicine_defender",
        "squad_attribute_arms_defender",
        "squad_attribute_synthesis_defender",
        "squad_attribute_scavenging_defender",
    ]
    DEFENDER_DISPLAY = {
        "squad_attribute_medicine_defender": "Medicine Defender",
        "squad_attribute_arms_defender": "Arms Defender",
        "squad_attribute_synthesis_defender": "Synthesis Defender",
        "squad_attribute_scavenging_defender": "Scavenging Defender",
    }

    def __init__(self, parent, stw_api):
        self._list: Optional[wx.ListCtrl] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Defender Squads",
            help_id="SaveTheWorldDefenderSquads",
            default_size=(700, 400),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        intro = wx.StaticText(
            self,
            label="Assign defenders into defender slots by squad.",
        )
        sizer.Add(intro, 0, wx.ALL | wx.EXPAND, 5)

        self._list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._list.InsertColumn(0, "Squad", width=280)
        self._list.InsertColumn(1, "Current", width=320)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        assign_btn = wx.Button(self, label="&Assign Defender")
        assign_btn.Bind(wx.EVT_BUTTON, self._on_assign)
        sizer.Add(assign_btn, 0, wx.ALL, 5)

    def _populate(self) -> None:
        self.stw_api.query_profile()
        items = self.stw_api._items()
        assigned: Dict[str, str] = {}
        for item_id, item in items.items():
            tid = item.get("templateId") or ""
            if not tid.startswith("Defender:"):
                continue
            attrs = item.get("attributes") or {}
            squad_id = attrs.get("squad_id")
            if squad_id:
                assigned[squad_id] = tid.rsplit(":", 1)[-1]
        self._list.DeleteAllItems()
        for idx, squad_id in enumerate(self.DEFENDER_SQUAD_IDS):
            self._list.InsertItem(idx, self.DEFENDER_DISPLAY[squad_id])
            self._list.SetItem(idx, 1, assigned.get(squad_id, "(empty)"))

    def _on_assign(self, _evt: wx.CommandEvent) -> None:
        idx = self._list.GetFirstSelected()
        if idx < 0:
            self.show_info("Select a squad first.", caption="No Selection")
            return
        squad_id = self.DEFENDER_SQUAD_IDS[idx]
        defenders = self.stw_api.get_defenders()
        options = []
        for did, itm in defenders:
            tid = itm.get("templateId", "")
            level = str((itm.get("attributes") or {}).get("level", "") or "")
            options.append((did, format_template_display(tid, level=level)))
        options.sort(key=lambda x: x[1].lower())
        defender_id = _select_item_from_list(
            self,
            "Assign Defender",
            f"Choose defender for {self.DEFENDER_DISPLAY[squad_id]}:",
            options,
        )
        if not defender_id:
            return
        ok = self.stw_api.assign_worker_to_squad(
            squad_id=squad_id, character_id=defender_id, slot_idx=0
        )
        if ok:
            speak_later("Defender assigned.")
            self._populate()
        else:
            self.show_error("Could not assign defender.")
