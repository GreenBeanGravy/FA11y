"""
Shop-related STW sub-dialogs: llama store offers, opening owned llamas.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

import wx

from lib.guis.stw.base import StwSubDialog, speak_later
from lib.stw.api import (
    CatalogAPI,
    format_price,
    format_template_display,
    parse_template_name,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Llama store — lists prerolled offers on the campaign profile
# ---------------------------------------------------------------------------

class LlamaStoreDialog(StwSubDialog):
    """View and purchase llamas from the campaign profile's prerolled offers.

    Epic's live schema stores llama offers as `PrerollData:*` items with:
      attributes.offerId       — the catalog offer ID passed to PurchaseCatalogEntry
      attributes.items[]       — preview of the llama's contents (schematic/hero/survivor templates)
      attributes.expiration    — ISO timestamp
    Currency and price aren't on the PrerollData blob — they come from the
    /storefront/v2/catalog endpoint. Since the in-game client already shows
    those in the shop UI, we focus here on what the llama WILL contain.
    """

    def __init__(self, parent, stw_api):
        self._list: Optional[wx.ListCtrl] = None
        self._preview_text: Optional[wx.TextCtrl] = None
        self._offers: List[Tuple[str, dict]] = []
        self._catalog: Optional[CatalogAPI] = None
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Llama Store",
            help_id="SaveTheWorldLlamaStore",
            default_size=(960, 640),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        instructions = wx.StaticText(
            self,
            label=(
                "Select a llama — the Preview panel shows what it will contain. "
                "Use Refresh Offers to pull a new slate from Epic."
            ),
        )
        sizer.Add(instructions, 0, wx.ALL | wx.EXPAND, 5)

        self._list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._list.InsertColumn(0, "Llama", width=170)
        self._list.InsertColumn(1, "Price", width=170)
        self._list.InsertColumn(2, "Items", width=60)
        self._list.InsertColumn(3, "Highest Rarity", width=110)
        self._list.InsertColumn(4, "Expires", width=110)
        self._list.InsertColumn(5, "Offer ID", width=280)
        self._list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_select)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 5)

        preview_label = wx.StaticText(self, label="Preview:")
        sizer.Add(preview_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 5)
        self._preview_text = wx.TextCtrl(
            self,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
            size=(-1, 150),
        )
        sizer.Add(self._preview_text, 0, wx.EXPAND | wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        refresh_btn = wx.Button(self, label="Re&fresh Offers")
        refresh_btn.Bind(wx.EVT_BUTTON, self._on_refresh_offers)
        sizer.Add(refresh_btn, 0, wx.ALL, 5)
        buy_btn = wx.Button(self, label="&Purchase Selected")
        buy_btn.Bind(wx.EVT_BUTTON, self._on_purchase)
        sizer.Add(buy_btn, 0, wx.ALL, 5)

    def _ensure_catalog(self) -> None:
        if self._catalog is None:
            self._catalog = CatalogAPI(self.stw_api.auth)
        self._catalog.fetch()

    # -- Data ---------------------------------------------------------
    def _populate(self) -> None:
        self.stw_api.query_profile()
        self._offers = self.stw_api.get_prerolled_offers()
        self._ensure_catalog()
        logger.info(f"LlamaStoreDialog: {len(self._offers)} prerolled offer(s)")

        self._list.DeleteAllItems()
        if not self._offers:
            self._list.InsertItem(
                0,
                "No llama offers found. Use Refresh Offers to generate them.",
            )
            self._preview_text.SetValue("")
            return

        for idx, (item_id, item) in enumerate(self._offers):
            attrs = item.get("attributes") or {}
            contents = attrs.get("items") or []
            offer_id = attrs.get("offerId") or attrs.get("offer_id") or item_id
            expiration = attrs.get("expiration", "") or "-"
            if expiration and expiration.endswith("Z"):
                expiration = expiration[5:16].replace("T", " ") + " UTC"
            highest_rarity = _highest_rarity_in_contents(contents)
            label = (
                item.get("templateId", "")
                .rsplit(":", 1)[-1]
                .replace("preroll_", "")
                .replace("_", " ")
                .title()
                or "Llama"
            )
            pricing = self._catalog.get_offer_pricing(str(offer_id)) if self._catalog else None
            price_text = format_price(pricing) if pricing else "(not in catalog)"
            self._list.InsertItem(idx, label)
            self._list.SetItem(idx, 1, price_text)
            self._list.SetItem(idx, 2, str(len(contents)))
            self._list.SetItem(idx, 3, highest_rarity or "-")
            self._list.SetItem(idx, 4, expiration)
            self._list.SetItem(idx, 5, str(offer_id))

        if self._offers:
            self._list.Select(0)
            self._render_preview(self._offers[0][1])

    def _render_preview(self, item: dict) -> None:
        attrs = item.get("attributes") or {}
        contents = attrs.get("items") or []
        if not contents:
            self._preview_text.SetValue("(llama contents not available)")
            return
        lines = []
        for entry in contents:
            template_id = entry.get("itemType", "")
            qty = entry.get("quantity", 1)
            parsed = parse_template_name(template_id)
            line = f"  - {qty}x {parsed['name']}"
            if parsed["rarity"] or parsed["tier"]:
                bits = []
                if parsed["rarity"]:
                    bits.append(parsed["rarity"])
                if parsed["tier"]:
                    bits.append(f"T{parsed['tier']}")
                line += f" ({' '.join(bits)})"
            alt_list = (entry.get("attributes") or {}).get("alterations") or []
            if alt_list:
                # Summarise perks compactly.
                perks = ", ".join(
                    parse_template_name(a)["name"] for a in alt_list[:3]
                )
                if len(alt_list) > 3:
                    perks += f" +{len(alt_list) - 3} more"
                line += f"   perks: {perks}"
            lines.append(line)
        self._preview_text.SetValue("\n".join(lines))

    def _selected(self) -> Optional[Tuple[str, dict]]:
        idx = self._list.GetFirstSelected()
        if idx < 0 or idx >= len(self._offers):
            return None
        return self._offers[idx]

    # -- Events -------------------------------------------------------
    def _on_select(self, _evt) -> None:
        sel = self._selected()
        if sel:
            self._render_preview(sel[1])

    def _on_refresh_offers(self, _evt: wx.CommandEvent) -> None:
        ok = self.stw_api.populate_prerolled_offers()
        if ok:
            speak_later("Llama offers refreshed.")
            self._populate()
        else:
            self.show_error("Could not refresh llama offers.")

    def _on_purchase(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected()
        if not sel:
            self.show_info("Select a llama offer first.", caption="No Selection")
            return
        _item_id, item = sel
        attrs = item.get("attributes") or {}
        offer_id = str(attrs.get("offerId") or attrs.get("offer_id") or "")
        if not offer_id:
            self.show_error("This offer has no offer ID — purchase unsupported.")
            return

        self._ensure_catalog()
        pricing = self._catalog.get_offer_pricing(offer_id) if self._catalog else None
        if not pricing:
            self.show_error(
                "Pricing for this offer isn't in Epic's storefront catalog "
                "right now. Try Refresh or use the in-game shop."
            )
            return

        price_display = format_price(pricing)
        if not self.confirm(
            f"Purchase this llama for {price_display}?",
            "Confirm Purchase",
        ):
            return

        logger.info(
            f"LlamaStoreDialog: purchasing offer={offer_id} "
            f"currency={pricing['currency']} sub={pricing['currency_sub_type']} "
            f"price={pricing['final_price']}"
        )
        result = self.stw_api.purchase_catalog_entry(
            offer_id=offer_id,
            purchase_quantity=1,
            currency=pricing["currency"],
            currency_sub_type=pricing["currency_sub_type"],
            expected_total_price=pricing["final_price"],
        )
        if result is not None:
            # Extract and speak the loot granted.
            loot_items = _extract_purchase_loot(result)
            if loot_items:
                summary = ", ".join(
                    f"{q}x {parse_template_name(t)['name']}"
                    for t, q in loot_items[:5]
                )
                speak_later(f"Llama purchased. Contains: {summary}.")
                self.show_info(
                    f"Llama purchased! Contains:\n\n"
                    + "\n".join(
                        f"  - {q}x {parse_template_name(t)['name']} "
                        f"({parse_template_name(t).get('rarity','?')} "
                        f"T{parse_template_name(t).get('tier','?')})"
                        for t, q in loot_items
                    )
                )
            else:
                speak_later("Llama purchased.")
                self.show_info("Llama purchased.")
            self._populate()
        else:
            # More specific error messages based on the common codes.
            err = self.stw_api.last_error_code or ""
            msg = self.stw_api.last_error_message or ""
            if "purchase_not_allowed" in err:
                self.show_error(
                    f"Purchase not allowed. "
                    f"This is usually a daily/event purchase limit you've "
                    f"already hit.\n\nEpic: {msg}"
                )
            elif "catalog_out_of_date" in err:
                self.show_error(
                    f"Prices changed since this offer loaded. Click Refresh "
                    f"Offers and try again.\n\nEpic: {msg}"
                )
            elif "not_enough" in err or "insufficient" in err:
                self.show_error(
                    f"Not enough currency to purchase this llama.\n\nEpic: {msg}"
                )
            else:
                self.show_error(
                    f"Could not purchase llama.\n\n{err}: {msg}"
                    if err else "Could not purchase llama."
                )


def _highest_rarity_in_contents(contents: list) -> str:
    """Return the highest rarity present across the content item types."""
    ranks = {
        "Common": 1, "Uncommon": 2, "Rare": 3,
        "Epic": 4, "Legendary": 5, "Mythic": 6,
    }
    best_rank = 0
    best_name = ""
    for entry in contents:
        tid = entry.get("itemType", "")
        parsed = parse_template_name(tid)
        rarity = parsed.get("rarity", "")
        rank = ranks.get(rarity, 0)
        if rank > best_rank:
            best_rank = rank
            best_name = rarity
    return best_name


# ---------------------------------------------------------------------------
# Open owned llamas — list unopened card packs and open them
# ---------------------------------------------------------------------------

class OpenLlamasDialog(StwSubDialog):
    """List owned unopened llamas / card packs and open them individually or
    in bulk. Rewards show up via Epic's `notifications[].lootGranted.items[]`
    which we summarise into a human-readable message.
    """

    def __init__(self, parent, stw_api):
        self._list: Optional[wx.ListCtrl] = None
        self._card_packs: List[Tuple[str, dict]] = []
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Open Llamas",
            help_id="SaveTheWorldOpenLlamas",
            default_size=(780, 520),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        instructions = wx.StaticText(
            self,
            label=(
                "Unopened llamas on your account. Select one and press Open, "
                "or use Open All to crack them all in sequence."
            ),
        )
        sizer.Add(instructions, 0, wx.ALL | wx.EXPAND, 5)

        self._list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._list.InsertColumn(0, "Card Pack", width=320)
        self._list.InsertColumn(1, "Quantity", width=100)
        self._list.InsertColumn(2, "Item ID", width=320)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 5)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        open_btn = wx.Button(self, label="&Open Selected")
        open_btn.Bind(wx.EVT_BUTTON, self._on_open)
        sizer.Add(open_btn, 0, wx.ALL, 5)
        open_all_btn = wx.Button(self, label="Open &All")
        open_all_btn.Bind(wx.EVT_BUTTON, self._on_open_all)
        sizer.Add(open_all_btn, 0, wx.ALL, 5)

    # -- Data ---------------------------------------------------------
    def _populate(self) -> None:
        self.stw_api.query_profile()
        self._card_packs = self.stw_api.get_card_packs()
        logger.info(f"OpenLlamasDialog: {len(self._card_packs)} unopened pack(s)")

        self._list.DeleteAllItems()
        if not self._card_packs:
            self._list.InsertItem(0, "No unopened llamas.")
            return
        for idx, (item_id, item) in enumerate(self._card_packs):
            template = item.get("templateId", "")
            name = parse_template_name(template)["name"] or template
            quantity = item.get("quantity", 1)
            self._list.InsertItem(idx, name)
            self._list.SetItem(idx, 1, str(quantity))
            self._list.SetItem(idx, 2, item_id)

    def _selected(self) -> Optional[Tuple[str, dict]]:
        idx = self._list.GetFirstSelected()
        if idx < 0 or idx >= len(self._card_packs):
            return None
        return self._card_packs[idx]

    # -- Actions ------------------------------------------------------
    def _on_open(self, _evt: wx.CommandEvent) -> None:
        sel = self._selected()
        if not sel:
            self.show_info("Select a llama first.", caption="No Selection")
            return
        item_id, _item = sel
        result = self.stw_api.open_card_pack(item_id)
        if result is not None:
            self._speak_loot(result)
            self._populate()
        else:
            self.show_error("Could not open llama.")

    def _on_open_all(self, _evt: wx.CommandEvent) -> None:
        if not self._card_packs:
            return
        if not self.confirm(
            f"Open all {len(self._card_packs)} unopened llamas?",
            "Confirm Open All",
        ):
            return
        speak_later(f"Opening {len(self._card_packs)} llamas.")
        failures = 0
        combined_loot_counts: dict = {}
        for item_id, _item in list(self._card_packs):
            result = self.stw_api.open_card_pack(item_id)
            if result is None:
                failures += 1
                continue
            self._accumulate_loot(result, combined_loot_counts)
        if combined_loot_counts:
            summary = ", ".join(
                f"{qty}x {name}" for name, qty in sorted(combined_loot_counts.items())
            )
            speak_later(f"Llamas opened. Total: {summary[:200]}")
        if failures:
            self.show_error(f"{failures} llamas failed to open.")
        self._populate()

    def _speak_loot(self, result: dict) -> None:
        loot = _extract_loot_items(result)
        if not loot:
            speak_later("Llama opened.")
            return
        summary = ", ".join(
            f"{qty}x {_short_template(tid)}" for tid, qty in loot[:5]
        )
        speak_later(f"Llama opened. Contained {summary}.")

    def _accumulate_loot(self, result: dict, counts: dict) -> None:
        for tid, qty in _extract_loot_items(result):
            name = _short_template(tid)
            counts[name] = counts.get(name, 0) + qty


def _extract_loot_items(mcp_result: dict) -> List[Tuple[str, int]]:
    """Extract loot from an OpenCardPack response (uses `lootGranted`)."""
    out: List[Tuple[str, int]] = []
    for note in mcp_result.get("notifications") or []:
        loot = note.get("lootGranted") or {}
        for item in loot.get("items") or []:
            tid = item.get("itemType", "")
            try:
                qty = int(item.get("quantity", 0) or 0)
            except (TypeError, ValueError):
                qty = 0
            if tid:
                out.append((tid, qty))
    return out


def _extract_purchase_loot(mcp_result: dict) -> List[Tuple[str, int]]:
    """Extract loot from a PurchaseCatalogEntry response. The schema is
    slightly different — rewards come in `notifications[].lootResult.items`
    (for llama catalog purchases) rather than `lootGranted.items`."""
    out: List[Tuple[str, int]] = []
    for note in mcp_result.get("notifications") or []:
        loot = note.get("lootResult") or note.get("lootGranted") or {}
        for item in loot.get("items") or []:
            tid = item.get("itemType", "")
            try:
                qty = int(item.get("quantity", 0) or 0)
            except (TypeError, ValueError):
                qty = 0
            if tid:
                out.append((tid, qty))
    return out


def _short_template(template_id: str) -> str:
    return template_id.rsplit(":", 1)[-1] if ":" in template_id else template_id
