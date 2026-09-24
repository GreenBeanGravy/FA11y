"""Continuously refresh quest progress without requiring an open window."""
import logging
from lib.monitors.base import BaseMonitor
from lib.managers.quest_announcements import quest_announcements
from lib.managers.quest_manager import quest_store
from lib.utilities.epic_quests import EpicQuestAPI, QuestQueryError

logger = logging.getLogger(__name__)


class QuestAccountMonitor(BaseMonitor):
    _THREAD_NAME = 'QuestAccountProgress'
    POLL_SECONDS = 15

    def __init__(self, api=None, speaker=None, enabled=None, history=None, store=None):
        super().__init__()
        self.api = api
        self.speaker = speaker
        self.enabled = enabled
        self.history = history or quest_announcements
        self.store = store or quest_store
        self._account = None
        self._baseline_logged = False

    def is_enabled(self):
        if self.enabled is not None:
            return self.enabled()
        from lib.utilities.utilities import read_config, get_config_boolean
        return get_config_boolean(read_config(), 'QuestAnnouncements', True)

    def process_once(self):
        if self.stop_event.is_set() or self.wizard_paused() or not self.is_enabled():
            return []
        if self.api is None:
            from lib.utilities.epic_auth import get_epic_auth_instance
            self.api = EpicQuestAPI(get_epic_auth_instance())
        auth = self.api.auth
        if not auth or not auth.access_token or not auth.account_id:
            return []
        account = auth.account_id
        if self._account != account:
            if self._account is not None:
                self.history.reset()
            self._account = account
            self._baseline_logged = False
        snapshot = self.api.query()
        # Shutdown, account changes, or disabling while HTTP is pending must
        # not release a stale burst of speech when the request completes.
        if (self.stop_event.is_set() or self.wizard_paused() or not self.is_enabled()
                or auth.account_id != account):
            return []
        self.store.replace_api(snapshot)
        messages = self.history.feed_api(snapshot)
        if not self._baseline_logged:
            logger.info('Account quest baseline loaded: %d quests; polling every %d seconds',
                        len(snapshot['quests']), self.POLL_SECONDS)
            self._baseline_logged = True
        speaker = self.speaker
        if speaker is None:
            from lib.app import state
            speaker = state.speaker
        if speaker is not None:
            for message in messages:
                if self.stop_event.is_set() or not self.is_enabled():
                    break
                speaker.speak(message, interrupt=False)
                logger.info('Quest progress speech: %s', message)
        return messages

    def _monitor_loop(self):
        failures = 0
        was_enabled = True
        while not self.stop_event.is_set():
            enabled = self.is_enabled() and not self.wizard_paused()
            if not enabled:
                if was_enabled:
                    self.history.reset()
                was_enabled = False
                self.stop_event.wait(1)
                continue
            was_enabled = True
            delay = self.POLL_SECONDS
            try:
                self.process_once()
                if failures:
                    logger.info('Account quest monitoring recovered')
                failures = 0
            except QuestQueryError as error:
                failures += 1
                delay = min(300, self.POLL_SECONDS * 2 ** min(failures, 5))
                if failures == 1:
                    logger.warning('Account quest monitoring: %s', error)
            except Exception:
                failures += 1
                delay = min(300, self.POLL_SECONDS * 2 ** min(failures, 5))
                if failures == 1:
                    logger.warning('Account quest monitoring could not process an update')
            self.stop_event.wait(delay)


quest_account_monitor = QuestAccountMonitor()
