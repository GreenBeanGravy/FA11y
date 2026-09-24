"""Player-facing quest text and grouping, independent of wx and account access."""
from datetime import datetime, timezone
from functools import lru_cache
import html
import json
from pathlib import Path
import re

from lib.utilities.epic_quests import quest_catalog


def clean_text(value):
    text = html.unescape(value or '')
    return ' '.join(re.sub(r'<[^>]*>', '', text).split())


def readable(value):
    text = clean_text(value)
    return bool(text) and not re.search(
        r'QuestCategory\.|^Quest:|^quest_|LOCTEXT|\{[^}]*\}|\[Community Winner|\bTBD\b|\bPLACEHOLDER\b|dummy reward token', text, re.I)


def natural_key(text):
    return tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                 for part in re.split(r'(\d+)', text))


@lru_cache(maxsize=1)
def group_catalog():
    try:
        groups = json.loads((Path(__file__).resolve().parents[1] / 'data/quest_groups_4210.json').read_text(encoding='utf-8'))
        supplement = Path(__file__).resolve().parents[1] / 'data/quest_supplement_4220.json'
        if supplement.exists():
            groups['categories'].extend(json.loads(supplement.read_text(encoding='utf-8')).get('categories', []))
        return groups
    except (OSError, ValueError):
        return dict(categories=[], products={})


def _matches(tag, prefix):
    return tag == prefix or tag.startswith(prefix + '.')


def category_text(tags, groups):
    if any(_matches(tag, 'QuestCategory.BR.Daily') for tag in tags):
        return 'Daily Quests'
    if any(_matches(tag, 'QuestCategory.BR.S42.CosmicThunder.Repeatable') for tag in tags):
        return 'Override Daily Quests' + (' / Bonus goals' if any('Bonus' in tag for tag in tags) else '')
    matches = []
    for category in groups['categories']:
        if any(_matches(tag, excluded) for tag in tags for excluded in category['exclude']):
            continue
        for prefix in category['tags']:
            if any(_matches(tag, prefix) for tag in tags) and readable(category['name']):
                matches.append((len(prefix), category))
    if not matches:
        return 'Other quests'
    # A season-specific category wins over a generic historical category.
    category = max(matches, key=lambda pair: (pair[0], pair[1]['asset']))[1]
    title = clean_text(category['name'])
    headers = [h for h in category['headers'] if h.get('tag') and readable(h['name'])
               and any(_matches(tag, h['tag']) for tag in tags)]
    if headers:
        header = clean_text(max(headers, key=lambda h: len(h['tag']))['name'])
        if header.casefold() != title.casefold():
            title += ' / ' + header
    if 'bonus goal' not in title.casefold() and any(re.search(r'\.(BonusGoals?|Bonus)$', tag) for tag in tags):
        title += ' / Bonus goals'
    return title


def mode_text(tags, metadata, groups):
    if any(_matches(tag, 'QuestCategory.All.MobileQuests') for tag in tags):
        return 'Fortnite mobile app'
    if any(_matches(tag, 'QuestCategory.Mimosa') for tag in tags):
        return 'Sidekicks (multiple modes)'
    aliases = {'BR': 'BR', 'BB': 'BlastBerry', 'Figment': 'Figment', 'Juno': 'Juno',
               'FNE': 'FNE', 'SquareClub': 'SquareClub', 'ForbiddenFruit': 'ForbiddenFruit',
               'Sprout': 'Sprout', 'DelMar': 'DelMar'}
    for tag in tags:
        parts = tag.split('.')
        if len(parts) > 1 and parts[1] in aliases:
            name = groups['products'].get('Product.' + aliases[parts[1]])
            if name:
                return clean_text(name)
        if len(parts) > 1 and parts[1] == 'Sparks':
            return 'Fortnite Festival'
    query = metadata.get('product_query', {})
    stream = query.get('QueryTokenStream', [])
    dictionary = query.get('TagDictionary', [])
    # Only flat ANY/ALL positive expressions are used as fallback. A query's
    # dictionary alone can also contain exclusions or unused entries.
    if len(stream) >= 4 and stream[:2] == [0, 1] and stream[2] in (1, 2) and len(stream) == 4 + stream[3]:
        indices = stream[4:]
        if all(type(i) is int and 0 <= i < len(dictionary) for i in indices):
            product_tags = [dictionary[i].get('TagName', '') for i in indices
                            if dictionary[i].get('TagName', '').startswith('Product.')]
            names = {groups['products'].get(tag) for tag in product_tags}
            if len(names) == 1 and None not in names:
                return clean_text(next(iter(names)))
            if len(product_tags) > 1:
                return 'Multiple modes'
    return 'Mode not identified'


