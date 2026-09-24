"""Exercise the actual catalog and player text without opening a window."""
from lib.utilities.epic_quests import normalize_quest, quest_catalog
from lib.utilities.quest_presentation import (
    prepare_quests, filter_quests, clean_text, details_text, list_label, list_labels,
    mode_text, group_catalog, natural_key,
)
from lib.managers.quest_announcements import QuestAnnouncements


def row(name, attributes=None):
    return normalize_quest(name, dict(templateId='Quest:' + name,
        attributes=attributes or dict(quest_state='Active')), quest_catalog(), 100)


def test_daily_subclass_definitions_have_real_names_and_targets():
    quests = [row('quest_daily_blastberry_18'), row('q_juno_nxs_daily_punchcard_01'),
              row('sparksquest_dailybass_songmissnotes')]
    rows, hidden, unresolved = prepare_quests(quests)
    assert len(rows) == 3 and hidden == unresolved == 0
    assert rows[0]['name'] == 'Eliminate players with pistols or sniper rifles'
    assert rows[0]['mode'] == 'Fortnite Reload'
    assert 'Bass' in rows[2]['name'] and rows[2]['mode'] == 'Fortnite Festival'
    assert all(q['objectives'][0]['required'] is not None for q in rows)


def test_builder_accepts_daily_class_and_q_filename(tmp_path):
    import json
    from tools.build_quest_catalog import build
    asset = [dict(Type='AthenaDailyQuestDefinition', Name='Q_Test', Package='/Test/Q_Test',
                  Properties=dict(ItemName=dict(LocalizedString='Build a cabin'), Objectives=[]))]
    (tmp_path / 'Game_Q_Test.uasset.json').write_text(json.dumps(asset))
    assert build(tmp_path)['rows']['quest:q_test']['name'] == 'Build a cabin'


def test_localized_week_and_mode_filter_with_real_progress():
    quest = row('quest_s42_weekly_w02_q05', dict(quest_state='Active', completion_Quest_S42_Weekly_W02_Q05_obj0=5))
    rows, _, _ = prepare_quests([quest, row('quest_daily_blastberry_18')])
    filtered = filter_quests(rows, mode='Battle Royale', query='Week 2')
    assert len(filtered) == 1
    assert filtered[0]['category'].endswith('/ Week 2')
    label = list_label(filtered[0])
    assert '5 of 10' in label and 'QuestCategory' not in label
    assert filter_quests(rows, mode='Fortnite Reload', query='Week 2') == []


def test_hidden_records_and_unknown_templates_never_become_raw_titles():
    hidden = row('quest_s42_crownspriteprogression_00_complete_cheatmaster')
    unknown = row('no_export_available')
    rows, excluded, unresolved = prepare_quests([hidden, unknown])
    assert rows == [] and excluded == 1 and unresolved == 1


def test_sidekick_names_and_story_headers_come_from_category_assets():
    from lib.utilities.quest_presentation import category_text
    groups = group_catalog()
    assert 'Ice Prince' in category_text(['QuestCategory.Mimosa.BriskImp'], groups)
    story = category_text(['QuestCategory.BR.S42.Story.SheerWill.P01'], groups)
    assert 'Geno: The Ultimate Reality' in story and 'SheerWill' not in story


def test_excluded_products_are_not_listed_as_compatible():
    groups = group_catalog()
    # NONE(Product.BR) is not evidence that this quest belongs in BR.
    metadata = dict(product_query=dict(TagDictionary=[dict(TagName='Product.BR')], QueryTokenStream=[0, 1, 3, 1, 0]))
    assert mode_text([], metadata, groups) == 'Mode not identified'


def test_rich_text_missing_count_expiry_and_duplicate_labels():
    assert clean_text('<img id="MapMasteryTier1"/> <b>Search</>\u2009containers &amp; chests') == 'Search containers & chests'
    quests, _, _ = prepare_quests([row('quest_s42_weekly_w02_q05')])
    quest = quests[0]
    quest['expiry'] = '0001-01-01T00:00:00Z'
    details = details_text(quest)
    assert 'target 10' in details and '0 of 10' not in details and 'Expires:' not in details
    assert list_labels([quest, dict(quest, id='second')])[0].endswith('Separate quest 1 of 2')
    quest['expired'] = True
    assert filter_quests([quest]) == []
    assert filter_quests([quest], expired=True) == [quest]


