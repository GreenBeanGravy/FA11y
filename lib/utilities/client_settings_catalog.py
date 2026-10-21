"""Fortnite's own settings (ClientSettings.Sav) as the settings editor shows them.

The settings are the ones Fortnite's settings menu has on PC, in the menu's tabs and sections
and with its names (taken from the menu's own definition in the game files). Types come from
lib/data/client_settings_schema_4230.json, read from the game's class layout.

Fortnite only saves settings that differ from its defaults, so a setting can be missing from
the file. Missing on/off settings and choices then show as "Game default", and missing numbers
as an empty box. Choosing "Game default", or clearing the box, takes the setting out of the
file again so the game uses its default. What that default is comes from
lib/data/client_settings_defaults.json (read from the settings class in the game files);
settings the game decides while it runs aren't in it and just say "Game default".

Volumes live in BusNameVolumesMap (one entry per slider) and are shown as percents. Keyboard
bindings and mouse sensitivity are described in client_settings_binds.
"""
from __future__ import annotations

import json
import math
import os
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from lib.utilities import client_settings_binds as binds
from lib.utilities import client_settings_gamepad as pad
from lib.utilities import client_settings_turning as turning
from lib.utilities.client_settings import FStr, MapValue, Raw, Save, TypeName

SCHEMA_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'client_settings_schema_4230.json')
DEFAULTS_FILE = os.path.join(os.path.dirname(SCHEMA_FILE), 'client_settings_defaults.json')
RECORD, VOLUME = 'record', 'volume'
DEFAULT = 'default'
ENUM_PACKAGE = '/Script/FortniteGame'
NUMBER_TYPES = {'IntProperty': True, 'FloatProperty': False, 'DoubleProperty': False}

