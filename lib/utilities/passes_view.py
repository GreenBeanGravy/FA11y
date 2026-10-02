"""What the pass browser shows, without any window code.

The wx PassesView and the new window's passes handler both build their texts
and button states here: ownership line, page choices, reward list items,
reward details, and which buttons are usable.
"""
from __future__ import annotations

from typing import Optional

from lib.utilities.epic_passes import (CURRENCY_NAMES, costs_text, pages, requirement_text, reward_status,
                                       rewards)
from lib.utilities.pass_quests import pass_quest_details, related_templates

SET_NOTICE = 'Cannot claim full set, please claim full page'
SHEER_WILL_TEXT = 'Cannot claim full set, please claim full page. Claim page 15 before page 16.'
HELP_TEXT = 'Arrow keys browse rewards. Page Up/Down changes pages. Ctrl+Tab changes passes.'


def metadata_by_id(cosmetics) -> dict:
    return {c.get('id', '').lower(): c for c in (cosmetics or [])}


def display_name(reward: dict, metadata: dict) -> str:
    meta = metadata.get(reward.get('item_id', ''), {})
    return reward.get('name') or meta.get('name') or 'Unnamed reward (' + reward.get('item_id', '') + ')'


def status_text(definition: dict, snapshot: Optional[dict]) -> str:
    """The ownership, level and currency line for a pass."""
    state = snapshot['passes'][definition['key']] if snapshot else None
    text = definition['season_name'] + '. '
    if not state or not state['active']:
        return text + 'Account status unavailable. Refresh to check this pass.'
    text += 'Premium pass owned. ' if state['purchased'] else 'Premium pass not owned. '
    text += f"Pass level: {state['level'] if state['level'] is not None else 'not reported'}. "
    currencies = {r['currency'] for c in definition['categories'] for r in rewards(c) + c['unlock_offers']}
    return text + 'Available: ' + ', '.join(
        f"{snapshot['balances'].get(c, 0):,} {CURRENCY_NAMES.get(c, c)}" for c in sorted(currencies))


def page_choices(definition: dict) -> list:
    """The Page choice items: '1 of 40: Bonus: Name'."""
    page_list = pages(definition)
    return [f'{i + 1} of {len(page_list)}: ' + ('Bonus: ' if c.get('group') == 'Bonus' else '') + c['name']
            for i, (c, p) in enumerate(page_list)]


def reward_labels(definition: dict, category: dict, page: dict, snapshot: Optional[dict], metadata: dict) -> list:
    return [display_name(r, metadata) + ', ' + reward_status(definition, category, page, r, snapshot)
            for r in page['rewards']]


def reward_details(definition: dict, category: dict, page: dict, reward: Optional[dict],
                   snapshot: Optional[dict], metadata: dict) -> str:
    if not reward:
        return ''
    state = snapshot['passes'][definition['key']] if snapshot else None
    meta = metadata.get(reward.get('item_id', ''), {})
    cosmetic_set = meta.get('set') or ''
    if isinstance(cosmetic_set, dict):
        cosmetic_set = cosmetic_set.get('value') or cosmetic_set.get('text') or ''
    text = display_name(reward, metadata) + '\n' + (reward.get('description') or meta.get('description') or 'No description supplied.')
    text += '\nType: ' + (reward.get('item_type') or 'Reward')
    text += '\nPass set: ' + category['name']
    if category.get('group') == 'Bonus':
        text += '\nBonus rewards'
    if category['unlock_offers']:
        unlock_cost = {}
        for offer in category['unlock_offers']:
            if not state or offer['id'] not in state['claimed']:
                unlock_cost[offer['currency']] = unlock_cost.get(offer['currency'], 0) + offer['cost']
        text += '\nSet unlock: ' + (costs_text(unlock_cost) if unlock_cost else 'Already unlocked')
    if category.get('dependent_category'):
        dependency = next((c['name'] for c in definition['categories'] if c['id'] == category['dependent_category']),
                          'another set')
        text += '\nSet prerequisite: ' + dependency + '; Epic checks the unlock requirements.'
    if cosmetic_set:
        text += '\nCosmetic set: ' + cosmetic_set
    text += '\n' + reward_status(definition, category, page, reward, snapshot)
    if reward['kind'] == 'quest':
        text += '\n\n' + pass_quest_details(reward, snapshot.get('quests') if snapshot else None)
    if reward['kind'] == 'reward':
        text += '\n' + ('Free track' if reward['free'] else 'Premium track')
        text += '\nCost: ' + costs_text({reward['currency']: reward['cost']})
        text += '\n' + requirement_text(reward)
        if reward.get('extra_rewards'):
            text += '\nAlso includes: ' + ', '.join(display_name(r, metadata) for r in reward['extra_rewards'])
    return text


def button_states(definition: dict, category: dict, page: dict, reward: Optional[dict],
                  snapshot: Optional[dict], busy: bool) -> dict:
    """Which of the pass buttons can be used, and whether the full set button or its notice shows."""
    state = snapshot['passes'][definition['key']] if snapshot else None
    usable = bool(state and state['active'] and not busy)
    page_only = definition['key'] == 'br' and category['id'] == 'Set_SheerWill'
    quests = snapshot.get('quests') if snapshot else None
    return {
        'reward': usable and bool(reward) and reward['kind'] == 'reward' and reward['id'] not in state['claimed'],
        'page': usable and any(r['kind'] == 'reward' and r['id'] not in state['claimed'] for r in page['rewards']),
        'set': (not page_only and usable and definition['key'] == 'br'
                and any(r['id'] not in state['claimed'] for r in rewards(category))),
        'unlock': usable and any(r['id'] not in state['claimed'] for r in category['unlock_offers']),
        'purchase': usable and not state['purchased'],
        'quests': (not busy and bool(reward) and reward['kind'] == 'quest'
                   and bool(related_templates(reward, quests))),
        'set_visible': not page_only,
        'set_notice': page_only,
    }


def claim_selection(kind: str, category: dict, page: dict, reward: Optional[dict]) -> list:
    """The entries a claim, page, set or unlock action covers."""
    if kind == 'reward':
        return [reward] if reward else []
    if kind == 'page':
        return [r for r in page['rewards'] if r['kind'] == 'reward']
    if kind == 'set':
        return rewards(category)
    if kind == 'unlock':
        return category['unlock_offers']
    return []


def quest_scope(definition: dict, snapshot: Optional[dict], metadata: dict,
                reward: Optional[dict] = None) -> dict:
    """Templates, heading and label for the quests linked to one reward or a whole pass."""
    quest_snapshot = snapshot.get('quests') if snapshot else None
    scope = definition['name'] + ' quests'
    if reward:
        return {'templates': related_templates(reward, quest_snapshot),
                'heading': 'Quests for ' + display_name(reward, metadata), 'label': scope}
    allowed = set()
    for category in definition['categories']:
        for page in category['pages']:
            for entry in page['rewards']:
                if entry['kind'] == 'quest':
                    allowed.update(related_templates(entry, quest_snapshot))
    return {'templates': allowed, 'heading': scope + ' - quests linked to this pass and its rewards.',
            'label': scope}
