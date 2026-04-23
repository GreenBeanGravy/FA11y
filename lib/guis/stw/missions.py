"""
Mission-related STW sub-dialogs: alerts, daily quests, expeditions.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import wx

from lib.guis.stw.base import StwSubDialog, confirm, speak_later
from lib.stw.world_info import MissionAlert, WorldInfoAPI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Mission Alerts
# ---------------------------------------------------------------------------

class MissionAlertsDialog(StwSubDialog):
    """Lists today's mission alerts for zones the player has unlocked.

    Flat list sorted by reward priority. Each row: zone, mission type, PL,
    reward summary, time until expires. The user picks from the list and
    either confirms it matches what they see in-game or uses the Claim
    button to claim all rewards at once.
    """

    def __init__(self, parent, stw_api):
        self._world_info: Optional[WorldInfoAPI] = None
        self._alerts: List[MissionAlert] = []
        self._list: Optional[wx.ListCtrl] = None
        self._filter_vbucks: Optional[wx.CheckBox] = None
        self._filter_legendary: Optional[wx.CheckBox] = None
        self._filter_evo: Optional[wx.CheckBox] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Mission Alerts",
            help_id="SaveTheWorldMissionAlerts",
            default_size=(820, 600),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        filter_box = wx.StaticBox(self, label="Filters")
        filter_sizer = wx.StaticBoxSizer(filter_box, wx.HORIZONTAL)
        self._filter_vbucks = wx.CheckBox(self, label="V-Bucks / X-Ray only")
        self._filter_legendary = wx.CheckBox(self, label="Legendary survivors")
        self._filter_evo = wx.CheckBox(self, label="Evo mats / PERK-UPs")
        for cb in (self._filter_vbucks, self._filter_legendary, self._filter_evo):
            cb.Bind(wx.EVT_CHECKBOX, lambda _evt: self._refresh_list())
            filter_sizer.Add(cb, 0, wx.ALL, 5)
        sizer.Add(filter_sizer, 0, wx.EXPAND | wx.ALL, 5)

        self._list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._list.InsertColumn(0, "Zone", width=120)
        self._list.InsertColumn(1, "Mission", width=200)
        self._list.InsertColumn(2, "Difficulty", width=130)
        self._list.InsertColumn(3, "Reward", width=300)
        self._list.InsertColumn(4, "Expires", width=90)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 5)

        self._status_text = wx.StaticText(self, label="")
        sizer.Add(self._status_text, 0, wx.ALL | wx.EXPAND, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        speak_btn = wx.Button(self, label="&Speak Summary")
        speak_btn.Bind(wx.EVT_BUTTON, self._on_speak_summary)
        sizer.Add(speak_btn, 0, wx.ALL, 5)

        claim_btn = wx.Button(self, label="&Claim All Alert Rewards")
        claim_btn.Bind(wx.EVT_BUTTON, self._on_claim_all)
        sizer.Add(claim_btn, 0, wx.ALL, 5)

    # -- Data ----------------------------------------------------------
    def _ensure_api(self) -> bool:
        if self._world_info is None:
            try:
                self._world_info = WorldInfoAPI(self.stw_api.auth)
            except Exception as e:
                logger.error(f"MissionAlertsDialog API init failed: {e}")
                return False
        return True

    def _populate(self) -> None:
        if not self._ensure_api():
            self._status_text.SetLabel("Could not initialise the world-info API.")
            return

        # Refresh player profile to get unlocked zones.
        self.stw_api.query_profile()
        unlocked = self.stw_api.get_unlocked_zones()
        if not self._world_info.fetch(force=True):
            self._status_text.SetLabel(
                "Could not fetch mission alerts from Epic. "
                "Try Refresh after checking connectivity."
            )
            return
        self._alerts = self._world_info.get_alerts_sorted_by_priority(
            unlocked_zones=unlocked
        )
        if not self._alerts:
            self._status_text.SetLabel(
                f"No mission alerts available in your unlocked zones "
                f"({', '.join(unlocked) or 'Stonewood'})."
            )
        else:
            self._status_text.SetLabel(
                f"{len(self._alerts)} alerts in "
                f"{', '.join(unlocked) or 'Stonewood'}."
            )
        self._refresh_list()

    def _refresh_list(self) -> None:
        if not self._list:
            return
        self._list.DeleteAllItems()
        only_vbucks = self._filter_vbucks and self._filter_vbucks.IsChecked()
        only_legendary = self._filter_legendary and self._filter_legendary.IsChecked()
        only_evo = self._filter_evo and self._filter_evo.IsChecked()

        row = 0
        for alert in self._alerts:
            if only_vbucks and not (alert.has_vbucks or alert.has_xray):
                continue
            if only_legendary and not alert.has_legendary_survivor:
                continue
            if only_evo and not (alert.has_evo_mat or alert.has_perkup):
                continue
            self._list.InsertItem(row, alert.theater_name or "")
            self._list.SetItem(row, 1, alert.mission_type or "")
            self._list.SetItem(row, 2, alert.difficulty_label or "-")
            self._list.SetItem(row, 3, alert.reward_summary or "")
            self._list.SetItem(row, 4, alert.expiry_display())
            row += 1

    # -- Actions -------------------------------------------------------
    def _on_speak_summary(self, _evt: wx.CommandEvent) -> None:
        if not self._alerts:
            speak_later("No alerts to summarise.")
            return
        vbucks = sum(1 for a in self._alerts if a.has_vbucks)
        xray = sum(1 for a in self._alerts if a.has_xray)
        legendary = sum(1 for a in self._alerts if a.has_legendary_survivor)
        evo = sum(1 for a in self._alerts if a.has_evo_mat)
        parts = [f"{len(self._alerts)} alerts today."]
        if vbucks:
            parts.append(f"{vbucks} V-Bucks.")
        if xray:
            parts.append(f"{xray} X-Ray Tickets.")
        if legendary:
            parts.append(f"{legendary} Legendary survivor.")
        if evo:
            parts.append(f"{evo} with Evolution Materials.")
        speak_later(" ".join(parts))

    def _on_claim_all(self, _evt: wx.CommandEvent) -> None:
        if not self.confirm(
            "Claim all pending mission alert rewards from today?",
            "Confirm Claim",
        ):
            return
        ok = self.stw_api.claim_mission_alert_rewards()
        if ok:
            speak_later("Mission alert rewards claimed.")
            self.show_info("Mission alert rewards claimed.")
        else:
            self.show_error("Could not claim mission alert rewards.")


# ---------------------------------------------------------------------------
# Daily Quests
# ---------------------------------------------------------------------------

class DailyQuestsDialog(StwSubDialog):
    """Shows today's daily quests; supports per-quest reroll + claim."""

    def __init__(self, parent, stw_api):
        self._list: Optional[wx.ListCtrl] = None
        self._quests: List[Tuple[str, dict]] = []
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Daily Quests",
            help_id="SaveTheWorldDailyQuests",
            default_size=(780, 520),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        instructions = wx.StaticText(
            self,
            label="Select a quest, then use Reroll or Claim. Rerolls are limited per day.",
        )
        sizer.Add(instructions, 0, wx.ALL | wx.EXPAND, 5)

        self._list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._list.InsertColumn(0, "Quest", width=280)
        self._list.InsertColumn(1, "Progress", width=120)
        self._list.InsertColumn(2, "State", width=120)
        self._list.InsertColumn(3, "Reward", width=200)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        reroll_btn = wx.Button(self, label="Re&roll Selected")
        reroll_btn.Bind(wx.EVT_BUTTON, self._on_reroll)
        sizer.Add(reroll_btn, 0, wx.ALL, 5)
        claim_btn = wx.Button(self, label="&Claim Selected")
        claim_btn.Bind(wx.EVT_BUTTON, self._on_claim)
        sizer.Add(claim_btn, 0, wx.ALL, 5)
        generate_btn = wx.Button(self, label="&Generate Dailies")
        generate_btn.Bind(wx.EVT_BUTTON, self._on_generate)
        sizer.Add(generate_btn, 0, wx.ALL, 5)

    # -- Data ----------------------------------------------------------
    def _populate(self) -> None:
        self.stw_api.query_profile()
        self._quests = self.stw_api.get_daily_quests()
        self._list.DeleteAllItems()
        if not self._quests:
            self._list.InsertItem(0, "No active daily quests.")
            self._list.SetItem(0, 2, "")
            return
        for idx, (quest_id, item) in enumerate(self._quests):
            template = item.get("templateId", "")
            name = _pretty_quest_name(template)
            attrs = item.get("attributes") or {}
            state = str(attrs.get("quest_state", "") or "")
            # Progress: find the "completion_" keys and pick the highest ratio.
            progress_parts = []
            for key, value in attrs.items():
                if key.startswith("completion_"):
                    try:
                        progress_parts.append(str(int(value)))
                    except (TypeError, ValueError):
                        pass
            progress = " / ".join(progress_parts) if progress_parts else "-"
            reward = _quest_reward_preview(item)
            self._list.InsertItem(idx, name)
            self._list.SetItem(idx, 1, progress)
            self._list.SetItem(idx, 2, state)
            self._list.SetItem(idx, 3, reward)

    def _selected_quest(self) -> Optional[Tuple[str, dict]]:
        idx = self._list.GetFirstSelected()
        if idx < 0 or idx >= len(self._quests):
            return None
        return self._quests[idx]

    # -- Actions -------------------------------------------------------
    def _on_reroll(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected_quest()
        if not sel:
            self.show_info("Select a quest first.", caption="No Selection")
            return
        quest_id, item = sel
        name = _pretty_quest_name(item.get("templateId", ""))
        if not self.confirm(
            f"Reroll \"{name}\"? Rerolls are limited per day.",
            "Confirm Reroll",
        ):
            return
        ok = self.stw_api.reroll_daily_quest(quest_id)
        if ok:
            speak_later("Quest rerolled.")
            self._populate()
        else:
            self.show_error("Could not reroll quest.")

    def _on_claim(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected_quest()
        if not sel:
            self.show_info("Select a quest first.", caption="No Selection")
            return
        quest_id, _item = sel
        ok = self.stw_api.claim_quest_reward(quest_id)
        if ok:
            speak_later("Quest reward claimed.")
            self._populate()
        else:
            self.show_error("Could not claim quest reward. "
                            "The quest may not be completed yet.")

    def _on_generate(self, _evt: wx.CommandEvent) -> None:
        ok = self.stw_api.generate_daily_quests()
        if ok:
            speak_later("Daily quests generated.")
            self._populate()
        else:
            self.show_error("Could not generate daily quests.")


def _pretty_quest_name(template_id: str) -> str:
    if not template_id:
        return "(unknown quest)"
    # Quest:DailyQuest_PiggyBank
    last = template_id.rsplit(":", 1)[-1]
    for prefix in ("DailyQuest_", "QuickDailyQuest_", "Quest_"):
        if last.startswith(prefix):
            last = last[len(prefix):]
    out = []
    for i, ch in enumerate(last):
        if i > 0 and ch.isupper() and (last[i - 1].islower() or (i + 1 < len(last) and last[i + 1].islower())):
            out.append(" ")
        out.append(ch)
    return "".join(out).replace("_", " ").strip()


def _quest_reward_preview(item: dict) -> str:
    """Extract a short reward preview from a quest item's attributes."""
    attrs = item.get("attributes") or {}
    # Epic sometimes embeds "questRewards" or "quest_rewards" with a list.
    rewards = attrs.get("questRewards") or attrs.get("quest_rewards") or []
    if isinstance(rewards, list) and rewards:
        names = []
        for reward in rewards[:2]:
            tid = reward.get("templateId", "")
            qty = reward.get("quantity", 1)
            last = tid.rsplit(":", 1)[-1] if ":" in tid else tid
            names.append(f"{qty}x {last}")
        return ", ".join(names)
    return "-"


# ---------------------------------------------------------------------------
# Expeditions
# ---------------------------------------------------------------------------

class ExpeditionsDialog(StwSubDialog):
    """Active + completed expeditions with refresh/collect actions."""

    def __init__(self, parent, stw_api):
        self._list: Optional[wx.ListCtrl] = None
        self._expeditions: List[Tuple[str, dict, str]] = []  # (id, item, bucket)
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Expeditions",
            help_id="SaveTheWorldExpeditions",
            default_size=(820, 540),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        instructions = wx.StaticText(
            self,
            label=(
                "Active expeditions are in progress; completed ones can be "
                "collected. Refresh regenerates the expedition offer list."
            ),
        )
        sizer.Add(instructions, 0, wx.ALL | wx.EXPAND, 5)

        self._list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._list.InsertColumn(0, "Expedition", width=320)
        self._list.InsertColumn(1, "State", width=120)
        self._list.InsertColumn(2, "Ends / ended", width=180)
        self._list.InsertColumn(3, "Reward hint", width=180)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        refresh_offers_btn = wx.Button(self, label="&New Offers")
        refresh_offers_btn.Bind(wx.EVT_BUTTON, self._on_refresh_offers)
        sizer.Add(refresh_offers_btn, 0, wx.ALL, 5)
        collect_btn = wx.Button(self, label="C&ollect Selected")
        collect_btn.Bind(wx.EVT_BUTTON, self._on_collect)
        sizer.Add(collect_btn, 0, wx.ALL, 5)
        collect_all_btn = wx.Button(self, label="Collect &All")
        collect_all_btn.Bind(wx.EVT_BUTTON, self._on_collect_all)
        sizer.Add(collect_all_btn, 0, wx.ALL, 5)
        abandon_btn = wx.Button(self, label="A&bandon Selected")
        abandon_btn.Bind(wx.EVT_BUTTON, self._on_abandon)
        sizer.Add(abandon_btn, 0, wx.ALL, 5)

    # -- Data ---------------------------------------------------------
    def _populate(self) -> None:
        self.stw_api.query_profile()
        groups = self.stw_api.get_expeditions()
        self._expeditions = []
        for item_id, item in groups["completed"]:
            self._expeditions.append((item_id, item, "Completed"))
        for item_id, item in groups["active"]:
            self._expeditions.append((item_id, item, "Active"))

        self._list.DeleteAllItems()
        if not self._expeditions:
            self._list.InsertItem(0, "No expeditions in flight.")
            return
        for idx, (item_id, item, bucket) in enumerate(self._expeditions):
            template = item.get("templateId", "")
            short = template.rsplit(":", 1)[-1]
            attrs = item.get("attributes") or {}
            end_time = attrs.get("expedition_end_time", "")
            self._list.InsertItem(idx, short)
            self._list.SetItem(idx, 1, bucket)
            self._list.SetItem(idx, 2, end_time or "-")
            # Rough reward hint from criteria
            hint = attrs.get("expedition_criteria") or attrs.get(
                "expedition_rewards"
            ) or "-"
            if isinstance(hint, (list, dict)):
                hint = "see rewards in-game"
            self._list.SetItem(idx, 3, str(hint))

    def _selected(self) -> Optional[Tuple[str, dict, str]]:
        idx = self._list.GetFirstSelected()
        if idx < 0 or idx >= len(self._expeditions):
            return None
        return self._expeditions[idx]

    # -- Actions ------------------------------------------------------
    def _on_refresh_offers(self, _evt: wx.CommandEvent) -> None:
        ok = self.stw_api.refresh_expeditions()
        if ok:
            speak_later("Expedition offers refreshed.")
            self._populate()
        else:
            self.show_error("Could not refresh expeditions.")

    def _on_collect(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected()
        if not sel:
            self.show_info("Select a completed expedition first.", caption="No Selection")
            return
        item_id, item, bucket = sel
        if bucket != "Completed":
            self.show_info(
                "Only completed expeditions can be collected.",
                caption="Not Completed",
            )
            return
        template = item.get("templateId", "")
        ok = self.stw_api.collect_expedition(item_id, template)
        if ok:
            speak_later("Expedition collected.")
            self._populate()
        else:
            self.show_error("Could not collect expedition.")

    def _on_collect_all(self, _evt: wx.CommandEvent) -> None:
        completed = [(eid, item) for (eid, item, bucket) in self._expeditions
                     if bucket == "Completed"]
        if not completed:
            self.show_info("No completed expeditions to collect.",
                           caption="Nothing to Collect")
            return
        if not self.confirm(
            f"Collect all {len(completed)} completed expeditions?",
            "Confirm Collect All",
        ):
            return
        failures = 0
        for item_id, item in completed:
            template = item.get("templateId", "")
            if not self.stw_api.collect_expedition(item_id, template):
                failures += 1
        if failures:
            self.show_error(f"{failures} of {len(completed)} failed.")
        else:
            speak_later(f"Collected {len(completed)} expeditions.")
        self._populate()

    def _on_abandon(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected()
        if not sel:
            self.show_info("Select an expedition first.", caption="No Selection")
            return
        item_id, _item, _bucket = sel
        if not self.confirm(
            "Abandon this expedition? Any assigned heroes will be returned "
            "unclaimed.",
            "Confirm Abandon",
        ):
            return
        ok = self.stw_api.abandon_expedition(item_id)
        if ok:
            speak_later("Expedition abandoned.")
            self._populate()
        else:
            self.show_error("Could not abandon expedition.")
