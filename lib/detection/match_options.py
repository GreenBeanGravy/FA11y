"""Screen-backed match-option profiles. Only verified mode profiles are enabled."""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import time

import cv2
import numpy as np
from PIL import ImageGrab

ASSETS = Path(__file__).resolve().parents[2] / 'assets' / 'match_options'


class OptionsUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class MatchOptions:
    mode: str
    build: str | None
    ranked: bool | None
    team: str
    fill: object  # None means Fortnite has locked this control.
    teams: tuple

    @property
    def mode_name(self):
        return next(p.name for p in PROFILES if p.key == self.mode)

    def summary(self):
        fill = 'Team fill locked' if self.fill is None else ('Fill' if self.fill else 'No fill')
        parts = [self.build] if self.build is not None else []
        if self.ranked is not None:
            parts.append("Ranked" if self.ranked else "Unranked")
        return ", ".join(parts + [self.team, fill]) + "."


@lru_cache(maxsize=64)
def template(profile, name):
    result = cv2.imread(str(ASSETS / profile / (name + '.png')), cv2.IMREAD_GRAYSCALE)
    if result is None:
        raise OptionsUnavailable('Missing match-options reference: ' + name)
    return result


def score(gray, profile, name, box):
    x1,y1,x2,y2 = box
    return float(cv2.matchTemplate(gray[y1:y2,x1:x2], template(profile,name), cv2.TM_CCOEFF_NORMED)[0,0])


class BattleRoyaleProfile:
    key = 'battle_royale'
    name = 'Battle Royale'
    builds = {'Build': (1336,128), 'Zero Build': (1640,128)}
    teams = {'Solo': (1507,380), 'Duos': (1589,380), 'Trios': (1671,380), 'Squads': (1753,380)}
    controls = {'ranked': (1688,254), 'fill': (1688,505)}

    title_box = (100,887,356,999)
    labels_box = (1190,232,1305,248)
    rank_box = (1189,253,1260,281)
    fill_box = (1189,508,1310,531)

    def matches(self, gray):
        return (score(gray,self.key,'title',self.title_box) > .85
                and score(gray,self.key,'labels',self.labels_box) > .85)

    @staticmethod
    def highlighted(rgb, x1, x2, y1, y2):
        strip = rgb[y1:y2,x1:x2]
        # Selection underlines are yellow in unranked and pale/white in ranked.
        light = (strip[:,:,0] > 170) & (strip[:,:,1] > 170)
        return float(light.mean()) > .20

    def read(self, rgb, gray):
        builds = [name for name,(x,_) in self.builds.items()
                  if self.highlighted(rgb,x-120,x+120,153,160)]
        teams = [name for name,(x,y) in self.teams.items()
                 if self.highlighted(rgb,x-27,x+27,y+26,y+33)]
        if (self.builds and len(builds)!=1) or len(teams)!=1:
            raise OptionsUnavailable('Could not read the selected build mode or team size. Use Refresh.')
        ranked = (self._label(gray, [('rank_off',False),('rank_on',True)],self.rank_box)
                  if self.rank_box is not None else None)
        fill = self._label(gray, [('fill_locked',None),('fill_on',True),('fill_off',False)],self.fill_box)
        enabled = []
        for name,(x,y) in self.teams.items():
            icon = rgb[y-15:y+17,x-24:x+24]
            if name==teams[0] or np.count_nonzero(np.all(icon > 200,axis=2)) >= 20:
                enabled.append(name)
        return MatchOptions(self.key,builds[0] if builds else None,ranked,teams[0],fill,tuple(enabled))

    def _label(self,gray,choices,box):
        matches = sorted([(score(gray,self.key,name,box),i,value) for i,(name,value) in enumerate(choices)],reverse=True)
        if matches[0][0] < .80 or matches[0][0]-matches[1][0] < .08:
            raise OptionsUnavailable('Match options are changing or unreadable. Use Refresh.')
        return matches[0][2]

    def target(self,current,field,value):
        if field=='build' and value in self.builds:
            return self.builds[value]
        if field=='team' and value in current.teams:
            return self.teams[value]
        if field=='ranked' and type(value) is bool and current.ranked is not None:
            return self.controls[field]
        if field=='fill' and type(value) is bool and current.fill is not None:
            return self.controls[field]
        raise OptionsUnavailable('That option is disabled or unsupported in the current mode.')


