from copy import deepcopy
from types import SimpleNamespace

from lib.managers.quest_announcements import QuestAnnouncements
from lib.managers.quest_manager import QuestStore
from lib.monitors.quest_account_monitor import QuestAccountMonitor

TEMPLATE = 'Quest:quest_test'
CATALOG = {TEMPLATE.lower(): dict(name='Search containers')}


def snapshot(amount, state='Active', identity='instance'):
    return dict(updated_at=100, quests=[dict(template=TEMPLATE, id=identity,
        state=state, expired=False, objectives=[dict(achieved=amount, required=10, hidden=False)])])


def packet(before, after, state=1, previous_state=1):
    def quest(amount, current):
        return dict(template=TEMPLATE, uid='packet-instance', state=current,
            objectives=[dict(id=1, achieved=amount, required=10, visible=True, active=True)])
    return dict(kind='quest_completed' if state in (2, 3) else 'quest_progress',
                quest=quest(after, state), previous=quest(before, previous_state))


def test_initial_api_is_silent_and_polling_announces_changes_only():
    history = QuestAnnouncements(CATALOG)
    assert history.feed_api(snapshot(3)) == []
    assert history.feed_api(snapshot(3)) == []
    assert history.feed_api(snapshot(4)) == ['Search containers. 4 of 10.']
    assert history.feed_api(snapshot(4)) == []


def test_packet_first_and_api_first_are_deduplicated():
    for packet_first in (True, False):
        history = QuestAnnouncements(CATALOG)
        history.feed_api(snapshot(3))
        calls = [lambda: history.feed_packet(packet(3, 4)), lambda: history.feed_api(snapshot(4))]
        if not packet_first:
            calls.reverse()
        assert [message for call in calls for message in call()] == ['Search containers. 4 of 10.']
        assert history.feed_api(snapshot(3)) == []  # Lagging account revision.
        assert history.feed_api(snapshot(4)) == []


def test_completion_once_and_no_historical_progress_after_completion():
    history = QuestAnnouncements(CATALOG)
    history.feed_api(snapshot(8))
    assert history.feed_packet(packet(8, 10, 2)) == ['Quest complete. Search containers.']
    assert history.feed_api(snapshot(10, 'Claimed')) == []
    assert history.feed_packet(packet(8, 9)) == []


def test_start_mid_match_and_first_account_snapshot_do_not_repeat():
    history = QuestAnnouncements(CATALOG)
    assert history.feed_packet(packet(3, 4)) == ['Search containers. 4 of 10.']
    assert history.feed_api(snapshot(4)) == []


def test_new_repeatable_instance_resets_silently():
    history = QuestAnnouncements(CATALOG)
    history.feed_api(snapshot(10, 'Claimed'))
    assert history.feed_api(snapshot(0, identity='new-instance')) == []
    assert history.feed_api(snapshot(1, identity='new-instance')) == ['Search containers. 1 of 10.']


def test_snapshot_and_disabled_packet_updates_are_silent():
    history = QuestAnnouncements(CATALOG)
    event = packet(3, 4)
    assert history.feed_packet(dict(kind='quest_snapshot', quests=[event['quest']])) == []
    assert history.feed_packet(packet(4, 5), announce=False) == []
    assert history.feed_packet(packet(5, 6)) == ['Search containers. 6 of 10.']


def test_background_monitor_runs_without_window_and_honors_disable_during_request():
    spoken = []
    enabled = [True]
    snapshots = iter([snapshot(3), snapshot(4)])
    auth = SimpleNamespace(account_id='test-account', access_token='test-token')
    api = SimpleNamespace(auth=auth, query=lambda: next(snapshots))
    history = QuestAnnouncements(CATALOG)
    monitor = QuestAccountMonitor(api, SimpleNamespace(speak=lambda text, **kw: spoken.append(text)),
        lambda: enabled[0], history, QuestStore())
    monitor.wizard_paused = lambda: False
    assert monitor.process_once() == []
    assert monitor.process_once() == ['Search containers. 4 of 10.']
    assert spoken == ['Search containers. 4 of 10.']
    def late_response():
        enabled[0] = False
        return snapshot(5)
    api.query = late_response
    assert monitor.process_once() == []
    assert len(spoken) == 1


def test_suppressed_account_quests_do_not_announce_progress():
    history = QuestAnnouncements(CATALOG)
    history.feed_api(snapshot(3))
    update = snapshot(4)
    update['quests'][0]['suppressed'] = True
    assert history.feed_api(update) == []
