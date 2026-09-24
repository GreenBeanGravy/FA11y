"""Merge an account snapshot with newer, explicitly identified match quests."""
from collections import Counter
import copy
import threading

from lib.utilities.epic_quests import quest_catalog


class QuestStore:
    def __init__(self):
        self.lock = threading.RLock()
        self.api = {'quests': [], 'updated_at': None}
        self.packet = {}
        self.epoch = None
        self.revision = 0

    def replace_api(self, snapshot):
        with self.lock:
            self.api = copy.deepcopy(snapshot)
            self.revision += 1

    def reset_packet(self, epoch):
        with self.lock:
            if epoch != self.epoch:
                self.epoch = epoch
                self.packet.clear()
                self.revision += 1

    def feed_packet(self, event, epoch):
        self.reset_packet(epoch)
        quests = event.get('quests', []) if event['kind'] == 'quest_snapshot' else [event['quest']]
        catalog = quest_catalog()
        with self.lock:
            for quest in quests:
                key = quest['template'].lower()
                meta = catalog.get(key, {})
                self.packet[key] = dict(id='packet:' + key, template=quest['template'],
                    name=meta.get('name') or quest['template'].partition(':')[2],
                    description=meta.get('description', ''), state=('Inactive', 'Active', 'Completed', 'Claimed')[quest['state']],
                    objectives=[dict(key=str(v['id']), achieved=v['achieved'], required=v['required'],
                        description='', hidden=not v['visible'], active=v.get('active'),
                        stage=v.get('stage'), display_stage=v.get('display_stage'),
                        display_max=v.get('display_max')) for v in quest['objectives'] if v],
                    completion_count=meta.get('completion_count'),
                    categories=meta.get('categories', []), products=meta.get('products', []),
                    hidden=meta.get('hidden', False), metadata_available=bool(meta), expired=False,
                    expiry=None, source='match_packets', updated_at=event['received_at'])
            self.revision += 1

    def snapshot(self):
        with self.lock:
            rows = copy.deepcopy(self.api['quests'])
            counts = Counter(q['template'].lower() for q in rows)
            used = set()
            for index, row in enumerate(rows):
                key = row['template'].lower()
                if key not in self.packet or counts[key] != 1:
                    continue
                packet = self.packet[key]
                objectives = copy.deepcopy(packet['objectives'])
                # Sparse replication must not erase recorded account counters,
                # and an older active sample cannot undo confirmed completion.
                if (not objectives or not any(o.get('achieved') is not None for o in objectives)
                        or (row['state'].lower() in ('completed','claimed')
                            and packet['state'].lower() not in ('completed','claimed')
                            and packet['updated_at'] <= (self.api.get('updated_at') or 0))):
                    used.add(key)
                    continue
                # A single objective is unambiguous. Numeric packet IDs are not
                # backend names, so do not pair multiple objectives by position.
                if len(objectives) == len(row['objectives']) == 1:
                    objectives[0]['description'] = row['objectives'][0].get('description', '')
                # Match replication can lead the persisted account profile.
                # Keep it authoritative for the current match epoch only.
                rows[index] = dict(row, state=packet['state'], objectives=objectives,
                                   source=packet['source'], updated_at=packet['updated_at'])
                used.add(key)
            rows.extend(copy.deepcopy(v) for key, v in self.packet.items() if key not in used and not counts[key])
            return self.revision, dict(quests=rows, updated_at=self.api.get('updated_at'))


quest_store = QuestStore()
