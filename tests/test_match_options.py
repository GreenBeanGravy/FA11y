from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image
from lib.detection import match_options as options

FIXTURES=Path(__file__).parent/'fixtures'/'match_options'
EXPECTED=[
 ('original','Zero Build',False,'Solo',None,('Solo','Duos','Trios','Squads')),
 ('duo_fill','Zero Build',False,'Duos',True,('Solo','Duos','Trios','Squads')),
 ('duo_no_fill','Zero Build',False,'Duos',False,('Solo','Duos','Trios','Squads')),
 ('ranked_zero','Zero Build',True,'Duos',None,('Solo','Duos')),
 ('ranked_build','Build',True,'Duos',None,('Solo','Duos','Trios')),
 ('ranked_trio','Build',True,'Trios',None,('Solo','Duos','Trios')),
 ('unranked_build','Build',False,'Trios',False,('Solo','Duos','Trios','Squads')),
 ('squad_build','Build',False,'Squads',False,('Solo','Duos','Trios','Squads')),
 ('squad_fill','Build',False,'Squads',True,('Solo','Duos','Trios','Squads')),
]


@pytest.mark.parametrize('name,build,ranked,team,fill,teams',EXPECTED)
def test_observed_br_states(name,build,ranked,team,fill,teams):
    result,scale=options.read_image(Image.open(FIXTURES/(name+'.png')))
    assert result==options.MatchOptions('battle_royale',build,ranked,team,fill,teams)
    assert scale==(1.,1.)


def test_unmapped_screen_and_aspect_ratio_fail_closed():
    for image in [Image.new('RGB',(1920,1080)),Image.new('RGB',(1280,1024))]:
        with pytest.raises(options.OptionsUnavailable): options.read_image(image)


def test_controls_reject_locked_fill_and_disabled_team():
    current=options.read_image(Image.open(FIXTURES/'ranked_zero.png'))[0]
    profile=options.PROFILES[0]
    for field,value in [('fill',True),('team','Trios'),('ranked','yes'),('build','Reload')]:
        with pytest.raises(options.OptionsUnavailable): profile.target(current,field,value)


def setup_apply(monkeypatch):
    from lib.utilities import mouse
    current=options.read_image(Image.open(FIXTURES/'original.png'))[0]
    click=Mock()
    monkeypatch.setattr(mouse,'instant_click',click)
    monkeypatch.setattr(options,'require_fortnite',lambda:None)
    monkeypatch.setattr(options,'focus_and_read',lambda:current)
    monkeypatch.setattr(options.time,'sleep',lambda _:None)
    ticks=iter(range(20))
    monkeypatch.setattr(options.time,'monotonic',lambda:next(ticks))
    return current,click


def test_changed_screen_refuses_stale_request(monkeypatch):
    current,click=setup_apply(monkeypatch)
    with pytest.raises(options.OptionsUnavailable,match='changed since'):
        options.apply_option(replace(current,ranked=True),'team','Duos')
    click.assert_not_called()


def test_applies_once_and_verifies_stable_readback(monkeypatch):
    current,click=setup_apply(monkeypatch)
    updated=replace(current,team='Duos',fill=True)
    frames=iter([current,current,updated,updated])
    monkeypatch.setattr(options,'capture',lambda:(next(frames), (1.,1.)))
    assert options.apply_option(current,'team','Duos')==updated
    click.assert_called_once_with(1589,380)


def test_failed_readback_does_not_repeat_toggle(monkeypatch):
    current,click=setup_apply(monkeypatch)
    monkeypatch.setattr(options,'capture',lambda:(current,(1.,1.)))
    with pytest.raises(options.OptionsUnavailable,match='did not confirm'):
        options.apply_option(current,'ranked',True)
    click.assert_called_once_with(1688,254)


def test_noop_does_not_toggle(monkeypatch):
    current,click=setup_apply(monkeypatch)
    assert options.apply_option(current,'ranked',False)==current
    click.assert_not_called()


def test_hotkey_and_gui_input_guard_are_wired():
    root=Path(__file__).resolve().parents[1]
    main=(root/'FA11y.py').read_text(encoding='utf-8')
    defaults=(root/'lib/utilities/utilities.py').read_text(encoding='utf-8')
    assert "'open match options': open_match_options" in main
    assert '"FA11y Match Options"' in main
    assert '_app_state.match_options_busy.is_set()' in main
    assert 'Open Match Options = lalt+o ' in defaults


MODE_STATES = [
 ('og_solo','fortnite_og','Zero Build',None,'Solo',None),
 ('og_duo_fill','fortnite_og','Zero Build',None,'Duos',True),
 ('og_duo_no_fill','fortnite_og','Zero Build',None,'Duos',False),
 ('og_build','fortnite_og','Build',None,'Duos',False),
 ('og_squad','fortnite_og','Build',None,'Squads',False),
 ('reload_squad','reload','Build',False,'Squads',False),
 ('reload_ranked_squad','reload','Build',True,'Squads',None),
 ('reload_ranked_zero','reload','Zero Build',True,'Squads',None),
 ('reload_ranked_solo','reload','Zero Build',True,'Solo',None),
 ('reload_ranked_duo','reload','Zero Build',True,'Duos',None),
 ('reload_duo_no_fill','reload','Zero Build',False,'Duos',False),
 ('reload_duo_fill','reload','Zero Build',False,'Duos',True),
 ('blitz_duo_fill','blitz',None,None,'Duos',True),
 ('blitz_six','blitz',None,None,'Six Stack',True),
 ('blitz_squad','blitz',None,None,'Squads',True),
 ('blitz_no_fill','blitz',None,None,'Squads',False),
 ('blitz_solo','blitz',None,None,'Solo',None),
]


@pytest.mark.parametrize('name,mode,build,ranked,team,fill',MODE_STATES)
def test_observed_mode_states(name,mode,build,ranked,team,fill):
    result,_=options.read_image(Image.open(FIXTURES/(name+'.png')))
    teams=('Solo','Duos','Squads','Six Stack') if mode=='blitz' else ('Solo','Duos','Squads')
    assert result==options.MatchOptions(mode,build,ranked,team,fill,teams)
    if ranked is None:
        assert 'Unranked' not in result.summary()
    assert 'None' not in result.summary()


@pytest.mark.parametrize('fixture,field,value',[
 ('og_solo','ranked',True),('og_solo','team','Trios'),
 ('blitz_six','ranked',True),('blitz_six','build','Build'),
 ('reload_squad','team','Trios'),
])
def test_mode_specific_unsupported_controls(fixture,field,value):
    current,_=options.read_image(Image.open(FIXTURES/(fixture+'.png')))
    profile=next(p for p in options.PROFILES if p.key==current.mode)
    with pytest.raises(options.OptionsUnavailable):profile.target(current,field,value)


def test_mode_specific_click_coordinates():
    for fixture,field,value,point in [
        ('og_solo','team','Duos',(1671,252)),
        ('og_duo_fill','fill',False,(1688,378)),
        ('reload_squad','team','Solo',(1589,380)),
        ('blitz_duo_fill','team','Six Stack',(1753,128)),
        ('blitz_duo_fill','fill',False,(1688,254)),
    ]:
        current,_=options.read_image(Image.open(FIXTURES/(fixture+'.png')))
        profile=next(p for p in options.PROFILES if p.key==current.mode)
        assert profile.target(current,field,value)==point
