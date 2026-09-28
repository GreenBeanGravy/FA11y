"""Sprite Mastery tiers: named from the sprite each objective tracks, shown in their own category."""
import json

import pytest

from lib.utilities.epic_quests import normalize_quest, quest_catalog
from lib.utilities.quest_presentation import details_text, prepare_quests


def shown(template, state='Active'):
    quest = normalize_quest('id', dict(templateId='Quest:' + template, attributes=dict(quest_state=state)),
                            quest_catalog(), 100)
    rows, hidden, unresolved = prepare_quests([quest])
    return rows[0] if rows else None, hidden, unresolved


@pytest.mark.parametrize('template, name', [
    ('quest_s42_spritemastery_8bit', 'Sprite Mastery - 8-Bit'),
    ('quest_s42_spritemastery_8bit_01', 'Sprite Mastery - Cheat Master 8-Bit'),
    ('quest_s42_spritemastery_doublejump_02', 'Sprite Mastery - Gold Jackrabbit'),
    ('quest_s42_spritemastery_birthday_03', 'Sprite Mastery - Loot Hacker Birthday'),
    ('quest_s42_spritemastery_bodyslam_04', 'Sprite Mastery - Gummy Crash Bandicoot'),
    ('quest_s42_spritemastery_8bit_05', 'Sprite Mastery - Holofoil 8-Bit'),
    ('quest_s42_spritemastery_squibbly_06', 'Sprite Mastery - Bounty Hunter Squibbly'),
    ('quest_s42_spritemastery_winnerd', 'Sprite Mastery - Dumpster Dive'),
    ('quest_s42_spritemastery_increaseheals_01', 'Sprite Mastery - Cheat Master Morgana'),
    ('quest_s42_spritemastery_winnerc', 'Sprite Mastery - Onigiri'),  # was "[Community Winner 3]"
])
def test_every_tier_is_named_and_listed(template, name):
    quest, _, _ = shown(template)
    assert quest['name'] == name
    assert quest['mode'] == 'Battle Royale'
    # The heading is the sprite itself ("Gummy Crash Bandicoot" -> "Crash Bandicoot").
    title, sprite = quest['category'].split(' / ')
    assert title == 'Sprite Mastery' and name.endswith(' ' + sprite) or name == 'Sprite Mastery - ' + sprite


def test_details_say_which_sprite_to_extract():
    quest, _, _ = shown('quest_s42_spritemastery_winnerc_06')
    text = details_text(quest)
    assert 'Category: Sprite Mastery / Onigiri' in text
    assert 'Extract a Bounty Hunter Onigiri Sprite: Progress not reported; target 1' in text
    quest, _, _ = shown('quest_s42_spritemastery_8bit_05')
    assert 'Extract a Holofoil 8-Bit Sprite to master it.' in details_text(quest)


def test_one_category_heading_per_sprite():
    from lib.utilities.quest_presentation import group_catalog
    category = next(c for c in group_catalog()['categories'] if c['name'] == 'Sprite Mastery')
    names = [h['name'] for h in category['headers']]
    assert len(names) == len(set(names)) == 22
    assert {'Tails', 'Crash Bandicoot', 'Dumpster Dive', 'Morgana', 'Squibbly'} <= set(names)


def test_sprites_without_a_name_in_the_build_are_not_invented():
    for template in ('quest_s42_spritemastery_cloakondamage_03', 'quest_s42_spritemastery_elimdropheals_05',
                     'quest_s42_spritemastery_consumableoverdrive'):
        assert shown(template)[0] is None, template


def _write(path, objects):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(objects), encoding='utf-8')


def test_builder_names_from_the_tracked_sprite_tag(tmp_path):
    from tools.build_sprite_mastery_quests import build
    def quest(name, tag):
        return [dict(Type='FortQuestItemDefinition_Athena', Name=name, Package='/P/' + name, Properties=dict(
            Objectives=[dict(BackendName=name + '_obj0', Count=1, ObjectiveFilters=[dict(Item=dict(TagQuery=dict(
                TagDictionary=[dict(TagName=tag)])))])]))]
    def sprite(name, title):
        return [dict(Type='ExtractableSpriteDefinition', Name=name, Properties=dict(ItemName=dict(LocalizedString=title)))]
    q, s = tmp_path / 'quests', tmp_path / 'sprites'
    _write(q / 'Quest_S42_SpriteMastery_Foo_06.json', quest('Quest_S42_SpriteMastery_Foo_06', 'Sprites.Extractable.Foo.Reaper'))
    _write(q / 'Quest_S42_SpriteMastery_Bar_04.json', quest('Quest_S42_SpriteMastery_Bar_04', 'Sprites.Extractable.Bar.Candy'))
    _write(q / 'Quest_S42_SpriteMastery_Old.json', quest('Quest_S42_SpriteMastery_Old', 'Sprites.Extractable.Old.Base'))
    _write(q / 'Quest_S42_SpriteMastery_Nope.json', quest('Quest_S42_SpriteMastery_Nope', 'Sprites.Extractable.Nope.Base'))
    # Only a variant definition exists for Foo; its prefix is stripped to recover the sprite name.
    _write(s / 'ESD_FooSprite_Variant_CheatMaster.json', sprite('ESD_FooSprite_Variant_CheatMaster', 'Cheat Master Apple Sprite'))
    _write(s / 'ESD_BarSprite.json', sprite('ESD_BarSprite', 'Bar Sprite'))
    rows, category, skipped = build(q, s, {'quest:quest_s42_spritemastery_old': dict(name='Sprite Mastery - Elder')})
    assert rows['quest:quest_s42_spritemastery_foo_06']['name'] == 'Sprite Mastery - Bounty Hunter Apple'
    assert rows['quest:quest_s42_spritemastery_foo_06']['objectives'][0]['description'] == 'Extract a Bounty Hunter Apple Sprite'
    assert rows['quest:quest_s42_spritemastery_bar_04']['name'] == 'Sprite Mastery - Gummy Bar'
    assert rows['quest:quest_s42_spritemastery_old']['name'] == 'Sprite Mastery - Elder'
    assert skipped == ['Quest_S42_SpriteMastery_Nope']
    assert [h['name'] for h in category['headers']] == ['Apple', 'Bar', 'Elder']
    assert all(not r['hidden'] for r in rows.values())
