"""Quest rewards from the shipped reward data, across quest types, without a window or account."""
import json

import pytest

from lib.utilities.epic_quests import normalize_quest, quest_catalog
from lib.utilities.quest_presentation import details_text, prepare_quests, reward_text, rewards_text


def details(template, contextual=False):
    quest = normalize_quest('id', dict(templateId='Quest:' + template, attributes=dict(quest_state='Active')),
                            quest_catalog(), 100)
    rows, _, _ = prepare_quests([quest], contextual_templates={'quest:' + template} if contextual else None)
    assert rows, template
    return details_text(rows[0])


@pytest.mark.parametrize('template, expected', [
    ('quest_s42_cosmicthunder_repeatable_q01', 'Rewards: 1,000 XP'),                 # Override daily
    ('quest_s42_weekly_w01_q01', 'Rewards: 20,000 XP'),                              # Battle Royale weekly
    ('quest_daily_blastberry_18', 'Rewards: 1,000 XP'),                              # Reload daily
    ('quest_mapmastery_03_jumpbear_q01', 'Rewards: 10,000 XP'),                      # Reload map mastery
    ('quest_mapmastery_03_bonusgoal_q05', 'Rewards: Red Eyes wrap'),                 # map mastery bonus goal
    ('quest_s41_ranked_reload_bonusgoal_02', 'Rewards: Blue Creche back bling'),     # Ranked Reload
    ('quest_figment_milestone_hitweakpoints', 'Rewards: 5,000 XP'),                  # OG milestone
    ('sparksquest_milestone_completesetlist', 'Rewards: 5,000 XP'),                  # Festival
    ('q_juno_nxs_sandbox_daily_build_remodeldryvalley', 'Rewards: 3,000 XP'),        # LEGO daily
    ('quest_cosmohound_vopunchcard_q01', 'Rewards: Hearts of Barkness loading screen'),  # Sidekick
    ('quest_s42_fncsbirthday_bonus_q02', 'Rewards: Cake Crusher pickaxe'),           # Birthday
    ('quest_squareclub_daily_q01', 'Rewards: 1,000 XP'),                             # Ballistic
    ('quest_tofugarden_firstwin', 'Rewards: Victory Wings Bonus Win'),               # Blitz bonus win
    ('quest_ecosystem_dailybonusgoal_01', 'Rewards: 25,000 XP'),                     # any-experience dailies
])
def test_details_name_rewards_for_each_quest_type(template, expected):
    assert expected in details(template).splitlines()


@pytest.mark.parametrize('template, expected', [
    ('quest_s42_story_sheerwill_bonusgoals_cosmetic_q05', 'Rewards: Ordered Geno style for Geno outfit'),
    ('quest_s42_spritemastery_narrowfleamonkey',
     'Rewards: Premium bonus: Tails Sprite Trainer style for Pixel Sprite Trainer back bling'),
    ('quest_junoosiris_rebeltowncenter_interact_l02', 'Rewards: Rebel Farm LEGO build; Oil Bath LEGO decor'),
])
def test_pass_and_town_trackers_name_their_rewards_when_shown(template, expected):
    assert expected in details(template, contextual=True).splitlines()


def test_quests_without_visible_rewards_say_nothing():
    assert 'Rewards' not in details('sparksquest_weekly_granter_01')
    assert rewards_text('quest:no_such_quest') == ''


def test_unlocked_quests_are_named_once():
    text = rewards_text('quest:quest_ranked_loosequest_gauntletunlock')
    assert text.startswith('unlocks 5 quests: Complete Ranked Gauntlet quests, ')
    assert text.count('unlocks') == 1
    assert rewards_text('', [dict(type='quest', name='Defeat the Storm King')]) == 'unlocks the quest Defeat the Storm King'
    assert rewards_text('', [dict(type='quest'), dict(type='quest')]) == 'unlocks 2 quests'


def test_reward_wording():
    assert reward_text(dict(type='xp', quantity=15000)) == '15,000 XP'
    assert reward_text(dict(type='item', name='Yeddy', category='Outfit')) == 'Yeddy outfit'
    assert reward_text(dict(type='item', name='Banner Icon', category='Banner Icon')) == 'Banner Icon'
    assert reward_text(dict(type='item', name='Oil Bath', category='LEGO decor')) == 'Oil Bath LEGO decor'
    assert reward_text(dict(type='item', name='Extraction Accelerator', category='', quantity=3)) == '3 Extraction Accelerator'
    assert reward_text(dict(type='resource', name='Sprite Dust', quantity=5000)) == '5,000 Sprite Dust'
    # A style tagged with its cosmetic's own type still reads as a style.
    assert reward_text(dict(type='style', name='Ziggy', category='Outfit', cosmetic='Wrixel',
                            cosmetic_category='Outfit')) == 'Ziggy style for Wrixel outfit'
    assert reward_text(dict(type='style', name="Voyager's Bone", category='Emote', cosmetic='The Bark Voyager',
                            cosmetic_category='Companion')) == "Voyager's Bone emote for The Bark Voyager companion"
    assert reward_text(dict(type='premium', requires='Battle Pass', rewards=[dict(type='xp', quantity=1000)])) \
        == 'Battle Pass bonus: 1,000 XP'


