from lib.utilities.gamemode_selection import find_text, select_gamemode


def row(text, x, y):
    return (text, x, y, .99)


class MenuUI:
    def __init__(self, wrong_title=False, no_fill=True):
        self.stage = "lobby"
        self.actions = []
        self.wrong_title = wrong_title
        self.no_fill = no_fill

    def all_rows(self):
        if self.stage == "lobby":
            return [row("PLAY", .07, .065), row("HORDE RUSH", .13, .54), row("No Fill" if self.no_fill else "Fill", .1, .76), row("PLAY", .13, .845)]
        if self.stage == "discovery":
            return [row("Search Discover", .25, .175)]
        if self.stage == "typed":
            return [row("Horde Rush", .25, .175)]
        if self.stage == "results":
            return [row("Islands Results", .1, .345)]
        if self.stage == "focused":
            return [row("Islands Results", .1, .345), row("Horde Rush", .1, .545)]
        if self.stage == "details":
            return [row("About Island", .82, .196), row("SELECT", .125, .85), row("Wrong Mode" if self.wrong_title else "HORDE RUSH", .14, .1)]
        if self.stage == "fill":
            return self.lobby_rows() + [row("TEAM FILL", .72, .426)]
        raise AssertionError(self.stage)

    def observe(self, region=None):
        rows = self.all_rows()
        if region:
            rows = [r for r in rows if region[0] <= r[1] <= region[2] and region[1] <= r[2] <= region[3]]
        return rows

    def lobby_rows(self):
        return [row("HORDE RUSH", .13, .54), row("No Fill" if self.no_fill else "Fill", .1, .76), row("PLAY", .13, .845)]

    def click(self, label):
        self.actions.append(("click", label[0]))
        if label[0] == "PLAY":
            assert label[2] < .12, "Must never click matchmaking Play"
        if self.stage == "results":
            self.stage = "focused"
        elif self.stage == "focused":
            self.stage = "details"
        elif label[0] == "SELECT":
            self.stage = "lobby"
            self.no_fill = False
        elif label[0] == "Fill":
            self.stage = "fill"

    def scroll(self):
        self.stage = "discovery"

    def type(self, text):
        assert text == "Horde Rush"
        self.stage = "typed"

    def key(self, *keys):
        self.actions.append(("key", keys))
        if keys == ("enter",):
            self.stage = "results"
        elif keys == ("f",):
            self.no_fill = True
        elif keys == ("esc",):
            self.stage = "lobby"


def test_selection_verifies_mode_without_changing_match_settings(monkeypatch):
    monkeypatch.setattr("lib.utilities.gamemode_selection.time.sleep", lambda _: None)
    ui = MenuUI()
    assert select_gamemode("Horde Rush", "Horde Rush", ui) == (True, None)
    assert ui.stage == "lobby" and not ui.no_fill
    assert ("key", ("f",)) not in ui.actions
    assert ("click", "Fill") not in ui.actions


def test_wrong_result_is_not_selected(monkeypatch):
    monkeypatch.setattr("lib.utilities.gamemode_selection.time.sleep", lambda _: None)
    ui = MenuUI(wrong_title=True)
    success, error = select_gamemode("Horde Rush", "Horde Rush", ui)
    assert not success and "title" in error
    assert ("click", "SELECT") not in ui.actions


def test_duplicate_text_and_other_regions_are_not_targets():
    assert find_text([row("Select", .1, .8), row("Select", .8, .8)], "Select", exact=True) is None
    assert find_text([row("Play", .1, .8)], "Play", (0, 0, .2, .12), True) is None


def test_input_validation_does_not_touch_ui():
    ui = MenuUI()
    assert not select_gamemode("", ui=ui)[0]
    assert not ui.actions


def test_observed_royale_recognition_and_cursor_error():
    rows = [row("battle rovalel", .125, .175)]
    assert find_text(rows, "battle royale", exact=True, fuzzy=True, cursor=True)
    assert not find_text([row("Battle Royale OG", .125, .175)], "Battle Royale", exact=True, fuzzy=True)


def test_one_click_details_never_gets_artwork_second_click(monkeypatch):
    monkeypatch.setattr("lib.utilities.gamemode_selection.time.sleep", lambda _: None)
    class ImmediateDetails(MenuUI):
        def click(self, label):
            if self.stage == "results":
                self.actions.append(("click", label[0]))
                self.stage = "details"
            else:
                super().click(label)
    ui = ImmediateDetails(no_fill=False)
    assert select_gamemode("Horde Rush", "Horde Rush", ui) == (True,None)
    assert len([a for a in ui.actions if a == ("click", "")]) == 1

from lib.utilities.gamemode_selection import find_title, title_close_enough


def test_long_title_split_and_misread_is_verified():
    rows = [row("1V1 BUILD FIGHTS", .1, .1), row("[4.2.0] - EU/NA", .3, .1)]
    assert find_title(rows, "1v1 Build Fights [4.2.0] - EU/NA")
    assert title_close_enough("ZONE WARS - PRO SCRIMS PRACTlCE MAP", "Zone Wars - Pro Scrims Practice Map")
    assert title_close_enough("BOX FIGHTS PRO SCRIMS…", "Box Fights Pro Scrims 4v4 Ranked")


def test_short_or_different_titles_still_fail():
    assert not title_close_enough("HORDE RUSH", "Horde Bush Duos")
    assert not title_close_enough("Red vs Blue", "Red vs Blue 22")  # short titles allow one error at most
    assert not find_title([row("Tilted Zone Wars", .1, .1)], "Pandvil Box Fights")