def compatible_modes(tags, metadata, groups):
    """Expand only an explicit flat ANY product query; never treat exclusions as modes."""
    mode = mode_text(tags, metadata, groups)
    query = metadata.get('product_query', {})
    stream, dictionary = query.get('QueryTokenStream', []), query.get('TagDictionary', [])
    if (len(stream) >= 4 and stream[:3] == [0, 1, 1]
            and len(stream) == 4 + stream[3]
            and all(type(i) is int and 0 <= i < len(dictionary) for i in stream[4:])):
        names = [groups['products'].get(dictionary[i].get('TagName')) for i in stream[4:]]
        if names and all(names):
            return sorted({clean_text(name) for name in names}, key=natural_key)
    return [mode]


def matches_mode(row, mode):
    return mode == 'All modes' or mode in row.get('modes', [row['mode']]) or mode == row['mode']


@lru_cache(maxsize=1)
def pass_reward_names():
    try:
        return json.loads((Path(__file__).resolve().parents[1]/'data/pass_quest_rewards_4220.json').read_text(encoding='utf-8'))['rows']
    except (OSError,ValueError,KeyError):
        return {}


def prepare_quests(quests, catalog=None, groups=None, contextual_templates=None):
    catalog = quest_catalog() if catalog is None else catalog
    groups = group_catalog() if groups is None else groups
    rows, hidden, unresolved = [], 0, 0
    for quest in quests:
        contextual=quest.get('template','').lower() in (contextual_templates or ())
        metadata = catalog.get(quest.get('template', '').lower(), {})
        tags = quest.get('categories', [])
        visibility = metadata.get('visibility', {})
        state = quest.get('state', '').lower()
        state_field = {'active': 'bIsVisibleWhenActive', 'inactive': 'bIsVisibleWhenInactive',
                       'completed': 'bIsVisibleWhenCompleted', 'claimed': 'bIsVisibleWhenCompleted'}.get(state)
        if (state not in ('active', 'completed', 'claimed')
                or (quest.get('suppressed') and state not in ('completed','claimed'))
                or (not contextual and (quest.get('hidden') or metadata.get('hidden') or visibility.get(state_field) is False
                or any('Hidden' in tag.split('.') for tag in tags)))):
            hidden += 1
            continue
        tracker=pass_reward_names().get(quest.get('template','').lower()) if contextual else None
        name = tracker['name']+' reward' if tracker else clean_text(quest.get('name'))
        if contextual and (not readable(name) or 'dummy reward token' in name.lower()):
            name='Selected pass reward quest'
        if not quest.get('metadata_available') or not readable(name):
            unresolved += 1
            continue
        description = clean_text(quest.get('description'))
        row = dict(quest, name=name, description=description if readable(description) else '',
                   mode=mode_text(tags, metadata, groups), modes=compatible_modes(tags, metadata, groups),
                   category=category_text(tags, groups))
        if tracker:
            row['reward_tracker']=True
            row['description']='Reward unlock tracker for '+tracker['name']+'. This is an internal reward record, not a playable quest. Epic has not supplied quest instructions for this record. Missing progress does not mean zero progress.'
        rows.append(row)
    return rows, hidden, unresolved


def filter_quests(rows, mode='All modes', category='All categories', status='Active', query='', expired=False):
    query = clean_text(query).casefold()
    result = []
    for row in rows:
        state = row['state'].lower()
        if state not in ('active', 'completed', 'claimed') or not matches_mode(row, mode):
            continue
        if category != 'All categories' and row['category'] != category:
            continue
        if not expired and row.get('expired'):
            continue
        if status == 'Active' and state != 'active':
            continue
        if status == 'Completed' and state not in ('completed', 'claimed'):
            continue
        if status == 'Inactive' and state != 'inactive':
            continue
        searchable = ' '.join([row['name'], row['description'], row['mode'], row['category']]
                              + [clean_text(o.get('description')) for o in row['objectives'] if not o.get('hidden')])
        if query and query not in searchable.casefold():
            continue
        result.append(row)
    return sorted(result, key=lambda q: (natural_key(q['mode']), natural_key(q['category']),
        natural_key(q['name']), tuple(o.get('required') or 0 for o in q['objectives']), q['id']))


