"""
Item management STW sub-dialogs.

Two dialog classes here:
  - ItemsDialog: unified browser for heroes / schematics / survivors /
    defenders. Shows level + rarity + favorited. Single-item actions
    (recycle / upgrade rarity / promote / reroll perks / craft).
  - RecycleBatchDialog: multi-select list with bulk recycle.
"""
from __future__ import annotations

import logging
from typing import Callable, Dict, List, Optional, Tuple

import wx

from lib.guis.stw.base import StwSubDialog, explain_api_error, speak_later
from lib.stw.api import (
    FORT_STAT_DISPLAY,
    FORT_STAT_ORDER,
    format_perk,
    format_template_display,
    parse_perk,
    parse_template_name,
)

logger = logging.getLogger(__name__)


# Mapping of "kind" string (used by ItemsDialog constructor) to the STWApi
# accessor and display label.
KIND_CONFIG: Dict[str, Dict[str, object]] = {
    "heroes": {
        "label": "Heroes",
        "accessor": lambda api: api.get_heroes(),
        "short": "Hero",
    },
    "schematics": {
        "label": "Schematics",
        "accessor": lambda api: api.get_schematics(),
        "short": "Schematic",
    },
    "survivors": {
        "label": "Survivors",
        "accessor": lambda api: api.get_survivors(),
        "short": "Survivor",
    },
    "defenders": {
        "label": "Defenders",
        "accessor": lambda api: api.get_defenders(),
        "short": "Defender",
    },
}


def _rarity_from_template(template_id: str) -> str:
    """Extract rarity via the parser — consistent with the friendly-name
    display so filters and displayed rarity always match."""
    return parse_template_name(template_id).get("rarity") or "?"


def _tier_from_template(template_id: str) -> str:
    tier = parse_template_name(template_id).get("tier") or ""
    return f"T{tier}" if tier else ""


def _perk_summary(item: dict) -> str:
    """Short perk summary for list-column display (first 3 perks)."""
    attrs = item.get("attributes") or {}
    alterations = attrs.get("alterations") or []
    if not alterations:
        return ""
    names = []
    for alt in alterations[:3]:
        names.append(format_perk(alt))
    suffix = f" +{len(alterations) - 3} more" if len(alterations) > 3 else ""
    return ", ".join(names) + suffix


def _full_stats_text(item: dict) -> str:
    """Full details panel for a selected item: rarity, tier, level, material,
    all 6 perk slots. Used by ItemsDialog's Stats panel."""
    template = item.get("templateId", "")
    parsed = parse_template_name(template)
    attrs = item.get("attributes") or {}

    lines = [
        f"Name: {parsed['name']}",
        f"Rarity: {parsed['rarity'] or '?'}",
        f"Tier: T{parsed['tier']}" if parsed["tier"] else "Tier: ?",
        f"Level: {attrs.get('level', '?')}",
        f"Template: {template}",
    ]

    if attrs.get("starting_rarity"):
        lines.append(f"Starting rarity: {attrs.get('starting_rarity')}")
    if attrs.get("starting_tier"):
        lines.append(f"Starting tier: {attrs.get('starting_tier')}")

    # Perks / alterations.
    alterations = attrs.get("alterations") or []
    if alterations:
        lines.append("")
        lines.append("Perks:")
        for idx, alt in enumerate(alterations, 1):
            parsed_perk = parse_perk(alt)
            tier_str = f" (T{parsed_perk['tier']})" if parsed_perk["tier"] else ""
            lines.append(f"  {idx}. {parsed_perk['desc']}{tier_str}")

    # Hero-specific: hero_name, building_slot_used
    if template.startswith("Hero:"):
        if attrs.get("hero_name") and attrs.get("hero_name") != "DefaultHeroName":
            lines.append(f"\nCustom name: {attrs.get('hero_name')}")

    # Survivor-specific: personality, portrait, set_bonus
    if template.startswith("Worker:"):
        if attrs.get("personality"):
            lines.append(f"\nPersonality: {attrs.get('personality').split('.')[-1]}")
        if attrs.get("set_bonus"):
            lines.append(f"Set bonus: {attrs.get('set_bonus').split('.')[-1]}")

    # Inventory overflow warning (for heroes).
    ov = attrs.get("inventory_overflow_date")
    if ov:
        lines.append(
            f"\n⚠ In overflow until {ov} — can't be equipped. "
            f"Recycle or transform in-game to clear."
        )

    lines.append(
        "\n(Damage/fire-rate numbers aren't exposed by Epic's profile API. "
        "Check the in-game menu for those.)"
    )
    return "\n".join(lines)


