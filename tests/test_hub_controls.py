"""Tests for the hub's drawn controls: StyledButton, NavList, TabbedBook, PageStack and ReadableText."""
import pytest
import wx

from lib.hub.controls import NavItem, NavList, PageStack, ReadableText, StyledButton, TabbedBook, TextLine


@pytest.fixture
def frame():
    app = wx.App.Get() or wx.App(False)
    frame = wx.Frame(None)
    panel = wx.Panel(frame)
    yield panel
    frame.Destroy()
    app.ProcessPendingEvents()


def test_styled_button_is_a_native_button(frame):
    clicks = []
    button = StyledButton(frame, label="&Install Fortnite", icon="download", variant="primary")
    button.Bind(wx.EVT_BUTTON, lambda e: clicks.append(e.GetEventObject()))
    assert isinstance(button, wx.Button)
    assert button.GetLabelText() == "Install Fortnite"

    event = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
    event.SetEventObject(button)
    button.ProcessWindowEvent(event)
    assert clicks == [button]


def test_styled_button_accepts_wx_button_arguments(frame):
    button = StyledButton(frame, wx.ID_CANCEL, "&Close", size=(200, 40))
    assert button.GetId() == wx.ID_CANCEL
    assert button.GetSize() == wx.Size(200, 40)


def test_styled_button_grows_with_its_label(frame):
    button = StyledButton(frame, label="Go")
    short = button.GetMinSize().width
    button.SetLabel("Go somewhere much further away")
    assert button.GetMinSize().width > short


def test_nav_list_selection_and_type_ahead(frame):
    items = [NavItem("home", "Home", "home"), NavItem("fortnite", "Fortnite", "home", "Play"),
             NavItem("locker", "Locker", "home", "Account")]
    nav = NavList(frame, items)
    selected = []
    nav.on_select = selected.append
    nav.set_selection(0)
    assert selected == []  # no notify
    nav.set_selection(2, notify=True)
    assert selected == [2]
    nav._type_ahead("f")
    assert nav.selection == 1
    assert nav.item_description(1) == "Play"


def test_tabbed_book_matches_notebook_api(frame):
    book = TabbedBook(frame)
    pages = [wx.Panel(book) for _ in range(3)]
    for index, page in enumerate(pages):
        book.AddPage(page, f"Tab {index}")
    changes = []
    book.Bind(wx.EVT_NOTEBOOK_PAGE_CHANGED, lambda e: changes.append((e.GetSelection(), e.GetOldSelection())))

    assert book.GetPageCount() == 3
    assert book.GetSelection() == 0
    assert all(page.GetParent() is book.book for page in pages)
    assert pages[0].IsShown() and not pages[1].IsShown()

    book.SetSelection(2)
    assert changes == [(2, 0)]
    assert book.GetCurrentPage() is pages[2]
    assert pages[2].IsShown() and not pages[0].IsShown()

    book.ChangeSelection(1)  # like wx.Notebook, no event
    assert changes == [(2, 0)]
    assert book.tabs.selection == 1

    book.AdvanceSelection()
    assert changes[-1] == (2, 1)

    book.DeletePage(2)
    assert book.GetPageCount() == 2
    assert book.GetSelection() == 1
    assert book.GetPageText(1) == "Tab 1"
    book.DeleteAllPages()
    assert book.GetPageCount() == 0


def test_page_stack_switches_pages_without_moving_focus(frame):
    button = wx.Button(frame, label="Stay here")
    stack = PageStack(frame)
    pages = []
    for _ in range(2):
        page = wx.Panel(stack)
        wx.Button(page, label="Inside")
        stack.AddPage(page)
        pages.append(page)
    frame.GetParent().Show()
    button.SetFocus()
    for index in (0, 1, 0):
        stack.ChangeSelection(index)
        wx.SafeYield()
        assert wx.Window.FindFocus() is button
        assert pages[index].IsShown() and not pages[1 - index].IsShown()


def test_readable_text_is_a_tab_stop_only_with_text(frame):
    text = ReadableText(frame, "")
    assert not text.AcceptsFocusFromKeyboard()
    text.SetLabel("Keybinds are active.")
    assert text.AcceptsFocusFromKeyboard()
    assert text.GetLabel() == "Keybinds are active."
    text.separator = ", "
    text.set_lines([TextLine("Fortnite"), TextLine(""), TextLine("Ready")])
    assert text.accessible_text() == "Fortnite, Ready"
    assert text.GetAccessible().GetName(0) == (wx.ACC_OK, "Fortnite, Ready")
    assert text.GetAccessible().GetRole(0) == (wx.ACC_OK, wx.ROLE_SYSTEM_STATICTEXT)