def objective_progress(objective):
    count, target = objective.get('achieved'), objective.get('required')
    def number(value):
        # Preserve fractional values without the six-significant-digit rounding
        # of :g, which can turn a nearly complete large counter into its target.
        return format(int(value), ',') if value == int(value) else format(value, ',')
    if count is None:
        return f'Progress not reported; target {number(target)}' if target is not None else 'Progress not reported'
    if target is None:
        return f'{number(count)}; target unavailable'
    return f'{number(count)} of {number(target)}'


def list_label(quest, include_mode=False):
    if quest.get('reward_tracker'):
        status={'claimed':'Reward claimed','completed':'Completion confirmed'}.get(quest['state'].lower())
        if not status:
            counters=[o for o in quest['objectives'] if o.get('achieved') is not None]
            status='; '.join(objective_progress(o) for o in counters) if counters else 'Unlock progress unavailable'
        return quest['name']+' - '+status
    prefix = f"{quest['mode']} / " if include_mode else ''
    objectives = [o for o in quest['objectives'] if not o.get('hidden')]
    progress = '; '.join((f'Objective {i}: ' if len(objectives) > 1 else '') + objective_progress(o)
                         for i, o in enumerate(objectives, 1))
    progress = completion_summary(quest) or progress
    if quest['state'].lower() in ('completed','claimed') and not any(o.get('achieved') is not None for o in objectives):
        progress = 'Completion confirmed by Epic; detailed counters not supplied'
    state = 'Completed' if quest['state'].lower() in ('completed', 'claimed') else quest['state']
    suffix = '' if state.lower() == 'active' else f' — {state}'
    return f"{quest['name']} — {progress or 'No counter reported'} — {prefix}{quest['category']}{suffix}"


def completion_summary(quest):
    required = quest.get('completion_count')
    objectives = quest['objectives']
    if not isinstance(required, int) or required <= 0 or len(objectives) < 2:
        return ''
    completed = sum(o.get('achieved') is not None and o.get('required') is not None
                    and o['achieved'] >= o['required'] for o in objectives)
    unknown = any(o.get('achieved') is None or o.get('required') is None for o in objectives)
    prefix = 'At least ' if unknown else ''
    return f'{prefix}{completed} of {required} objectives completed' + ('; some progress not reported' if unknown else '')


def list_labels(quests, include_mode=False):
    from collections import Counter
    labels = [list_label(quest, include_mode) for quest in quests]
    counts, seen = Counter(labels), Counter()
    result = []
    for label in labels:
        seen[label] += 1
        result.append(f'{label} — Separate quest {seen[label]} of {counts[label]}' if counts[label] > 1 else label)
    return result


def details_text(quest):
    lines = [quest['name'], 'Mode: ' + ', '.join(quest.get('modes', [quest['mode']])), 'Category: ' + quest['category'],
             'Status: ' + ('Completed (reward claimed)' if quest['state'].lower() == 'claimed' else quest['state'])]
    if quest['description'] and quest['description'] != quest['name']:
        lines += ['', quest['description']]
    objectives = [o for o in quest['objectives'] if not o.get('hidden')]
    summary = completion_summary(quest)
    if summary:
        lines.extend(['', summary])
    for i, objective in enumerate(objectives, 1):
        description = clean_text(objective.get('description'))
        label = description if readable(description) else ('Progress' if len(objectives) == 1 else f'Objective {i}')
        lines.extend(['', f'{label}: {objective_progress(objective)}'])
    if not objectives:
        lines.append('No objective counter reported.')
    expiry = quest.get('expiry')
    if expiry:
        try:
            date = datetime.fromisoformat(expiry.replace('Z', '+00:00'))
            if date.year > 1:
                local = date.replace(tzinfo=date.tzinfo or timezone.utc).astimezone()
                lines.append(('Expired: ' if quest.get('expired') else 'Expires: ') + local.strftime('%B %d, %Y at %I:%M %p %Z'))
        except (ValueError, OverflowError):
            pass
    lines.append('Updated from match packets.' if quest['source'] == 'match_packets' else 'Updated from your Epic account.')
    return '\n'.join(lines)
