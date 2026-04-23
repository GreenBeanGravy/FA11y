"""
Movement / camera action handlers.

Pure config-driven mouse-move wrappers. No state mutation, just reads
from the config and calls ``smooth_move_mouse`` / ``mouse_scroll``.

The ``speaker`` is injected so this module stays free of global
dependencies. Callers in ``FA11y.py`` wrap these via the action-handler
dispatch table.
"""
from __future__ import annotations

from lib.utilities.mouse import smooth_move_mouse, mouse_scroll
from lib.utilities.utilities import get_config_int, get_config_float, read_config


def handle_movement(action: str, reset_sensitivity: bool, speaker) -> None:
    """Handle all movement-related actions."""
    config = read_config()
    turn_sensitivity = get_config_int(config, 'TurnSensitivity', 100)
    secondary_turn_sensitivity = get_config_int(config, 'SecondaryTurnSensitivity', 50)
    turn_delay = get_config_float(config, 'TurnDelay', 0.01)
    turn_steps = get_config_int(config, 'TurnSteps', 5)
    recenter_delay = get_config_float(config, 'RecenterDelay', 0.05)
    recenter_steps = get_config_int(config, 'RecenterSteps', 10)
    recenter_step_delay = get_config_float(config, 'RecenterStepDelay', 0) / 1000.0
    recenter_step_speed = get_config_int(config, 'RecenterStepSpeed', 0)
    up_down_sensitivity = turn_sensitivity // 2
    x_move, y_move = 0, 0

    if action in ['turn left', 'turn right', 'secondary turn left',
                  'secondary turn right', 'look up', 'look down']:
        if 'secondary' in action:
            sensitivity = secondary_turn_sensitivity
        elif action in ['look up', 'look down']:
            sensitivity = up_down_sensitivity
        else:
            sensitivity = turn_sensitivity

        if 'left' in action:
            x_move = -sensitivity
        elif 'right' in action:
            x_move = sensitivity
        elif action == 'look up':
            y_move = -sensitivity
        elif action == 'look down':
            y_move = sensitivity

        smooth_move_mouse(x_move, y_move, turn_delay, turn_steps)
        return

    if action == 'turn around':
        x_move = get_config_int(config, 'TurnAroundSensitivity', 1158)
        smooth_move_mouse(x_move, 0, turn_delay, turn_steps)
        return

    if action == 'recenter':
        if reset_sensitivity:
            recenter_move = get_config_int(config, 'ResetRecenterLookDown', 1500)
            down_move = get_config_int(config, 'ResetRecenterLookUp', -580)
        else:
            recenter_move = get_config_int(config, 'RecenterLookDown', 1500)
            down_move = get_config_int(config, 'RecenterLookUp', -820)

        smooth_move_mouse(0, recenter_move, recenter_step_delay, recenter_steps,
                          recenter_step_speed, down_move, recenter_delay)
        speaker.speak("Reset Camera")
        return

    smooth_move_mouse(x_move, y_move, recenter_delay)


def handle_scroll(action: str) -> None:
    """Handle scroll-wheel actions."""
    config = read_config()
    scroll_sensitivity = get_config_int(config, 'ScrollSensitivity', 120)
    if action == 'scroll down':
        scroll_sensitivity = -scroll_sensitivity
    mouse_scroll(scroll_sensitivity)
