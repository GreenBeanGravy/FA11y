from lib.utilities.horde_ranks import rank_catalog, rank_text

def test_current_rank_effect_level_is_not_mistaken_for_rank_number():
    rank=rank_catalog()[2]
    assert rank['effect_level']==2
    assert rank['exact_values']['MaxHealth']==15 and rank['exact_values']['Shield']==15
    assert rank['exact_values']['DiceCritChance']==.025
    assert rank['exact_values']['MonsterPartsTotal']==80 and rank['exact_values']['MonsterPartsThisRank']==40
    assert 'Maximum health bonus: 15.' in rank_text()

def test_exact_starting_ammo_reports_disabled_grant_separately_from_defined_amounts():
    rank=rank_catalog()[3]
    assert '75 medium' in rank['exact_description'] and '2 rockets' in rank['exact_description']
    assert 'disabled in the installed game data' in rank['exact_description']
