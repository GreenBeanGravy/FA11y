import re
from lib.player_location import find_player_icon_location, ROI_START_ORIG, ROI_END_ORIG

def get_current_coordinates():
    return find_player_icon_location()

def get_quadrant(x, y, width, height):
    mid_x, mid_y = width // 2, height // 2
    if x < mid_x:
        return "top left" if y < mid_y else "bottom left"
    else:
        return "top right" if y < mid_y else "bottom right"

def get_position_in_quadrant(x, y, quad_width, quad_height):
    third_x, third_y = quad_width // 3, quad_height // 3

    vertical = "top" if y < third_y else "bottom" if y > 2 * third_y else ""
    horizontal = "left" if x < third_x else "right" if x > 2 * third_x else ""

    if vertical and horizontal:
        return f"{vertical}-{horizontal}"
    elif vertical:
        return vertical
    elif horizontal:
        return horizontal
    else:
        return "center"