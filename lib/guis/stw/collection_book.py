"""
Collection Book STW sub-dialog: view slot progress and research items back.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import wx

from lib.guis.stw.base import StwSubDialog, speak_later

logger = logging.getLogger(__name__)


class CollectionBookDialog(StwSubDialog):
    """Lists items slotted in the Collection Book and exposes Research-Item-
    From-Collection-Book as an action. Claim-all has its own menu entry.
    """

    def __init__(self, parent, stw_api):
        self._list: Optional[wx.ListCtrl] = None
        self._research_text: Optional[wx.TextCtrl] = None
        self._summary_label: Optional[wx.StaticText] = None
        self._slots: List[Tuple[str, Dict]] = []
        super().__init__(
            parent,
            stw_api,
            title="Save the World — Collection Book",
            help_id="SaveTheWorldCollectionBook",
            default_size=(820, 580),
        )

    def _build_ui(self, sizer: wx.BoxSizer) -> None:
        self._summary_label = wx.StaticText(self, label="")
        sizer.Add(self._summary_label, 0, wx.ALL, 10)

        self._list = wx.ListCtrl(
            self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.LC_HRULES,
        )
        self._list.InsertColumn(0, "Slotted Item", width=420)
        self._list.InsertColumn(1, "Template", width=320)
        sizer.Add(self._list, 1, wx.EXPAND | wx.ALL, 10)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Research templateId:"),
                0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self._research_text = wx.TextCtrl(self)
        row.Add(self._research_text, 1)
        sizer.Add(row, 0, wx.EXPAND | wx.ALL, 10)

    def _add_extra_buttons(self, sizer: wx.BoxSizer) -> None:
        research_btn = wx.Button(self, label="&Research Item")
        research_btn.Bind(wx.EVT_BUTTON, self._on_research)
        sizer.Add(research_btn, 0, wx.ALL, 5)

    def _populate(self) -> None:
        self.stw_api.query_profile()
        items = self.stw_api._items()
        self._slots = []
        # Collection book slots are items with templateId prefix
        # "CollectionBookPage:" or whose attributes include `slotted_`.
        for item_id, item in items.items():
            template = item.get("templateId", "")
            if (
                template.startswith("CollectionBookPage:")
                or template.startswith("CollectionBook:")
            ):
                self._slots.append((item_id, item))
        self._list.DeleteAllItems()
        if not self._slots:
            self._summary_label.SetLabel(
                "Collection Book data not exposed by this profile endpoint. "
                "You can still research items by typing their template ID below."
            )
            self._list.InsertItem(0, "(no slotted items)")
            return
        self._summary_label.SetLabel(
            f"{len(self._slots)} Collection Book entries."
        )
        for idx, (item_id, item) in enumerate(self._slots):
            template = item.get("templateId", "")
            name = template.rsplit(":", 1)[-1]
            self._list.InsertItem(idx, name)
            self._list.SetItem(idx, 1, template)

    def _on_research(self, _evt: wx.CommandEvent) -> None:
        template_id = (self._research_text.GetValue() or "").strip()
        if not template_id:
            self.show_error("Enter a template ID to research.")
            return
        if not self.confirm(
            f"Research item '{template_id}' from the Collection Book? "
            "Consumes Collection Book XP.",
            "Confirm Research",
        ):
            return
        ok = self.stw_api.research_item_from_collection_book(template_id)
        if ok:
            speak_later("Item researched.")
        else:
            self.show_error("Could not research item.")
