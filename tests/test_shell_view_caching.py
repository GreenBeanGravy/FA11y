"""The Quests page asks for the same view several times; the core must not redo the work."""
from lib.shell.handlers import passes, quests
from lib.utilities import epic_passes, quest_presentation


def test_pass_catalog_is_read_once():
    assert epic_passes.load_pass_catalog() is epic_passes.load_pass_catalog()


def test_quest_view_is_rendered_once_per_revision_and_filters(monkeypatch):
    calls = []
    monkeypatch.setattr(quests, "_signed_in", lambda auth: True)
    monkeypatch.setattr(quests, "_auth", lambda: object())
    monkeypatch.setattr(quests, "render_quests", lambda snapshot, **kw: calls.append(kw) or {"rows": []})
    monkeypatch.setattr(quests, "_view_key", None)
    quests.quest_store.replace_api(dict(quests=[], updated_at=1))
    first = quests.view({"status": "Active"})
    assert quests.view({"status": "Active"}) is first
    assert len(calls) == 1
    quests.view({"status": "Completed"})
    quests.quest_store.replace_api(dict(quests=[], updated_at=2))
    quests.view({"status": "Completed"})
    assert len(calls) == 3


def test_category_is_worked_out_once_per_tag_set(monkeypatch):
    calls = []
    monkeypatch.setattr(quest_presentation, "category_text", lambda tags, groups: calls.append(1) or "Cat")
    quest = lambda i: dict(template=f"quest:{i}", name=f"Quest {i}", state="Active", metadata_available=True,
                           categories=["QuestCategory.BR.Daily"])
    rows = quest_presentation.prepare_quests([quest(i) for i in range(5)], catalog={}, groups=dict(categories=[], products={}))[0]
    assert len(rows) == 5 and len(calls) == 1


def test_passes_metadata_warms_once(monkeypatch):
    monkeypatch.setattr(passes, "_metadata", None)
    monkeypatch.setattr(passes, "_warming", False)
    started = []
    monkeypatch.setattr(passes.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: started.append(kw["name"])})())
    passes._warm_metadata()
    passes._warm_metadata()
    assert started == ["passes-metadata"]