# (tab, group, property, label, description). Tabs, sections and labels are the ones Fortnite's
# settings menu uses on PC; descriptions say what the setting does.
CURATED: List[Tuple[str, str, str, str, str]] = [
    ('Game', 'Camera', 'bMovingTurnsCamera', 'Moving Turns Camera',
     'Moving sideways turns the camera with you. Epic keeps this switched off on PC, so it does '
     'nothing there for now.'),
    ('Game', 'Camera', 'bAutoCenterCamera', 'Auto-Center Camera',
     'The camera levels itself while you move. Epic keeps this switched off on PC, so it does '
     'nothing there for now.'),
    ('Game', 'Camera', 'ThirdPersonAutoFollowMode', 'Camera Follow',
     'Whether the camera swings round behind your character as you move: Off, Auto, or Lazy (slowly).'),
    ('Game', 'Camera', 'FirstPersonFOV', 'First Person FOV',
     'How wide your view is in first person modes, in degrees.'),
    ('Game', 'Movement', 'bToggleSprint', 'Toggle Sprint',
     'Pressing sprint once keeps you sprinting until you press it again.'),
    ('Game', 'Movement', 'bAutoOpenDoorsNonMobile', 'Auto Open Doors',
     'Doors open by themselves when you walk into them.'),
    ('Game', 'Movement', 'bAutoClamber', 'Mantle Activation',
     'How you grab onto a ledge after you jump: by holding forward, or by holding jump.'),
    ('Game', 'Movement', 'bAutoHurdle', 'Hurdle Activation',
     'How you hurdle over small obstacles: by running at them while you hold forward, or only when '
     'you press jump.'),
    ('Game', 'Combat', 'bTargetingToggleable', 'ADS',
     'Whether you aim down sights only while you hold the aim button, or press it once to start and '
     'again to stop.'),
    ('Game', 'Combat', 'bWeaponStayADSWhenManualReloadEnabled', 'ADS Reloading',
     'Whether you keep aiming down sights or stop aiming when you reload yourself.'),
    ('Game', 'Combat', 'bUseHoldToSwapPickup', 'Hold to Swap Pickup',
     'Holding interact swaps the item you look at with the one in your hand.'),
    ('Game', 'Combat', 'bAutoEquipBetterItems', 'Auto Equip Better Items',
     'A better version of the item in your hand is equipped as you pick it up.'),
    ('Game', 'Combat', 'bPlaceDangerMarkerWhenTargeting', 'Mark Danger When ADS',
     'Pinging while you aim down sights places a danger marker instead of a location marker.'),
    ('Game', 'Combat', 'bAutoPickupWeaponsConsolePC', 'Auto Pick Up Weapons',
     'Weapons you walk over are picked up when you have a free slot.'),
    ('Game', 'Combat', 'bSwapFireInputsForDualWieldShotgunSMG', 'Swap Fire Buttons for Pump & Dump',
     'Swaps which mouse button fires which half of the Pump & Dump.'),
    ('Game', 'Preferred Item Slots', 'bEnablePreferredItemSlots', 'Preferred Item Slots',
     'Items you pick up go into the slot you picked for their type. The slots themselves are set in '
     'the game.'),
    ('Game', 'Preferred Item Slots', 'bAutoSortConsumablesToRight', 'Auto Sort Consumables to Right',
     'Healing items and other consumables move to the right end of your inventory.'),
    ('Game', 'Building', 'bSmartBuildEnabled', 'Simple Build',
     'Building needs fewer buttons.'),
    ('Game', 'Building', 'bNewFocusOnFirstBuildingPieceWhenQuickbarSwappedAthena', 'Reset Building Choice',
     'Switching to build mode always starts on the first building piece. When off, you get the piece '
     'you used last.'),
    ('Game', 'Building', 'bTurboBuild', 'Turbo Building',
     'Holding the build button keeps placing pieces.'),
    ('Game', 'Building', 'bAutoChangeMaterial', 'Auto Material Change',
     'Building switches material when the one you use runs out.'),
    ('Game', 'Editing', 'bQuickEditEnabled', 'Simple Edit',
     'Pressing Edit once starts editing a building piece.'),
    ('Game', 'Editing', 'bTapQuickEditEnabled', 'Tap To Simple Edit',
     'Simple Edit actions that need a hold start with one press and finish by themselves.'),
    ('Game', 'Editing', 'bDisablePreEditsWhenPlacingBuilding', 'Disable Pre-Edit Option',
     'Pieces are placed without the edit you had chosen beforehand.'),
    ('Game', 'Editing', 'bEditConfirmOnReleaseEnabled', 'Confirm Edit On Release',
     'Letting go of the edit button confirms the edit.'),
    ('Game', 'Editing', 'bResetConfirmOnReleaseEnabled', 'Confirm Reset Edit On Release',
     'Letting go of the reset button confirms the reset.'),
    ('Game', 'Editing', 'bBuildingPossessionShown', 'Building Possession',
     'Looking at a building shows whether you can edit it.'),
    ('Game', 'Tutorial', 'bContextTutorialEnabled', 'Contextual Tips',
     'Shows tips about the game as you play.'),
    ('Game', 'Extra Game Options', 'bCreativeTurboDelete', 'Turbo Delete In Creative Mode',
     'Holding the delete button in Creative keeps deleting.'),
    ('Game', 'Extra Game Options', 'bShadowPlayHighlightsEnabled', 'NVIDIA Highlights',
     'Records NVIDIA highlights of moments like wins and eliminations. Needs an NVIDIA graphics card.'),
    ('Game', 'Replays', 'bReplayRecordingEnabled', 'Record Replays',
     'Saves replays of your Battle Royale matches.'),
    ('Game', 'Replays', 'bLargeTeamReplayRecordingEnabled', 'Record Large Team Replays',
     'Saves replays of large team modes such as 50v50. They can lower performance and take up disk space.'),
    ('Game', 'Replays', 'bCreativeModeReplayRecordingEnabled', 'Record Creative Replays',
     'Saves replays of Creative sessions.'),
    ('Game', 'Replays', 'bHighQualityReplayRecordingEnabled', 'Record High Quality Replays',
     'Replays record more often, so they play back with fewer glitches. This can lower performance and '
     'takes more disk space.'),
    ('Mouse and Keyboard', 'Sensitivity', 'bInvertedLookMouse', 'Invert Mouse View',
     'Moving the mouse up makes you look down.'),
    ('Mouse and Keyboard', 'Sensitivity', 'BuildingMultiplier', 'Building Sensitivity',
     'Mouse sensitivity in build mode, as a multiplier of the normal sensitivity.'),
    ('Mouse and Keyboard', 'Sensitivity', 'EditingMultiplier', 'Editing Sensitivity',
     'Mouse sensitivity in edit mode, as a multiplier of the normal sensitivity.'),
    ('Mouse and Keyboard', 'Sensitivity', 'FPSMultiplier', 'First Person Mode',
     'Mouse sensitivity in first person modes, as a multiplier of the normal sensitivity.'),
    ('Mouse and Keyboard', 'Sensitivity', 'MouseZoomScaling', 'Zoom Scaling',
     'How mouse sensitivity goes down when the camera zooms in. Legacy follows the field of view; '
     'Standard also allows for how big targets look on screen.'),
    ('Mouse and Keyboard', 'Sensitivity', 'bInvertedPitchForAircraftSecondary', 'Invert Aircraft Mouse Controls',
     'Moving the mouse forward points an aircraft down.'),
    ('Mouse and Keyboard', 'Sensitivity', 'bInvertedPitchForFightersMouse', 'Invert Fighter Mouse Controls',
     'Moving the mouse forward points a fighter down.'),
    ('Mouse and Keyboard', 'Sensitivity', 'bIgnoreGamepadInput', 'Ignore Controller Input',
     'The game ignores controllers. Useful with a tool that turns controller input into keys.'),
    ('Mouse and Keyboard', 'Sensitivity', 'bLockPrimaryInputMethodToMouse', 'Lock Input Method as Mouse',
     'You can use a controller and the mouse together, and the game keeps showing mouse and keyboard '
     'prompts.'),
    ('Mouse and Keyboard', 'Mouse Offset', 'OffsetAimingCombatMouse', 'Offset Aim Modes',
     'When moving the mouse moves the reticle on screen before it turns the camera.'),
    ('Mouse and Keyboard', 'Mouse Offset', 'OffsetAimingBuildMouse', 'Offset Build Modes',
     'Whether moving the mouse moves the reticle before it turns the camera while you build or edit.'),
    ('Mouse and Keyboard', 'Mouse Offset', 'OffsetAimingLimitMouse', 'Offset Limit',
     'How far the reticle can move from the center of the screen.'),
    ('Mouse and Keyboard', 'Mouse Offset', 'OffsetAimingCenteringMouse', 'Offset Centering Speed',
     'How fast the camera turns to bring the reticle back to the center.'),
    ('Mouse and Keyboard', 'Keyboard Movement', 'bCustomKeyboardDiagonals', 'Use Custom Diagonals',
     'Diagonal movement with the keyboard uses the angles below.'),
    ('Mouse and Keyboard', 'Keyboard Movement', 'KeyboardForwardDiagonal', 'Forward Diagonal Angle',
     'The angle, in degrees, you move at when you go forward diagonally.'),
    ('Mouse and Keyboard', 'Keyboard Movement', 'KeyboardStrafeDiagonal', 'Strafe Angle',
     'The angle, in degrees, you move at when you strafe.'),
    ('Mouse and Keyboard', 'Keyboard Movement', 'KeyboardBackwardDiagonal', 'Backward Diagonal Angle',
     'The angle, in degrees, you move at when you go backward diagonally.'),
    ('Mouse and Keyboard', 'Building', 'MouseBuildMode', 'Build With Building Keys',
     'In build mode, the keys that pick building pieces can also place them. Off means you pick a piece '
     'and then press Place Building.'),
    ('Mouse and Keyboard', 'Touchpad', 'bForceMaxTouchpadSensitivity', 'Touchpad Sensitivity to Maximum',
     'Typing no longer blocks a laptop touchpad, so it works better for playing. Stray touches can count '
     'if you also use a mouse.'),
    ('Mouse and Keyboard', 'Mouse Flight', 'MouseSensitivityMultiplierForAircraftValue',
     'Mouse Sensitivity Multiplier For Aircraft Steering',
     'Mouse sensitivity is multiplied by this when you steer an aircraft with the mouse.'),
    ('Controller', 'Input', 'bInvertedLookController', 'Invert Controller View',
     'Pushing the right stick up makes you look down.'),
    ('Controller', 'Input', 'bInvertedPitchForAircraftPrimary', 'Invert Aircraft Controller Controls',
     'Pushing the stick forward points an aircraft down.'),
    ('Controller', 'Input', 'bInvertedPitchForFightersGamepad', 'Invert Fighter Controller Controls',
     'Pushing the stick forward points a fighter down.'),
    ('Controller', 'Input', 'bUseGamepadAutoRun', 'Controller Auto-Run',
     'Pressing the left stick twice makes you run forward by yourself.'),
    ('Controller', 'Input', 'bEnableTryBuildOnFocus', 'Build Immediately (Builder Pro)',
     'With Builder Pro, switching to a building piece tries to place it straight away.'),
    ('Controller', 'Input', 'EditButtonHoldTime', 'Edit Hold Time',
     'How long, in seconds, you hold the edit button to start editing.'),
    ('Controller', 'Input', 'SimpleEditButtonHoldTime', 'Simple Edit Hold Time',
     'How long, in seconds, you hold the button to edit or reset with Simple Edit.'),
    ('Controller', 'Input', 'SlideButtonHoldTime', 'Slide Hold Time',
     'How long, in seconds, you hold the slide button to start sliding.'),
    ('Controller', 'Input', 'CameraResetAxes', 'Reset Camera Axes',
     'What Reset Camera puts back: Pitch only levels your view, Yaw only turns you to face the way '
     'your character faces, Both does both.'),
    ('Controller', 'Input', 'CameraResetTime', 'Reset Camera Time',
     'How long, in seconds, Reset Camera takes to move the camera back.'),
    ('Controller', 'Input', 'bForceFeedbackEnabled', 'Vibration',
     'The controller vibrates.'),
    ('Controller', 'Quick Weapon', 'bQuickWeaponToggleEnabled', 'Quick Weapon',
     'Quick Weapon takes the place of the Next Weapon button: press it to equip your primary item, or '
     'press it with another button to pick a slot. Custom only keeps it for custom button layouts.'),
    ('Controller', 'Quick Weapon', 'QuickWeaponDelay', 'Show Diamond Delay',
     'How long, in seconds, you hold Quick Weapon before its diamond shows on screen. It only changes '
     'what you see.'),
    ('Controller', 'Quick Weapon', 'QuickWeaponToggleMode', 'Toggle Behavior',
     'What tapping Quick Weapon does when your primary item is already in your hands.'),
    ('Controller', 'Quick Weapon', 'bQuickWeaponInstantToggleEnabled', 'Instant Toggle',
     'Your primary weapon is picked the moment you press Quick Weapon, not when you let go.'),
    ('Controller', 'Quick Weapon', 'QuickWeaponButtonGroup', 'Button Group',
     'Which buttons pick weapons while you hold Quick Weapon.'),
    ('Controller', 'Look Sensitivity', 'GamepadFPSModeMultiplier', 'First Person Mode',
     'Look sensitivity in first person modes, as a multiplier of the normal sensitivity.'),
    ('Controller', 'Legacy Controls', 'bAimAssistEnabled', 'Aim Assist',
     'The game helps keep your aim on targets while you use a controller.'),
    ('Controller', 'Legacy Controls', 'bUseGamepadEditModeAimAssist', 'Edit Mode Aim Assist',
     'In edit mode, your aim is pulled to the nearest edit square.'),
    ('Controller', 'Legacy Controls', 'GamepadBuildingMultiplier', 'Controller Building Sensitivity',
     'Controller sensitivity in build mode, as a multiplier of the normal sensitivity.'),
    ('Controller', 'Legacy Controls', 'GamepadEditModeMultiplier', 'Controller Edit Mode Sensitivity',
     'Controller sensitivity in edit mode, as a multiplier of the normal sensitivity.'),
    ('Controller', 'Dead Zone', 'GamepadMoveStickDeadZone', 'Left Stick Dead Zone',
     'How far the left stick moves before your character does, from 0 to 1.'),
    ('Controller', 'Dead Zone', 'GamepadLookStickDeadZone', 'Right Stick Dead Zone',
     'How far the right stick moves before the camera does, from 0 to 1.'),
    ('Controller', 'Tweak Zone', 'CombatTweakZone', 'Tweak Zone Aiming',
     'When small right stick movements move the reticle on screen, for fine aim, instead of turning '
     'the camera: while scoped, while scoped or aiming, always, whenever you are not scoped, or '
     'whenever you are not aiming.'),
    ('Controller', 'Tweak Zone', 'BuildingTweakZone', 'Tweak Zone Building',
     'When the tweak zone is on while building or editing.'),
    ('Controller', 'Tweak Zone', 'TweakZoneOverlap', 'Tweak Zone',
     'How much of the stick past the deadzone moves the reticle, from 0 to 1, where 1 is 100 '
     'percent. At 1 the whole stick only moves the reticle.'),
    ('Controller', 'Tweak Zone', 'TweakZoneScale', 'Tweak Sensitivity',
     'How far the tweak zone can move the reticle. 0 turns the tweak zone off.'),
    ('Controller', 'Flick Stick', 'bFlickStickEnabled', 'Flick Stick',
     'The right stick turns you straight to the direction you push it: right turns you a quarter turn '
     'right, down turns you around. Turning the stick round while held then turns you smoothly.'),
    ('Controller', 'Flick Stick', 'FlickTime', 'Flick Time',
     'How long, in seconds, a flick takes to turn you.'),
    ('Controller', 'Flick Stick', 'FlickStickWindingSpeed', 'Flick Stick Rotation Speed',
     'How fast turning the held stick round turns you.'),
    ('Controller', 'Flick Stick', 'FlickStickSmoothingThreshold', 'Flick Stick Smoothing',
     'Small stick movements below this are smoothed out.'),
    ('Controller', 'Flick Stick', 'FlickForwardDeadZone', 'Flick Forward Deadzone',
     'How far around straight up the stick counts as straight ahead (no turn).'),
    ('Controller', 'Flick Stick', 'FlickStickDeadZoneFactor', 'Flick Stick Deadzone',
     'How far the stick moves before it starts a flick.'),
    ('Controller', 'Foot Controller', 'bEnableRudderControl', 'Enable Foot Controller',
     'A foot controller is used for input when one is connected.'),
    ('Controller', 'Foot Controller', 'RudderDeadZone', 'Foot Controller Dead Zone',
     'How far the foot controller moves before it counts.'),
    ('Controller', 'Foot Controller', 'RudderMaxThrottle', 'Foot Controller Max Throttle',
     'The point on the foot controller that gives full throttle.'),
    ('Controller', 'Virtual Cursor', 'VirtualPointerSpeed', 'Pointer Speed',
     'How fast the on-screen pointer moves with a controller. 0.5 is the normal speed, which the game '
     'shows as 5.'),
    ('Controller', 'Virtual Cursor', 'VirtualPointerCursorOpacity', 'Pointer Opacity',
     'How solid the on-screen pointer looks, from 0 (see-through) to 1.'),
    ('Controller', 'Virtual Cursor', 'VirtualPointerHapticIntensity', 'Pointer Haptic Feedback Intensity',
     'How strongly the controller vibrates while you use the on-screen pointer, from 0 to 1.'),
    ('Audio', 'Sound', 'bVisualizeAudioSources', 'Visualize Sound Effects',
     'Shows on screen where sounds such as footsteps and gunfire come from. Depending on Epic\'s '
     'server settings, turning it on can also stop game sounds panning, so you no longer hear '
     'which side they come from.'),
    ('Audio', 'Sound', 'VisualizeAudioPriority', 'Visualize Sound Effects Priority',
     'Which sounds Visualize Sound Effects shows: All, or Critical (footsteps and vehicles, gunshots, '
     'and healing).'),
    ('Audio', 'Sound', 'bNewHitmarkersEnabled', 'Hitmarkers',
     'Which sounds play when you hit a target: Default, or Legacy (the older sounds).'),
    ('Audio', 'Sound', 'AllowAudioInBackground', 'Background Audio',
     'Whether you hear the game while another window is in front.'),
    ('Audio', 'Subtitles', 'bEnableSubtitles', 'Subtitles',
     'Shows subtitles for speech.'),
    ('Audio', 'Subtitles', 'SubtitleTextSize', 'Subtitle Text Size',
     'How big subtitles are.'),
    ('Audio', 'Subtitles', 'SubtitleTextColor', 'Subtitle Text Color',
     'The color of subtitle text.'),
    ('Audio', 'Subtitles', 'SubtitleTextBorder', 'Subtitle Text Border',
     'The border around subtitle text.'),
    ('Audio', 'Subtitles', 'SubtitleBackgroundOpacity', 'Subtitle Background Opacity',
     'How solid the background behind subtitles is, from Clear to Solid.'),
    ('Audio', 'Voice Chat', 'VoiceChatSetting', 'Voice Chat',
     'Who you can talk to with voice chat.'),
    ('Audio', 'Voice Chat', 'VoiceChatMethodNoMute', 'Voice Chat Method',
     'Whether your microphone is always on or you push a key to talk.'),
    ('Accessibility', 'Text Chat', 'bEnableTextToSpeech', 'Read Messages Aloud',
     'Reads incoming text chat messages aloud. English only.'),
    ('Accessibility', 'Text Chat', 'bEnableSpeechToText', 'Allow Voice Dictation',
     'Shows a microphone button in chat so you can type messages with your voice. English only.'),
    ('Accessibility', 'Color', 'ColorBlindMode', 'Color Blind Mode',
     'Changes the game\'s colors for a type of color blindness.'),
    ('Accessibility', 'Color', 'ColorBlindStrength', 'Color Blind Strength',
     'How strongly Color Blind Mode changes colors, from 0 to 10.'),
    ('Game UI', 'HUD Options', 'HUDScale', 'HUD Scale',
     'How big the on-screen HUD is, as a fraction of its normal size.'),
    ('Game UI', 'HUD Options', 'bShowViewerCount', 'Show Spectator Count',
     'Shows how many players are spectating you.'),
    ('Game UI', 'HUD Options', 'bAutoHideBuildingMaterials', 'Auto-Hide Building Materials',
     'Building materials only show on the HUD in build mode or when you pick some up.'),
    ('Game UI', 'HUD Options', 'bShouldShowBothQuickbars', 'Use Both Quickbars Layout',
     'Shows the combat and building quickbars at the same time. When off, only the one in use shows.'),
    ('Game UI', 'HUD Options', 'bShowQuickbarKeybinds', 'Show Quickbar Buttons',
     'Shows the key for each quickbar slot.'),
    ('Game UI', 'HUD Options', 'ShowPickupDotsOnMapByRarity', 'Minimap Pickup Indicators',
     'The map marks ingredients, ammo and building materials of this rarity and above.'),
    ('Game UI', 'HUD Options', 'bEnableCircularMinimapShape', 'Circular Minimap',
     'The minimap is round instead of square.'),
    ('Game UI', 'HUD Options', 'bEnablePlayerAlwaysFaceNorth', 'Lock Minimap Rotation',
     'The minimap turns with you and your marker stays still.'),
    ('Game UI', 'Reticle and Damage Feedback', 'HitNumbersMode', 'Damage Numbers',
     'How damage numbers appear when you hit something.'),
    ('Game UI', 'Reticle and Damage Feedback', 'bShowFirstPersonReticleSpread', 'Show Spread (First Person)',
     'The reticle grows to show how far your shots can stray, in first person modes.'),
    ('Game UI', 'Reticle and Damage Feedback', 'bShowThirdPersonReticleSpread', 'Show Spread (Third Person)',
     'The reticle grows to show how far your shots can stray, in third person modes.'),
    ('Game UI', 'Reticle and Damage Feedback', 'bShowFirstPersonReticleRecoil', 'Show Recoil (First Person)',
     'On weapons with offset recoil, the reticle moves off center to show recoil, in first person modes.'),
    ('Game UI', 'Reticle and Damage Feedback', 'bShowThirdPersonReticleRecoil', 'Show Recoil (Third Person)',
     'On weapons with offset recoil, the reticle moves off center to show recoil, in third person modes.'),
    ('Game UI', 'Reticle and Damage Feedback', 'bReticleRecoilPull', 'Pull Reticle',
     'When recoil moves the reticle off center, aiming the other way pulls it back before the camera turns.'),
    ('Game UI', 'Reticle and Damage Feedback', 'bReticleColorChangeForEnemyEnabled', 'Change Reticle Color For Enemy',
     'The crosshair changes color while it is over an enemy.'),
    ('Game UI', 'Reticle and Damage Feedback', 'ReticleEnemyColor', 'Reticle Color For Enemy',
     'The color the crosshair turns over an enemy.'),
    ('Account and Privacy', 'Privacy', 'bAnonymousMode', 'Hide My Name',
     'Other players see you with a generic name.'),
    ('Account and Privacy', 'Privacy', 'bHideOtherPlayerNames', 'Hide Other Players\' Names',
     'You see other players with generic names.'),
    ('Account and Privacy', 'Privacy', 'AllowedConfrontationalEmoteSources', 'See Confrontational Emotes',
     'Whose overly confrontational emotes you see.'),
]

