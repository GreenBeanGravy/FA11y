from accessible_output2.outputs.auto import Auto
from lib.player_location import find_player_icon_location, ROI_START_ORIG, ROI_END_ORIG

speaker = Auto()

def speak(s):
    speaker.speak(s)

def get_current_coordinates():
    coords = find_player_icon_location()
    if coords:
        return coords
    return None

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
    elif vertical or horizontal:
        return vertical or horizontal
    else:
        return "center"

def speak_current_coordinates():
    coords = get_current_coordinates()
    if coords:
        # Convert the on-screen coordinates to ROI coordinates
        roi_x = coords[0] - ROI_START_ORIG[0]
        roi_y = coords[1] - ROI_START_ORIG[1]
        
        # Ensure the coordinates are within the ROI bounds
        roi_width = ROI_END_ORIG[0] - ROI_START_ORIG[0]
        roi_height = ROI_END_ORIG[1] - ROI_START_ORIG[1]
        roi_x = max(0, min(roi_x, roi_width))
        roi_y = max(0, min(roi_y, roi_height))
        
        # Determine quadrant
        quadrant = get_quadrant(roi_x, roi_y, roi_width, roi_height)
        
        # Determine position within quadrant
        quad_width = roi_width // 2
        quad_height = roi_height // 2
        quad_x = roi_x % quad_width
        quad_y = roi_y % quad_height
        position_in_quadrant = get_position_in_quadrant(quad_x, quad_y, quad_width, quad_height)
        
        speak(f"You are at {roi_x}, {roi_y}, in the {position_in_quadrant} of the {quadrant} quadrant")
        print(f"On-screen coordinates: {coords[0]}, {coords[1]}")
        print(f"Visible area coordinates: {roi_x}, {roi_y}")
        print(f"Quadrant: {quadrant}")
        print(f"Position in quadrant: {position_in_quadrant}")
    else:
        speak("Unable to determine current coordinates")

if __name__ == "__main__":
    speak_current_coordinates()