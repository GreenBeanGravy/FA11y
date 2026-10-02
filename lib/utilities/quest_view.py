"""What the quest browser shows for a snapshot and a set of filters, without any window code.

The wx QuestView and the new window's quests handler both call render_quests,
so the filter choices, list items, details and status line are made once.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional

from lib.utilities.quest_presentation import (details_text, filter_quests, list_labels, matches_mode,
                                              natural_key, prepare_quests)

ALL_MODES = 'All modes'
ALL_CATEGORIES = 'All categories'
STATUS_CHOICES = ['Active', 'Completed', 'All']
DEFAULT_MODE = 'Battle Royale'


def keep_choice(selected: Optional[str], values: List[str]) -> str:
    """The selected value if it is still offered, else the first one."""
    return selected if selected in values else values[0]


def render_quests(snapshot: dict, *, mode: Optional[str] = None, category: Optional[str] = None,
                  status: str = 'Active', query: str = '', expired: bool = False,
                  templates: Optional[Iterable[str]] = None, scope_label: Optional[str] = None,
                  error: Optional[str] = None) -> dict:
    """Everything the browser shows.

    mode None means "not chosen yet": Battle Royale when there are quests for it, else all modes.
    Returns modes, mode, categories, category, rows (id, label, details), and the status line.
    """
    templates = set(templates) if templates is not None else None
    rows, hidden, unresolved = prepare_quests(snapshot['quests'], contextual_templates=templates)
    if templates is not None:
        rows = [q for q in rows if q['template'].lower() in templates]
    modes = [ALL_MODES] + sorted({m for q in rows for m in q['modes']}, key=natural_key)
    if mode is None:
        mode = DEFAULT_MODE if rows and DEFAULT_MODE in modes else ALL_MODES
    mode = keep_choice(mode, modes)
    if scope_label:
        rows = [dict(q, category=scope_label) for q in rows]
        categories = [scope_label]
    else:
        found = {q['category'] for q in rows if matches_mode(q, mode)}
        categories = [ALL_CATEGORIES] + sorted(found, key=natural_key)
    category = keep_choice(category, categories)
    shown = filter_quests(rows, mode=mode, category=category, status=status, query=query, expired=expired)
    labels = list_labels(shown, include_mode=mode == ALL_MODES)
    when = snapshot.get('updated_at')
    stamp = datetime.fromtimestamp(when).strftime('%I:%M:%S %p') if when else 'not yet loaded'
    return {
        'modes': modes, 'mode': mode, 'categories': categories, 'category': category,
        'rows': [{'id': q['id'], 'label': label, 'details': details_text(q)} for q, label in zip(shown, labels)],
        'status': error or (f'{len(shown)} quests shown. {hidden} inactive, hidden, or suppressed quests excluded; '
                            f'{unresolved} quests awaiting readable names. Account snapshot: {stamp}.'),
        'empty_details': 'No quests match these filters.',
    }