# On/off settings whose choices the menu names (on, off).
BOOL_LABELS = {
    'bAutoClamber': ('Hold forward', 'Hold jump'),
    'bAutoHurdle': ('Hold forward', 'Press jump'),
    'bTargetingToggleable': ('Toggle', 'While held'),
    'bWeaponStayADSWhenManualReloadEnabled': ('Stay in ADS', 'Exit ADS'),
    'bQuickWeaponToggleEnabled': ('Enabled', 'Custom only'),
    'bNewHitmarkersEnabled': ('Default', 'Legacy'),
}

VOLUMES = [
    ('CB_Slider_Main', 'Main Volume'), ('CB_Slider_Music', 'Music Volume'),
    ('CB_Slider_LobbyMusic', 'Music - Lobby Volume'), ('CB_Slider_Pilgrim_Music', 'Music - Festival Volume'),
    ('CB_Slider_SFX', 'Gameplay Volume'), ('CB_Slider_Dialogue', 'Dialogue Volume'),
    ('CB_Slider_Chat', 'Voice Chat Volume'), ('CB_Slider_Cinematics', 'Cinematics Volume'),
    ('CB_Slider_PIP', 'Picture in Picture Volume'),
]
# Choice names Fortnite's menu uses (from its settings registry), in the menu's order. Values the
# menu leaves out get a name in the same style and come after. Other choices are named from the
# enum value.
CHOICE_LABELS = {
    'EActiveCombatMode': [('None', 'Off'), ('ScopeOnly', 'Scope'), ('ScopeADS', 'Scope or aiming'),
                          ('All', 'Always on'), ('NotScope', 'When not scoped'), ('HipOnly', 'When not aiming')],
    'EActiveBuildMode': [('None', 'Off'), ('Edit', 'Edit mode'), ('Build', 'Build mode'), ('All', 'Build or edit')],
    'EFortVoiceChatMethod': [('OpenMic', 'Open mic'), ('PTT', 'Push to talk'), ('Mute', 'Mute')],
    'ESocialCommsPermission': [('FriendsTeamConnections', 'Friends, teammates and connections')],
    'EVisualizeAudioPriority': [('All', 'All'), ('HighPriority', 'Critical')],
    'EMouseBuildMode': [('RequireConfirm', 'Off'), ('OnRepeat', 'Repeated press'), ('Immediate', 'Immediately')],
    'EQuickWeaponToggle': [('None', 'None'), ('Secondary', 'Slot 2'), ('PreviouslyEquipped', 'Previously equipped item')],
    'EQuickWeaponButtonGroup': [('DPad', 'Directional buttons'), ('FaceButtons', 'Action buttons'), ('Both', 'Both')],
    'EAllowedConfrontationalEmoteDisplaySources': [('Anyone', 'From anyone'),
                                                   ('FriendsInParty', 'From friends in party'), ('LocalOnly', 'Never')],
}
# Settings whose menu offers only some of the enum's values, with their own names.
PROPERTY_CHOICES = {
    'OffsetAimingCombatMouse': [('None', 'Off'), ('HipOnly', 'Not aiming'), ('ScopeOnly', 'Scope'),
                                ('ScopeADS', 'Scope or aiming'), ('All', 'Always offset')],
    'ShowPickupDotsOnMapByRarity': [('Common', 'Common'), ('Uncommon', 'Uncommon'), ('Rare', 'Rare'),
                                    ('Epic', 'Epic'), ('Legendary', 'Legendary'), ('Mythic', 'Mythic')],
}
# Enum values that are the engine's bookkeeping, not choices.
NOT_CHOICES = {'num', 'count', 'max', 'invalid'}
# The auto interact settings (bAutoInteract*) are left out: the game only runs them while the input
# type is touch, so on PC they do nothing.
TABS = ['Game', 'Mouse and Keyboard', 'Keybinds', 'Controller', 'Controller Binds', 'Audio', 'Accessibility', 'Game UI',
        'Account and Privacy']