def test_reward_data_has_no_raw_asset_names():
    from lib.utilities.quest_presentation import quest_rewards
    rows = quest_rewards()
    assert len(rows) > 600
    for key, rewards in rows.items():
        text = rewards_text(key, rewards)
        assert text, key
        assert not any(tag in text for tag in ('VTID_', 'Athena', 'MagpieReward', 'JBPID', 'Token')), (key, text)


def _write(directory, name, objects):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / (name + '.json')).write_text(json.dumps(objects), encoding='utf-8')


def test_builder_reads_display_rewards_names_and_definition_fallback(tmp_path, monkeypatch):
    from tools import build_quest_rewards as builder
    monkeypatch.setattr(builder, 'catalog_rows', lambda: {
        'quest:quest_a': dict(name='Quest A', asset='/P/Quest_A.Quest_A'),
        'quest:quest_b': dict(name='Quest B', asset='/P/Quest_B.Quest_B'),
        'quest:quest_c': dict(name='Quest C', asset='/P/Quest_C.Quest_C')})
    display, items = tmp_path / 'display', tmp_path / 'items'
    asset = lambda kind, name: dict(PrimaryAssetType=dict(Name=kind), PrimaryAssetName=name)
    _write(display, 'QuestDisplayData_quest_a', [dict(Type='FortQuestDisplayDataAsset', Name='QDD_A', Properties=dict(
        TemplateId='Quest:quest_a', ExtensionData=[dict(RewardInfo=dict(
            StandardRewards=[dict(ItemPrimaryAssetId=asset('AccountResource', 'AthenaSeasonalXP'), Quantity=15000),
                             dict(ItemPrimaryAssetId=asset('AthenaCharacter', 'Character_Test'), Quantity=1),
                             dict(ItemPrimaryAssetId=asset('CosmeticVariantToken', 'VTID_Old'), Quantity=1),
                             dict(ItemPrimaryAssetId=asset('Quest', 'Quest_B'), Quantity=1),
                             dict(ItemPrimaryAssetId=asset('Token', 'Some_Token'), Quantity=1)],
            HiddenRewards=[dict(TemplateId='CosmeticVariantToken:VTID_Secret', Quantity=1)],
            PremiumRewards=[dict(Rewards=[dict(ItemPrimaryAssetId=asset('AthenaDance', 'Spray_Test'), Quantity=1)],
                                 RequiredTokenId=asset('Token', 'BattlePassS42_SeasonPass_PremiumToken'))]))]))])
    name = lambda text: dict(LocalizedString=text)
    _write(items, 'Character_Test', [dict(Type='AthenaCharacterItemDefinition', Name='Character_Test',
                                          Properties=dict(ItemName=name('Yeddy'), ItemShortDescription=name('Outfit')))])
    _write(items, 'Spray_Test', [dict(Type='AthenaSprayItemDefinition', Name='Spray_Test',
                                      Properties=dict(ItemName=name('Tag')))])
    _write(items, 'VTID_Old', [dict(Type='ObjectRedirector', Name='VTID_Old',
                                    DestinationObject=dict(ObjectPath='/B/VTID_New.0'))])
    _write(items, 'VTID_New', [dict(Type='FortVariantTokenType', Name='VTID_New', Properties=dict(
        ItemName=name('Gold'), ItemShortDescription=name('Style'),
        cosmetic_item=dict(ObjectPath='/B/Character_Test.0')))])
    _write(items, 'XPTable', [dict(Type='DataTable', Name='XPTable', Rows=dict(
        Daily=dict(ResourceDefinition=dict(AssetPathName='/Game/AthenaSeasonalXP.AthenaSeasonalXP'), Quantity=1000),
        Secret=dict(ResourceDefinition=dict(AssetPathName='/Game/AthenaSeasonalXP.AthenaSeasonalXP'), Quantity=50,
                    bIsVisibleToPlayer=False)))])
    # Quest C has no display record, so its own rewards component is used.
    _write(items, 'Quest_C', [dict(Type='FortQuestDefinitionComponent_Rewards', Name='FortQuestDefinitionComponent_Rewards_0',
        Properties=dict(QuestRewardsArray=[dict(ResourceDataTableRewards=[
            dict(TableRowEntry=dict(DataTable=dict(ObjectPath='/P/XPTable.0'), RowName='Daily')),
            dict(TableRowEntry=dict(DataTable=dict(ObjectPath='/P/XPTable.0'), RowName='Secret'))])])),
        dict(Type='AthenaDailyQuestDefinition', Name='Quest_C', Properties={})])
    data, unresolved, fallback = builder.build(display, [items], 'test')
    # A cosmetic missing from the export is named through the optional lookup, never guessed.
    resolver = builder.RewardResolver(builder.ItemIndex([items]), {}, lambda asset: ('Pixel Polli', 'Outfit'))
    assert rewards_text('', [resolver.item('AthenaCharacter', 'Character_Missing', 1)]) == 'Pixel Polli outfit'
    offline = builder.RewardResolver(builder.ItemIndex([items]), {})
    assert offline.item('AthenaCharacter', 'Character_Missing', 1) is None and offline.unresolved
    assert unresolved == set() and fallback == 1
    assert rewards_text('quest:quest_a', data['rows']['quest:quest_a']) == (
        '15,000 XP; Yeddy outfit; Gold style for Yeddy outfit; Battle Pass bonus: Tag spray; unlocks the quest Quest B')
    assert 'quest:quest_b' not in data['rows']
    assert rewards_text('quest:quest_c', data['rows']['quest:quest_c']) == '1,000 XP'
