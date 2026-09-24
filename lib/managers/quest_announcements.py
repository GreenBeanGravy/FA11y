"""Share quest announcement history between packet and account updates."""
import threading
from lib.utilities.epic_quests import quest_catalog


class QuestAnnouncements:
    def __init__(self, catalog=None):
        self.catalog = catalog
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        with self.lock:
            self.records = {}
            self.api_seen = False

    def _accept(self, template, state, objectives, baseline=False, identity=None, source=None):
        key = template.lower()
        catalog = self.catalog if self.catalog is not None else quest_catalog()
        metadata = catalog.get(key, {})
        if not key.startswith('quest:') or not metadata.get('name') or metadata.get('hidden'):
            return None
        if key not in self.records and len(self.records) >= 4096:
            return None
        record = self.records.setdefault(key, dict(values={}, completed=False, identities={}))
        if identity is not None:
            old_identity = record['identities'].get(source)
            if old_identity is not None and old_identity != identity:
                # A new repeatable instance is a new baseline, not a reward.
                record = dict(values={}, completed=False, identities={})
                self.records[key] = record
                baseline = True
            record['identities'][source] = identity
        complete = state.lower() in ('completed', 'claimed')
        announce_complete = complete and not record['completed'] and not baseline
        changes = []
        for index, objective in enumerate(objectives):
            value = objective.get('achieved')
            if value is None:
                continue
            old = record['values'].get(index)
            if old is None or value > old:
                record['values'][index] = value
                if not baseline and not objective.get('hidden') and (old is None or value != old):
                    target = objective.get('required')
                    changes.append(f'{value:g} of {target:g}' if target is not None else f'Progress {value:g}')
        record['completed'] |= complete
        if announce_complete:
            return f"Quest complete. {metadata['name']}."
        if changes and not complete and not record['completed']:
            return f"{metadata['name']}. {'; '.join(changes)}."
        return None

    def feed_api(self, snapshot):
        from collections import Counter
        with self.lock:
            baseline = not self.api_seen
            self.api_seen = True
            counts = Counter(q['template'].lower() for q in snapshot['quests'])
            messages = []
            for quest in snapshot['quests']:
                if counts[quest['template'].lower()] != 1 or quest.get('expired') or quest.get('suppressed'):
                    continue
                key = quest['template'].lower()
                message = self._accept(quest['template'], quest['state'], quest['objectives'],
                    baseline=baseline or key not in self.records, identity=quest['id'], source='api')
                if message:
                    messages.append(message)
            return messages

    def feed_packet(self, event, announce=True):
        with self.lock:
            baseline = event['kind'] == 'quest_snapshot' or not announce
            quests = event.get('quests', []) if event['kind'] == 'quest_snapshot' else [event['quest']]
            messages = []
            for quest in quests:
                def objectives(value):
                    return [dict(achieved=v['achieved'], required=v['required'],
                                 hidden=not v['visible'] or not v['active']) for v in value['objectives'] if v]
                # A recovered change carries its prior state. Seed it silently
                # even when the monitor did not receive the initial snapshot.
                previous = event.get('previous')
                if previous is not None:
                    self._accept(previous['template'], ('Inactive', 'Active', 'Completed', 'Claimed')[previous['state']],
                                 objectives(previous), baseline=True, identity=previous.get('uid'), source='packet')
                message = self._accept(quest['template'], ('Inactive', 'Active', 'Completed', 'Claimed')[quest['state']],
                    objectives(quest), baseline=baseline, identity=quest.get('uid'), source='packet')
                if message:
                    messages.append(message)
            return messages


quest_announcements = QuestAnnouncements()