def _favorited(item: dict) -> bool:
    attrs = item.get("attributes") or {}
    return bool(attrs.get("favorite") or attrs.get("favourited"))


# ---------------------------------------------------------------------------
# Items browser
# ---------------------------------------------------------------------------

class ItemsDialog(StwSubDialog):
    """Unified items browser. Shows level, rarity, favourite flag. Actions
    differ by kind (recycle always available; upgrade rarity + promote apply
    to heroes/schematics/survivors; craft applies to schematics)."""

    def __init__(self, parent, stw_api, kind: str):
        if kind not in KIND_CONFIG:
            raise ValueError(f"Unknown items kind: {kind}")
        self._kind = kind
        config = KIND_CONFIG[kind]
        self._items_list: Optional[wx.ListCtrl] = None
        self._items_data: List[Tuple[str, dict]] = []
        self._filter_text: Optional[wx.TextCtrl] = None
        self._rarity_choice: Optional[wx.Choice] = None
        super().__init__(
            parent,
            stw_api,
            title=f"Save the World — {config['label']}",
            help_id=f"SaveTheWorld{config['label']}",
            default_size=(900, 600),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        filter_row = wx.BoxSizer(wx.HORIZONTAL)
        filter_row.Add(wx.StaticText(self, label="Name contains:"),
                       0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._filter_text = wx.TextCtrl(self)
        self._filter_text.Bind(wx.EVT_TEXT, lambda _evt: self._refresh_list())
        filter_row.Add(self._filter_text, 1, wx.RIGHT, 10)

        filter_row.Add(wx.StaticText(self, label="Rarity:"),
                       0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._rarity_choice = wx.Choice(
            self, choices=["All", "Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic"]
        )
        self._rarity_choice.SetSelection(0)
        self._rarity_choice.Bind(wx.EVT_CHOICE, lambda _evt: self._refresh_list())
        filter_row.Add(self._rarity_choice, 0)
        sizer.Add(filter_row, 0, wx.ALL | wx.EXPAND, 5)

        self._items_list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._items_list.InsertColumn(0, "Name", width=280)
        self._items_list.InsertColumn(1, "Rarity", width=90)
        self._items_list.InsertColumn(2, "Tier", width=50)
        self._items_list.InsertColumn(3, "Level", width=60)
        self._items_list.InsertColumn(4, "Perks", width=260)
        self._items_list.InsertColumn(5, "Favourite", width=70)
        self._items_list.InsertColumn(6, "Item ID", width=280)
        self._items_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_item_selected)
        sizer.Add(self._items_list, 1, wx.EXPAND | wx.ALL, 5)

        # Full-details panel for the selected item.
        details_label = wx.StaticText(self, label="Details (selected item):")
        sizer.Add(details_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
        self._details_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
            size=(-1, 180),
        )
        sizer.Add(self._details_text, 0, wx.EXPAND | wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        recycle_btn = wx.Button(self, label="&Recycle")
        recycle_btn.Bind(wx.EVT_BUTTON, self._on_recycle)
        sizer.Add(recycle_btn, 0, wx.ALL, 5)

        if self._kind in ("heroes", "schematics", "survivors"):
            upgrade_btn = wx.Button(self, label="&Upgrade Rarity")
            upgrade_btn.Bind(wx.EVT_BUTTON, self._on_upgrade)
            sizer.Add(upgrade_btn, 0, wx.ALL, 5)
            promote_btn = wx.Button(self, label="&Promote")
            promote_btn.Bind(wx.EVT_BUTTON, self._on_promote)
            sizer.Add(promote_btn, 0, wx.ALL, 5)

        if self._kind == "schematics":
            reroll_btn = wx.Button(self, label="Re&spec Perks")
            reroll_btn.Bind(wx.EVT_BUTTON, self._on_respec)
            sizer.Add(reroll_btn, 0, wx.ALL, 5)
            craft_btn = wx.Button(self, label="C&raft")
            craft_btn.Bind(wx.EVT_BUTTON, self._on_craft)
            sizer.Add(craft_btn, 0, wx.ALL, 5)

    # -- Data ---------------------------------------------------------
    def _populate(self) -> None:
        self.stw_api.query_profile()
        accessor = KIND_CONFIG[self._kind]["accessor"]
        self._items_data = accessor(self.stw_api)
        self._refresh_list()

    def _refresh_list(self) -> None:
        if not self._items_list:
            return
        self._items_list.DeleteAllItems()
        filter_str = (self._filter_text.GetValue() if self._filter_text else "").lower()
        rarity_filter = (
            self._rarity_choice.GetStringSelection() if self._rarity_choice else "All"
        )

        row = 0
        for item_id, item in sorted(
            self._items_data,
            key=lambda t: (t[1].get("templateId") or "").lower(),
        ):
            template = item.get("templateId", "")
            parsed = parse_template_name(template)
            name = parsed["name"] or template
            rarity = parsed["rarity"] or "?"
            if rarity_filter != "All" and rarity != rarity_filter:
                continue
            if filter_str and filter_str not in (
                template.lower() + " " + name.lower()
            ):
                continue
            tier = f"T{parsed['tier']}" if parsed["tier"] else ""
            level = str((item.get("attributes") or {}).get("level", "") or "")
            fav = "Yes" if _favorited(item) else ""
            perks = _perk_summary(item)
            self._items_list.InsertItem(row, name)
            self._items_list.SetItem(row, 1, rarity)
            self._items_list.SetItem(row, 2, tier)
            self._items_list.SetItem(row, 3, level)
            self._items_list.SetItem(row, 4, perks)
            self._items_list.SetItem(row, 5, fav)
            self._items_list.SetItem(row, 6, item_id)
            row += 1
        logger.info(
            f"ItemsDialog[{self._kind}]: rendered {row} row(s) "
            f"(filter={filter_str!r}, rarity={rarity_filter})"
        )

    def _selected(self) -> Optional[Tuple[str, dict]]:
        idx = self._items_list.GetFirstSelected()
        if idx < 0:
            return None
        # Item ID in column 6.
        item_id = self._items_list.GetItem(idx, 6).GetText()
        for iid, itm in self._items_data:
            if iid == item_id:
                return iid, itm
        return None

    def _on_item_selected(self, _evt) -> None:
        sel = self._selected()
        if not sel or not self._details_text:
            return
        _iid, item = sel
        self._details_text.SetValue(_full_stats_text(item))

    # -- Actions ------------------------------------------------------
    def _on_recycle(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected()
        if not sel:
            self.show_info("Select an item first.", caption="No Selection")
            return
        item_id, item = sel
        template = item.get("templateId", "")
        if _favorited(item):
            if not self.confirm(
                "This item is marked as a favourite. Recycle anyway?",
                "Confirm Recycle Favourite",
            ):
                return
        else:
            if not self.confirm(
                f"Recycle {template.rsplit(':', 1)[-1]}? This is permanent.",
                "Confirm Recycle",
            ):
                return
        ok = self.stw_api.recycle_item(item_id)
        if ok:
            speak_later("Item recycled.")
            self._populate()
        else:
            self.show_error(explain_api_error(
                self.stw_api.last_error_code,
                self.stw_api.last_error_message,
                default="Could not recycle item.",
            ))

    def _on_upgrade(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected()
        if not sel:
            self.show_info("Select an item first.", caption="No Selection")
            return
        item_id, item = sel
        if not self.confirm(
            "Upgrade rarity? This consumes evolution materials and Flux.",
            "Confirm Upgrade Rarity",
        ):
            return
        ok = self.stw_api.upgrade_item_rarity(item_id)
        if ok:
            speak_later("Item rarity upgraded.")
            self._populate()
        else:
            self.show_error(explain_api_error(
                self.stw_api.last_error_code,
                self.stw_api.last_error_message,
                default="Could not upgrade item rarity. You may be missing "
                        "materials or at max rarity.",
            ))

    def _on_promote(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected()
        if not sel:
            self.show_info("Select an item first.", caption="No Selection")
            return
        item_id, _item = sel
        if not self.confirm(
            "Promote this item to the next level cap? Consumes training "
            "materials / flux.",
            "Confirm Promote",
        ):
            return
        ok = self.stw_api.promote_item(item_id)
        if ok:
            speak_later("Item promoted.")
            self._populate()
        else:
            self.show_error(explain_api_error(
                self.stw_api.last_error_code,
                self.stw_api.last_error_message,
                default="Could not promote item. You may be missing materials "
                        "or not at the level cap.",
            ))

    def _on_respec(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected()
        if not sel:
            self.show_info("Select a schematic first.", caption="No Selection")
            return
        item_id, _item = sel
        if not self.confirm(
            "Respec all perks on this schematic? Returns spent PERK-UP.",
            "Confirm Respec",
        ):
            return
        ok = self.stw_api.respec_alteration(item_id)
        if ok:
            speak_later("Perks reset.")
            self._populate()
        else:
            self.show_error(explain_api_error(
                self.stw_api.last_error_code,
                self.stw_api.last_error_message,
                default="Could not respec perks.",
            ))

    def _on_craft(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected()
        if not sel:
            self.show_info("Select a schematic first.", caption="No Selection")
            return
        item_id, _item = sel
        count_dlg = wx.TextEntryDialog(
            self, "Craft count:", "Craft", value="1"
        )
        try:
            if count_dlg.ShowModal() != wx.ID_OK:
                return
            try:
                count = int(count_dlg.GetValue())
            except ValueError:
                self.show_error("Count must be a number.")
                return
        finally:
            count_dlg.Destroy()
        if count < 1:
            return
        ok = self.stw_api.craft_world_item(
            target_schematic_item_id=item_id, target_count=count
        )
        if ok:
            speak_later(f"Crafted {count}.")
        else:
            self.show_error(explain_api_error(
                self.stw_api.last_error_code,
                self.stw_api.last_error_message,
                default="Could not craft. Check materials.",
            ))


# ---------------------------------------------------------------------------
# Batch recycle
# ---------------------------------------------------------------------------

class RecycleBatchDialog(StwSubDialog):
    """Multi-select list across heroes/schematics/survivors/defenders with
    bulk recycle. Safety: favourited items are opt-in."""

    def __init__(self, parent, stw_api):
        self._list: Optional[wx.ListCtrl] = None
        self._kind_choice: Optional[wx.Choice] = None
        self._rarity_choice: Optional[wx.Choice] = None
        self._include_favs: Optional[wx.CheckBox] = None
        self._items_data: List[Tuple[str, dict]] = []
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Recycle Items (batch)",
            help_id="SaveTheWorldRecycleBatch",
            default_size=(900, 640),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        top_row = wx.BoxSizer(wx.HORIZONTAL)
        top_row.Add(wx.StaticText(self, label="Kind:"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._kind_choice = wx.Choice(
            self, choices=["Heroes", "Schematics", "Survivors", "Defenders"]
        )
        self._kind_choice.SetSelection(0)
        self._kind_choice.Bind(wx.EVT_CHOICE, lambda _evt: self._populate())
        top_row.Add(self._kind_choice, 0, wx.RIGHT, 10)

        top_row.Add(wx.StaticText(self, label="Rarity:"),
                    0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._rarity_choice = wx.Choice(
            self,
            choices=["All", "Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic"],
        )
        self._rarity_choice.SetSelection(0)
        self._rarity_choice.Bind(wx.EVT_CHOICE, lambda _evt: self._populate())
        top_row.Add(self._rarity_choice, 0, wx.RIGHT, 10)

        self._include_favs = wx.CheckBox(self, label="Include favourites")
        top_row.Add(self._include_favs, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(top_row, 0, wx.ALL | wx.EXPAND, 5)

        self._list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_HRULES,
        )
        self._list.InsertColumn(0, "Name", width=280)
        self._list.InsertColumn(1, "Rarity", width=90)
        self._list.InsertColumn(2, "Tier", width=50)
        self._list.InsertColumn(3, "Level", width=60)
        self._list.InsertColumn(4, "Favourite", width=70)
        self._list.InsertColumn(5, "Item ID", width=300)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 5)

        intro = wx.StaticText(
            self,
            label=(
                "Select items (hold Shift/Ctrl for multi-select), then press "
                "Recycle Selected. Up to 200 items per batch."
            ),
        )
        sizer.Add(intro, 0, wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        recycle_btn = wx.Button(self, label="Re&cycle Selected")
        recycle_btn.Bind(wx.EVT_BUTTON, self._on_recycle_batch)
        sizer.Add(recycle_btn, 0, wx.ALL, 5)

    # -- Data ---------------------------------------------------------
    def _populate(self) -> None:
        self.stw_api.query_profile()
        kind = self._kind_choice.GetStringSelection() if self._kind_choice else "Heroes"
        accessor: Callable = {
            "Heroes": self.stw_api.get_heroes,
            "Schematics": self.stw_api.get_schematics,
            "Survivors": self.stw_api.get_survivors,
            "Defenders": self.stw_api.get_defenders,
        }.get(kind, self.stw_api.get_heroes)
        self._items_data = accessor()

        rarity_filter = (
            self._rarity_choice.GetStringSelection() if self._rarity_choice else "All"
        )

        self._list.DeleteAllItems()
        row = 0
        for item_id, item in sorted(
            self._items_data,
            key=lambda t: (t[1].get("templateId") or "").lower(),
        ):
            template = item.get("templateId", "")
            parsed = parse_template_name(template)
            name = parsed["name"] or template
            rarity = parsed["rarity"] or "?"
            if rarity_filter != "All" and rarity != rarity_filter:
                continue
            tier = f"T{parsed['tier']}" if parsed["tier"] else ""
            level = str((item.get("attributes") or {}).get("level", "") or "")
            fav = "Yes" if _favorited(item) else ""
            self._list.InsertItem(row, name)
            self._list.SetItem(row, 1, rarity)
            self._list.SetItem(row, 2, tier)
            self._list.SetItem(row, 3, level)
            self._list.SetItem(row, 4, fav)
            self._list.SetItem(row, 5, item_id)
            row += 1

    def _selected_ids(self) -> List[str]:
        out: List[str] = []
        include_favs = self._include_favs.IsChecked() if self._include_favs else False
        row = self._list.GetFirstSelected()
        while row != -1:
            # Item ID now at column 5, favourite flag at column 4.
            item_id = self._list.GetItem(row, 5).GetText()
            fav = self._list.GetItem(row, 4).GetText() == "Yes"
            if fav and not include_favs:
                row = self._list.GetNextSelected(row)
                continue
            out.append(item_id)
            row = self._list.GetNextSelected(row)
        return out

    # -- Actions ------------------------------------------------------
    def _on_recycle_batch(self, _evt: wx.CommandEvent) -> None:
        ids = self._selected_ids()
        if not ids:
            self.show_info(
                "Select items first. Favourites are skipped unless the "
                "\"Include favourites\" box is ticked.",
                caption="No Selection",
            )
            return
        if len(ids) > 200:
            self.show_error("Please recycle no more than 200 items per batch.")
            return
        if not self.confirm(
            f"Recycle {len(ids)} items? This is permanent.",
            "Confirm Batch Recycle",
        ):
            return
        ok = self.stw_api.recycle_item_batch(ids)
        if ok:
            speak_later(f"Recycled {len(ids)} items.")
            self._populate()
        else:
            self.show_error(explain_api_error(
                self.stw_api.last_error_code,
                self.stw_api.last_error_message,
                default="Batch recycle failed.",
            ))