VOLUME_MAP = 'BusNameVolumesMap'
LOOK_HEADING = 'Look Sensitivity'
NOT_SHOWN ='FA11y doesn\'t show this setting.'


@lru_cache(maxsize=1)
def load_schema() -> dict:
    with open(SCHEMA_FILE, encoding='utf-8') as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_defaults() -> dict:
    """The game's defaults: {'values': {property: value}, 'GamepadUserOptions': {'Basic.X': value}}.
    Empty when the file is missing, so every row just says Game default."""
    try:
        with open(DEFAULTS_FILE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def default_value(name: str):
    """The game's default for a setting, or None when it isn't known."""
    return load_defaults().get('values', {}).get(name)


def split_words(name: str) -> str:
    """'bAutoOpenDoorsNonMobile' -> 'Auto open doors non mobile'."""
    if re.match(r'b[A-Z]', name):
        name = name[1:]
    words = re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', ' ', name).replace('_', ' ').split()
    text = ' '.join(words)
    return text[:1].upper() + text[1:].lower() if text else name


def _type_name(spec: dict, existing: Optional[TypeName]) -> TypeName:
    """The tag type for a setting that is not in the file yet."""
    if existing is not None:
        return existing
    kind = spec['type']
    if kind == 'EnumProperty':
        return TypeName('EnumProperty', [TypeName(spec['enum'], [TypeName(ENUM_PACKAGE)]),
                                         TypeName(spec.get('inner', 'ByteProperty'))])
    return TypeName(kind)


class SettingsView:
    """The editor over one loaded settings file: what to show, and applying the user's changes."""

    def __init__(self, save: Save, original: Save, controller: bool = False):
        self.save = save
        self.original = original
        self.controller = controller        # show the Controller Binds tab
        schema = load_schema()
        self.specs: Dict[str, dict] = schema['settings']
        self.enums: Dict[str, List[str]] = schema['enums']
        self.curated = {name for _tab, _group, name, _label, _desc in CURATED}

    # Describing ----------------------------------------------------------------------------------

    def schema(self) -> List[dict]:
        tabs: Dict[str, Dict[str, List[dict]]] = {tab: {} for tab in TABS}
        for tab, group, name, label, description in CURATED:
            if name in self.specs:
                tabs[tab].setdefault(group, []).append(self.entry(name, label, description))
        volumes = self._volume_entries()
        if volumes:
            tabs['Audio'] = {'Volume': volumes, **tabs['Audio']}
        sensitivity = binds.sens_entries(self.save)
        if sensitivity:
            mouse = tabs['Mouse and Keyboard']
            tabs['Mouse and Keyboard'] = {'Sensitivity': sensitivity + mouse.pop('Sensitivity', []), **mouse}
        keybinds = dict(binds.bind_groups(self.save))
        tabs['Keybinds'] = {binds.CAMERA_HEADING: turning.rows(self.save) + keybinds.pop(binds.CAMERA_HEADING, []),
                            **keybinds}
        # The look options go first in Look Sensitivity, with Advanced Look Options right after it.
        looks, controller = dict(pad.look_entries(self.save)), {}
        for heading, entries in tabs['Controller'].items():
            controller[heading] = looks.pop(heading, []) + entries
            if heading == LOOK_HEADING:
                controller.update(looks)
                looks = {}
        controller.update(looks)
        tabs['Controller'] = controller
        if self.controller:
            tabs['Controller Binds'] = dict(pad.pad_groups(self.save))
        return [{'name': tab, 'groups': [{'heading': h, 'settings': s} for h, s in groups.items() if s]}
                for tab, groups in tabs.items() if groups]

    def search_entries(self) -> List[dict]:
        entries = []
        for tab in self.schema():
            for group in tab['groups']:
                for s in group['settings']:
                    entries.append({'id': s['id'], 'label': s['label'], 'tab': tab['name'], 'tab_name': tab['name'],
                                    'map': None, 'description': s['description'],
                                    'hay': f"{s['label']} {s['key']} {s['description']}".lower(),
                                    'text': f"{s['label']}, {tab['name']}"})
        return entries

    def entry(self, name: str, label: str, description: str) -> dict:
        spec = self.specs[name]
        prop = self.save.get(name)
        value = None if prop is None or isinstance(prop.value, Raw) else prop.value
        out: Dict[str, Any] = {'id': f'{RECORD}/{name}', 'section': RECORD, 'key': name, 'label': label,
                               'description': description, 'show_description': bool(description)}
        kind = spec['type']
        known = default_value(name)
        out['default'] = None
        if prop is not None and isinstance(prop.value, Raw):
            out.update(kind='text', value='(can\'t be edited here)')
        elif kind == 'BoolProperty':
            on, off = BOOL_LABELS.get(name, ('On', 'Off'))
            default_label = 'Game default' + ('' if known is None else f' ({on if known else off})')
            out.update(kind='choice', value=DEFAULT if value is None else ('on' if value else 'off'),
                       choices=[{'value': DEFAULT, 'label': default_label}, {'value': 'on', 'label': on},
                                {'value': 'off', 'label': off}])
        elif kind == 'EnumProperty':
            names = [n for n in self.enums.get(spec['enum'], []) if n.lower() not in NOT_CHOICES]
            if name in PROPERTY_CHOICES:
                named = dict(PROPERTY_CHOICES[name])
                names = [n for n in named if n in names]
            else:
                named = dict(CHOICE_LABELS.get(spec['enum'], []))
                names = [n for n in named if n in names] + [n for n in names if n not in named]

            def choice_label(value_name: str) -> str:
                return named.get(value_name, split_words(value_name))

            shown = f' ({choice_label(known.split("::")[-1])})' if isinstance(known, str) else ''
            choices = [{'value': DEFAULT, 'label': 'Game default' + shown}]
            choices += [{'value': f"{spec['enum']}::{n}", 'label': choice_label(n)} for n in names]
            current = str(value) if value is not None else DEFAULT
            if current != DEFAULT and current not in {c['value'] for c in choices}:
                choices.append({'value': current, 'label': choice_label(current.split('::')[-1])})
            out.update(kind='choice', value=current, choices=choices)
        elif kind in NUMBER_TYPES:
            # The default goes beside the box; the box itself stays empty while the setting isn't set.
            if isinstance(known, (int, float)) and not isinstance(known, bool):
                out['default'] = _number_text(known)
            if value is not None:
                integer = NUMBER_TYPES[kind]
                out.update(kind='number', value=value if integer else round(float(value), 6),
                           min=-1e9, max=1e9, step=1 if integer else 0.01, decimals=0 if integer else 4)
            else:
                out.update(kind='text', value='')
        else:
            out.update(kind='text', value='' if value is None else _number_text(value))
        return out

    def _volume_entries(self) -> List[dict]:
        volumes = self.save.get(VOLUME_MAP)
        if volumes is None or not isinstance(volumes.value, MapValue):
            return []
        values = {str(k): v for k, v in volumes.value.items}
        names = [k for k, _ in VOLUMES if k in values] + sorted(k for k in values if k not in dict(VOLUMES))
        labels = dict(VOLUMES)
        return [{'id': f'{VOLUME}/{k}', 'section': VOLUME, 'key': k, 'label': labels.get(k, split_words(k)),
                 'description': '', 'show_description': False, 'kind': 'number',
                 'value': int(round(float(values[k]) * 100)), 'min': 0, 'max': 100, 'step': 1, 'decimals': 0,
                 'default': None} for k in names if isinstance(values[k], float)]

    def label(self, section: str, key: str) -> str:
        if section == binds.BIND:
            return binds.bind_label(key)
        if section == binds.SENS:
            return binds.sens_label(key)
        if section == pad.LOOK:
            return pad.look_label(key)
        if section == turning.TURN:
            return turning.label(key)
        if section in (pad.PAD_BIND, pad.PAD_PRESET):
            return pad.pad_entry_label(self.save, section, key)
        if section == VOLUME:
            return dict(VOLUMES).get(key, split_words(key))
        for _tab, _group, name, label, _desc in CURATED:
            if name == key:
                return label
        return split_words(key)

    # Changing ------------------------------------------------------------------------------------

    def apply(self, section: str, key: str, value: Any, save: Optional[Save] = None) -> Any:
        """Set one setting from what its control holds. Returns what the control should show."""
        save = save or self.save
        if section == VOLUME:
            return self._apply_volume(save, key, value)
        if section == binds.BIND:
            return binds.apply_bind(save, key, value)
        if section == binds.SENS:
            return binds.apply_sens(save, key, value)
        if section == pad.LOOK:
            return pad.apply_look(save, key, value)
        if section == turning.TURN:
            return turning.apply(save, key, value)
        if section == pad.PAD_BIND:
            return pad.apply_pad_bind(save, key, value)[0]
        if section == pad.PAD_PRESET:
            return pad.apply_preset(save, value)
        if section != RECORD or key not in self.specs:
            raise ValueError('Unknown setting.')
        if key not in self.curated:
            raise ValueError(NOT_SHOWN)
        spec = self.specs[key]
        prop = save.get(key)
        if prop is not None and isinstance(prop.value, Raw):
            raise ValueError('This setting can\'t be edited here.')
        kind = spec['type']
        text = '' if value is None else str(value).strip()
        if text in ('', DEFAULT):
            save.remove(key)
            return DEFAULT if kind in ('BoolProperty', 'EnumProperty') else ''
        if kind == 'BoolProperty':
            if text not in ('on', 'off'):
                raise ValueError('Choose Game default, On or Off.')
            save.set(key, _type_name(spec, prop.type if prop else None), text == 'on')
            return text
        if kind == 'EnumProperty':
            allowed = {f"{spec['enum']}::{n}" for n in self.enums.get(spec['enum'], [])}
            if prop is not None:
                allowed.add(str(prop.value))
            if text not in allowed:
                raise ValueError('That isn\'t one of the choices.')
            save.set(key, _type_name(spec, prop.type if prop else None), FStr(text, False))
            return text
        if kind in NUMBER_TYPES:
            try:
                number = float(text)
            except ValueError:
                raise ValueError('Enter a number.') from None
            if not math.isfinite(number):
                raise ValueError('Enter a number.')
            if NUMBER_TYPES[kind]:
                if not number.is_integer() or abs(number) >= 2 ** 31:
                    raise ValueError('Enter a whole number.')
                number = int(number)
            save.set(key, _type_name(spec, prop.type if prop else None), number)
            # A text box (a setting that wasn't in the file) gets text back; a number box a number.
            return _number_text(number) if isinstance(value, str) else number
        if kind in ('StrProperty', 'NameProperty'):
            save.set(key, _type_name(spec, prop.type if prop else None),
                     FStr(text, getattr(prop.value, 'wide', False) if prop else False))
            return text
        raise ValueError('This setting can\'t be edited here.')

    def _apply_volume(self, save: Save, key: str, value: Any) -> int:
        volumes = save.get(VOLUME_MAP)
        if volumes is None or not isinstance(volumes.value, MapValue):
            raise ValueError('Unknown setting.')
        try:
            percent = max(0, min(int(round(float(value))), 100))
        except (TypeError, ValueError):
            raise ValueError('Enter a number from 0 to 100.') from None
        for i, (k, v) in enumerate(volumes.value.items):
            if str(k) == key:
                volumes.value.items[i] = (k, percent / 100.0)
                return percent
        raise ValueError('Unknown setting.')

    def original_value(self, section: str, key: str) -> Any:
        """What the setting's control showed when the file was loaded."""
        view = SettingsView(self.original, self.original)
        if section == binds.BIND:
            action, scale, slot = binds.parse_bind_id(key)
            return binds.current_key(self.original, action, scale, slot)
        if section == binds.SENS:
            return binds.sens_value(self.original, key)
        if section == pad.LOOK:
            return pad.look_values(self.original)[key]
        if section == turning.TURN:
            return turning.values(self.original)[key]
        if section == pad.PAD_BIND:
            return pad.pad_values(self.original).get(f'{pad.PAD_BIND}/{key}')
        if section == pad.PAD_PRESET:
            return pad.preset(self.original)
        if section == VOLUME:
            for entry in view._volume_entries():
                if entry['key'] == key:
                    return entry['value']
            raise ValueError('Unknown setting.')
        return view.entry(key, key, '')['value']

    def changes(self) -> List[str]:
        """Labels of the settings that differ from the file as loaded."""
        old, new = SettingsView(self.original, self.original), self
        changed = []
        for _tab, _group, name, _label, _desc in CURATED:
            if name not in self.specs:
                continue
            if old.entry(name, name, '')['value'] != new.entry(name, name, '')['value']:
                changed.append(self.label(RECORD, name))
        for entry in binds.sens_entries(self.save):
            if binds.sens_value(self.original, entry['key']) != entry['value']:
                changed.append(entry['label'])
        old_binds = binds.bind_values(self.original)
        for key, value in binds.bind_values(self.save).items():
            if old_binds.get(key) != value:
                changed.append(binds.bind_label(key))
        old_turn = turning.values(self.original)
        for key, value in turning.values(self.save).items():
            if old_turn[key] != value:
                changed.append(turning.label(key))
        old_look = pad.look_values(self.original)
        for key, value in pad.look_values(self.save).items():
            if old_look[key] != value:
                changed.append(pad.look_label(key))
        old_pad = pad.pad_values(self.original)
        for entry_id, value in pad.pad_values(self.save).items():
            if old_pad.get(entry_id) != value:
                section, _, key = entry_id.partition('/')
                changed.append(pad.pad_entry_label(self.save, section, key))
        old_volumes = {e['key']: e['value'] for e in old._volume_entries()}
        for entry in new._volume_entries():
            if old_volumes.get(entry['key']) != entry['value']:
                changed.append(entry['label'])
        return changed


def _number_text(value) -> str:
    if isinstance(value, float):
        return f'{value:.6f}'.rstrip('0').rstrip('.') or '0'
    return str(value)
