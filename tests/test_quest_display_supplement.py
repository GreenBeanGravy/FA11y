"""Live quests added from QuestDisplayData: only enabled ones, with real categories and rewards."""
import json

from lib.utilities.epic_quests import normalize_quest, quest_catalog
from lib.utilities.quest_presentation import details_text, group_catalog, prepare_quests


def shown(template):
    quest = normalize_quest('id', dict(templateId='Quest:' + template, attributes=dict(quest_state='Active')),
                            quest_catalog(), 100)
    rows, hidden, unresolved = prepare_quests([quest])
    return rows[0] if rows else None, hidden, unresolved


def test_reload_map_mastery_tier_released_later_has_its_category_and_reward():
    quest, _, _ = shown('quest_mapmastery_03_punchberry_q02')
    assert quest['mode'] == 'Fortnite Reload'
    assert quest['category'] == 'Map Mastery / Oasis Mastery'
    text = details_text(quest)
    assert '[Tier 2 of 4] Reach Top 10 players in Oasis: Progress not reported; target 10' in text
    assert 'Rewards: 10,000 XP' in text


def test_later_weeks_and_questlines_use_current_category_headers():
    assert shown('quest_s42_weekly_w05_q03')[0]['category'] == 'This Week / Week 5'
    sonic = shown('quest_s42_narrowflea_q02')[0]
    assert sonic['name'] == 'Defeat Dr. Eggman' and sonic['category'] == 'Gotta Go Fast!'
    assert shown('quest_figment_s10_weekly_w04_q01')[0]['category'] == 'Weekly / Week 4'


def test_daily_pool_quests_are_covered_before_they_are_drawn():
    for template, mode in [('quest_daily_blastberry_04', 'Fortnite Reload'),
                           ('sparksquest_dailydrums_playnotes', 'Fortnite Festival'),
                           ('q_juno_nxs_survival_daily_craft_dynamite', 'LEGO Fortnite')]:
        quest, _, _ = shown(template)
        assert quest and quest['mode'] == mode and 'Rewards: ' in details_text(quest), template


def test_game_disabled_and_placeholder_quests_were_not_added():
    catalog = quest_catalog()
    # Sprite Mastery tiers are hidden by the game itself; Epic ships "Quest Name" placeholders.
    assert 'quest:quest_s42_spritemastery_8bit_05' not in catalog
    assert 'quest:quest_sparksspotlight_s15_event03_q01' not in catalog
    assert shown('quest_s42_spritemastery_8bit_05') == (None, 0, 1)


def test_newer_category_copy_replaces_the_older_one():
    groups = group_catalog()
    assets = [c['asset'] for c in groups['categories']]
    assert len(assets) == len(set(assets))
    weekly = [c for c in groups['categories'] if 'QuestCategory.BR.Daily' in c['tags']]
    assert any(h['name'] == 'Week 6' for c in weekly for h in c['headers'])


def _write(path, objects):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(objects), encoding='utf-8')


def _record(template, name, tags, quest_type='EFortQuestType::AthenaChallengeBundleQuest', visible=True):
    return [dict(Type='FortQuestDisplayDataAsset', Name='QDD_' + template, Package='/QDD/P/QDD_' + template,
                 Properties=dict(TemplateId='Quest:' + template, OwnedGameplayTags=tags,
                                 Objectives=[dict(ObjectiveId=template + '_obj0', Count=3,
                                                  Description=dict(LocalizedString=name))],
                                 ExtensionData=[dict(DisplayName=dict(LocalizedString=name), QuestType=quest_type,
                                                     SortPriority=1),
                                                dict(bIsVisibleToPlayers=visible, bIncludedInCategories=visible,
                                                     QuestVisiblityData={})]))]


def test_builder_rules(tmp_path):
    from tools.build_quest_display_supplement import build, merge
    daily, other = 'EFortQuestType::AthenaDailyQuest', 'EFortQuestType::AthenaChallengeBundleQuest'
    qdd = tmp_path / 'qdd'
    _write(qdd / 'Pool/QuestDisplayData_d1.json', _record('d1', 'Daily one', ['QuestCategory.X.Dailies'], daily))
    _write(qdd / 'Pool/QuestDisplayData_d2.json', _record('d2', 'Daily two', ['QuestCategory.X.Dailies'], daily))
    _write(qdd / 'OldSeason/QuestDisplayData_d3.json', _record('d3', 'Old daily', ['QuestCategory.X.Dailies'], daily))
    _write(qdd / 'Pool/QuestDisplayData_w1.json', _record('w1', 'Weekly one', ['QuestCategory.X.Weekly'], other))
    _write(qdd / 'Pool/QuestDisplayData_w2.json', _record('w2', 'Weekly two', ['QuestCategory.X.Weekly'], other))
    _write(qdd / 'Pool/QuestDisplayData_h1.json', _record('h1', 'Hidden', ['QuestCategory.X.Weekly'], other, visible=False))
    _write(qdd / 'Pool/QuestDisplayData_p1.json', _record('p1', 'Quest Name', ['QuestCategory.X.Weekly'], other))
    _write(tmp_path / 'qc/QC_X.json', [dict(Type='QuestCategoryData', Package='/QC/QC_X', Properties=dict(
        DisplayName=dict(LocalizedString='X Quests'), IncludeTags=['QuestCategory.X'],
        AdditionalHeaders=[dict(HeaderName=dict(LocalizedString='Week 9'), HeaderTag=dict(TagName='QuestCategory.X.Weekly'))]))])
    supplement = dict(rows={}, categories=[dict(asset='/QC/QC_X', name='Old', tags=[], exclude=[], headers=[])])
    added, categories, _ = build(qdd, tmp_path / 'qc', ['Quest:d1', 'Quest:w1', 'Quest:h1', 'Quest:p1'], {}, supplement)
    # Active + enabled, plus the same-plugin daily pool; not the old season, other weeks, hidden or placeholders.
    assert sorted(added) == ['quest:d1', 'quest:d2', 'quest:w1']
    assert added['quest:w1']['objectives'][0] == dict(key='w1_obj0', required=3, description='Weekly one',
                                                      hidden=False, stage=-1)
    merged = merge(supplement, added, categories, [], 'test')
    assert [c['name'] for c in merged['categories']] == ['X Quests']