def test_natural_week_sort():
    assert sorted(['Week 10', 'Week 2', 'Week 1'], key=natural_key) == ['Week 1', 'Week 2', 'Week 10']


def test_festival_daily_announcements_are_not_rejected_by_template_prefix():
    quest = row('sparksquest_dailybass_songmissnotes')
    announcements = QuestAnnouncements()
    assert announcements.feed_api(dict(quests=[quest])) == []
    quest['state'] = 'Completed'
    assert announcements.feed_api(dict(quests=[quest])) == ['Quest complete. On Bass, miss fewer than 75 notes in a song.']


def test_birthday_shared_modes_keep_separate_account_instances_and_categories():
    names = ['quest_s42_fncsbirthday_03', 'quest_s42_championsroad_26_elim_01',
             'quest_s42_fncsbirthday_bonus_q01']
    quests, _, unresolved = prepare_quests([row(name) for name in names])
    assert unresolved == 0 and len(quests) == 3
    assert len(filter_quests(quests, mode='Battle Royale')) == 3
    assert len(filter_quests(quests, mode='Fortnite OG')) == 3
    assert len({q['category'] for q in quests}) == 3
    duplicates = [quests[0], dict(quests[0], id='different-instance')]
    assert len(filter_quests(duplicates, mode='Battle Royale')) == 2


def test_daily_and_override_lists_are_separate_and_inactive_never_listed():
    quests, hidden, _ = prepare_quests([
        row('quest_daily_elim_br'), row('quest_s42_cosmicthunder_repeatable_q01'),
        row('quest_daily_place_br', dict(quest_state='Inactive'))])
    assert hidden == 1
    assert {q['category'] for q in quests} == {'Daily Quests', 'Override Daily Quests'}
    assert len(filter_quests(quests, mode='Battle Royale', status='All')) == 2


def test_birthday_location_progress_uses_eight_required_not_thirteen_options():
    from lib.utilities.quest_presentation import completion_summary
    attributes = dict(quest_state='Active')
    attributes.update({f'completion_quest_s42_fncsbirthday_08_obj{i}': int(i < 3) for i in range(13)})
    quests, _, _ = prepare_quests([row('quest_s42_fncsbirthday_08', attributes)])
    assert completion_summary(quests[0]) == '3 of 8 objectives completed'
    assert '3 of 8' in list_label(quests[0])
    quests[0]['objectives'][5]['achieved'] = None
    assert completion_summary(quests[0]).startswith('At least 3 of 8')


def test_fractional_progress_is_not_rounded_to_completed():
    from lib.utilities.quest_presentation import objective_progress
    assert objective_progress(dict(achieved=0.75, required=1)) == '0.75 of 1'
    assert objective_progress(dict(achieved=999999.9, required=1000000)) == '999,999.9 of 1,000,000'


def test_exclusion_query_does_not_add_br_to_another_mode():
    from lib.utilities.quest_presentation import compatible_modes
    metadata = dict(product_query=dict(TagDictionary=[dict(TagName='Product.BR')], QueryTokenStream=[0, 1, 3, 1, 0]))
    assert 'Battle Royale' not in compatible_modes([], metadata, group_catalog())


def test_geno_reward_trackers_have_actual_cosmetic_names_and_unknown_progress():
    from lib.utilities.epic_quests import normalize_quest,quest_catalog
    from lib.utilities.quest_presentation import pass_reward_names,prepare_quests,list_labels,details_text
    templates={key for key in pass_reward_names() if 'sheerwill' in key}
    assert len(templates)==7
    quests=[normalize_quest(str(i),dict(templateId=t,attributes={'quest_state':'Active'}),quest_catalog(),100) for i,t in enumerate(sorted(templates))]
    rows,_,_=prepare_quests(quests,contextual_templates=templates)
    labels=list_labels(rows,True)
    assert len(labels)==len(set(labels))==7
    assert any('Ordered Conduits of Power reward' in label for label in labels)
    assert all('Unlock progress unavailable' in label for label in labels)
    assert not any('Selected pass reward quest' in label or 'Separate quest' in label or 'target 1' in label for label in labels)
    assert 'not a playable quest' in details_text(rows[0])
    quests[0]['state']='Claimed'
    rows,_,_=prepare_quests(quests,contextual_templates=templates)
    assert any('Reward claimed' in label for label in list_labels(rows))
