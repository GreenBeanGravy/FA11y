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
    assert names[0] == 'Mastery Rewards'
    assert len(names) == len(set(names)) == 23
    assert {'Tails', 'Crash Bandicoot', 'Dumpster Dive', 'Morgana', 'Squibbly'} <= set(names)


@pytest.mark.parametrize('count, reward', [(7, '2 Portable Extractor'), (12, '2 Portable Extractor'),
                                           (8, '3 Extraction Accelerator'), (28, 'Pixel Polli outfit')])
def test_mastery_reward_track_is_listed_with_its_rewards(count, reward):
    quest, _, _ = shown(f'quest_s42_progressiontrack_{count:02d}')
    assert quest['name'] == f'Mastered {count} Sprites'
    assert quest['category'] == 'Sprite Mastery / Mastery Rewards'
    text = details_text(quest)
    assert f'Sprites mastered: Progress not reported; target {count}' in text
    assert f'Rewards: {reward}' in text


def test_mastery_monday_override_bonus_goals_give_portable_extractors():
    for template, target in (('quest_dailychase_br_s42_mm_q01', 1), ('quest_dailychase_br_s42_mm_q03', 3)):
        quest, _, _ = shown(template)
        assert quest['category'] == 'Override Daily Quests / Bonus goals'
        text = details_text(quest)
        assert f'target {target}' in text and 'Rewards: Portable Extractor' in text


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
    d = tmp_path / 'qdd'
    _write(d / 'QuestDisplayData_quest_s42_progressiontrack_03.json', [dict(
        Type='FortQuestDisplayDataAsset', Name='QDD_T3', Package='/QDD/QDD_T3', Properties=dict(
            TemplateId='Quest:quest_s42_progressiontrack_03', Objectives=[dict(ObjectiveId='T3_obj0', Count=3)],
            ExtensionData=[dict(DisplayName=dict(LocalizedString='Mastered 3 Sprite')),
                           dict(bIsVisibleToPlayers=True, bIncludedInCategories=False)]))])
    rows, category, skipped = build(q, s, {'quest:quest_s42_spritemastery_old': dict(name='Sprite Mastery - Elder')}, d)
    track = rows.pop('quest:quest_s42_progressiontrack_03')
    assert track['name'] == 'Mastered 3 Sprites' and track['objectives'][0]['required'] == 3
    assert rows['quest:quest_s42_spritemastery_foo_06']['name'] == 'Sprite Mastery - Bounty Hunter Apple'
    assert rows['quest:quest_s42_spritemastery_foo_06']['objectives'][0]['description'] == 'Extract a Bounty Hunter Apple Sprite'
    assert rows['quest:quest_s42_spritemastery_bar_04']['name'] == 'Sprite Mastery - Gummy Bar'
    assert rows['quest:quest_s42_spritemastery_old']['name'] == 'Sprite Mastery - Elder'
    assert skipped == ['Quest_S42_SpriteMastery_Nope']
    assert [h['name'] for h in category['headers']] == ['Mastery Rewards', 'Apple', 'Bar', 'Elder']
    assert all(not r['hidden'] for r in rows.values())