class ReloadProfile(BattleRoyaleProfile):
    key = 'reload'
    name = 'Reload'
    title_box = (105,690,390,755)
    teams = {'Solo': (1589,380), 'Duos': (1671,380), 'Squads': (1753,380)}


class FortniteOGProfile(BattleRoyaleProfile):
    key = 'fortnite_og'
    name = 'Fortnite OG'
    title_box = (110,834,277,967)
    labels_box = (1190,230,1315,248)
    rank_box = None
    teams = {'Solo': (1589,252), 'Duos': (1671,252), 'Squads': (1753,252)}
    controls = {'fill': (1688,378)}
    fill_box = (1189,380,1310,403)


class BlitzProfile(BattleRoyaleProfile):
    key = 'blitz'
    name = 'Blitz Royale'
    title_box = (105,690,433,755)
    labels_box = (1190,106,1315,124)
    rank_box = None
    builds = {}
    teams = {'Solo': (1507,128), 'Duos': (1589,128),
             'Squads': (1671,128), 'Six Stack': (1753,128)}
    controls = {'fill': (1688,254)}
    fill_box = (1189,256,1310,279)


PROFILES = (BattleRoyaleProfile(), ReloadProfile(), FortniteOGProfile(), BlitzProfile())


def read_image(image):
    image = image.convert('RGB')
    width,height=image.size
    if abs(width/height-16/9) > .02:
        raise OptionsUnavailable('Match options currently require a fullscreen 16 by 9 display.')
    rgb = np.asarray(image.resize((1920,1080)))
    gray = cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
    profiles=[profile for profile in PROFILES if profile.matches(gray)]
    if len(profiles)!=1:
        raise OptionsUnavailable('Open match options for Battle Royale, Reload, Fortnite OG, or Blitz Royale first. This screen has not been mapped.')
    return profiles[0].read(rgb,gray), (width/1920,height/1080)


def require_fortnite():
    from lib.utilities.window_utils import get_active_window_title
    if get_active_window_title().strip().lower()!='fortnite':
        raise OptionsUnavailable('Fortnite lost focus. No further changes were made.')


def capture():
    require_fortnite()
    return read_image(ImageGrab.grab())


def focus_and_read():
    from lib.utilities.window_utils import focus_fortnite
    if not focus_fortnite():
        raise OptionsUnavailable('Could not focus Fortnite.')
    time.sleep(.25)
    return capture()[0]


def apply_option(expected,field,value):
    from lib.utilities.mouse import instant_click
    current=focus_and_read()
    if current != expected:
        raise OptionsUnavailable('Fortnite options changed since they were read. Refresh before changing another setting.')
    profile=next(p for p in PROFILES if p.key==current.mode)
    point=profile.target(current,field,value)
    if getattr(current,field)==value:
        return current
    latest,scale=capture()
    if latest != current:
        raise OptionsUnavailable("Fortnite options changed before the click. Refresh before trying again.")
    require_fortnite()
    instant_click(round(point[0]*scale[0]),round(point[1]*scale[1]))
    deadline=time.monotonic()+4.
    previous=None
    while time.monotonic()<deadline:
        time.sleep(.2)
        try:
            updated,_=capture()
        except OptionsUnavailable:
            require_fortnite()
            continue
        if updated.mode!=expected.mode:
            raise OptionsUnavailable('The game mode changed. Refresh the match options.')
        if getattr(updated,field)==value and updated==previous:
            return updated
        previous=updated
    raise OptionsUnavailable('Fortnite did not confirm the requested setting. Refresh to read its current state.')
