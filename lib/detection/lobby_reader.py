"""
Lobby screen reader for FA11y
Detects and controls mode selection screens (BR and Creative lobbies).
All coordinates assume 1920x1080 resolution.

Supports:
- BR-style screens: Build/Zero Build, Ranked, Team Size (Solo/Duo/Trio/Squad), Team Fill
- Creative screens: Privacy (Public/Private), Team Fill (Fill/No Fill)

Detection approach:
- Single full-screen capture, then pixel sampling at known coordinates
- Preset-driven: each game mode defines expected team sizes; the scan validates
  by matching the number of detected button clusters to the expected count
- This avoids false positives from fill toggles or other UI elements
"""

import time
import logging
import io

from PIL import Image
from lib.utilities.mouse import instant_click, move_to
from accessible_output2.outputs.auto import Auto
from lib.managers.screenshot_manager import ScreenshotManager

logger = logging.getLogger(__name__)
speaker = Auto()
screenshot_manager = ScreenshotManager()

# Debug: size of the region captured around click points for clipboard preview
DEBUG_REGION_SIZE = 80  # pixels in each direction from click point


# =====================================================================
# Helpers
# =====================================================================

def safe_speak(text):
    """Safely speak text, catching COM errors."""
    try:
        speaker.speak(text)
    except Exception as e:
        logger.debug(f"TTS error: {e}")


def _click_and_recapture(x, y, delay=0.3):
    """Click a position, move the mouse away, wait, then recapture.
    Moving the mouse away prevents hover effects from interfering with pixel reads."""
    instant_click(x, y)
    time.sleep(0.05)
    move_to(600, 540, duration=0)  # Move to center-left (neutral area)
    time.sleep(delay)
    return capture_screen()


def get_px(screen, x, y):
    """Get pixel (R,G,B) from numpy screenshot array (indexed [y, x])."""
    try:
        return tuple(int(v) for v in screen[y, x, :3])
    except (IndexError, TypeError):
        return None


def capture_screen():
    """Capture full screen as RGB numpy array."""
    return screenshot_manager.capture_full_screen('rgb')


def copy_region_to_clipboard(screen, cx, cy, label=""):
    """Copy a small region around (cx, cy) to the clipboard for calibration.
    Draws a red crosshair at the exact sample/click point."""
    try:
        import win32clipboard
        h = DEBUG_REGION_SIZE
        # Clamp to screen bounds
        y1 = max(0, cy - h)
        y2 = min(screen.shape[0], cy + h)
        x1 = max(0, cx - h)
        x2 = min(screen.shape[1], cx + h)
        region = screen[y1:y2, x1:x2].copy()

        # Draw red crosshair at the target pixel
        local_x = cx - x1
        local_y = cy - y1
        red = (255, 0, 0)
        for dx in range(-3, 4):
            nx = local_x + dx
            if 0 <= nx < region.shape[1]:
                region[local_y, nx] = red
        for dy in range(-3, 4):
            ny = local_y + dy
            if 0 <= ny < region.shape[0]:
                region[ny, local_x] = red

        img = Image.fromarray(region)
        output = io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        bmp_data = output.getvalue()[14:]  # Strip BMP file header for clipboard
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
        win32clipboard.CloseClipboard()

        px = get_px(screen, cx, cy)
        logger.info(f"Clipboard debug [{label}]: ({cx},{cy}) pixel={px}")
    except Exception as e:
        logger.debug(f"Clipboard debug failed: {e}")


# =====================================================================
# Color checks
# =====================================================================

def is_selected_blue(pixel):
    """Selected button/icon: bright blue background (normal/unranked mode).
    Must distinguish selected (0,85,254) from unselected (82,48,217)."""
    if pixel is None:
        return False
    r, g, b = pixel
    return b > 220 and r < 50


def is_selected_green(pixel):
    """Selected button/icon: green/yellow background (ranked mode).
    Ranked ON changes the selected color from blue to green/yellow.
    Examples: (200,255,0), (181,232,0)"""
    if pixel is None:
        return False
    r, g, b = pixel
    return g > 200 and b < 50 and r > 150


def is_selected(pixel):
    """Selected button: either blue (normal) or green (ranked mode)."""
    return is_selected_blue(pixel) or is_selected_green(pixel)


def is_yellow(pixel):
    """PLAY button yellow. Handles pure yellow and green-yellow variants."""
    if pixel is None:
        return False
    r, g, b = pixel
    return r >= 190 and g >= 200 and b < 100


def is_purple(pixel):
    """DONE button purple."""
    if pixel is None:
        return False
    r, g, b = pixel
    return r > 100 and b > 150 and g < 100


def _is_button_pixel(pixel):
    """Check if a pixel belongs to a team size button (selected or unselected).
    Selected: bright blue (0,85,254) or green (200,255,0)
    Unselected: dark blue (82,48,217) — distinct from gradient background (~25,13,70)"""
    if pixel is None:
        return False
    r, g, b = pixel
    # Selected blue/green
    if is_selected(pixel):
        return True
    # Unselected button dark blue: R=70-100, G=40-60, B=190-240
    if 50 < r < 110 and 30 < g < 70 and 180 < b < 240:
        return True
    # White icon overlay on buttons
    if r > 230 and g > 230 and b > 230:
        return True
    return False


# =====================================================================
# COORDINATE CONSTANTS (1920x1080)
# =====================================================================

# --- Build / Zero Build ---
# Sample at multiple positions to handle different mode layouts
BUILD_SAMPLES = [(1240, 170), (1240, 150), (1300, 160)]
ZEROBUILD_SAMPLES = [(1540, 170), (1540, 150), (1600, 160)]
BUILD_CLICK = (1340, 170)
ZEROBUILD_CLICK = (1640, 170)

# --- Ranked toggle ---
# The ranked toggle sits between BUILD/ZB and Team Size rows.
# Its exact y depends on the layout. We scan for it dynamically.
RANKED_TOGGLE_X_RANGE = (1640, 1740)

# --- BR screen gate pixels ---
BR_PLAY_GATE = (1200, 955)
BR_DONE_GATE = (1600, 955)

# --- Creative screen gate ---
CREATIVE_PLAY_GATE = (197, 691)
CREATIVE_FILL_TOGGLE_CLICK = (1380, 317)
CREATIVE_PUBLIC_SAMPLE = (1330, 277)
CREATIVE_PRIVATE_SAMPLE = (1400, 277)
CREATIVE_FILL_SAMPLE = (1420, 317)
CREATIVE_NOFILL_SAMPLE = (1345, 317)

# --- Team button scan parameters ---
TEAM_SCAN_X_START = 1400
TEAM_SCAN_X_END = 1900
TEAM_SCAN_X_STEP = 5
TEAM_SCAN_Y_START = 140
TEAM_SCAN_Y_END = 560
TEAM_SCAN_Y_STEP = 10
TEAM_MIN_CLUSTER_WIDTH = 15  # Minimum pixel span to count as a button

# --- Fill toggle scan parameters ---
FILL_TOGGLE_X_CENTER = 1690
FILL_TOGGLE_X_RANGE = (1640, 1740)

# --- Mode presets per map ---
# has_build: whether Build/Zero Build toggle exists
# ranked_sizes: which team sizes support ranked (None = all, [] = none)
MODE_PRESETS = {
    'main':                   {'sizes': ['Solo', 'Duo', 'Trio', 'Squad'], 'ranked': True,  'has_build': True,  'ranked_sizes': ['Solo', 'Duo', 'Squad']},
    'blitz':                  {'sizes': ['Solo', 'Duo', 'Squad', '6-Stack'], 'ranked': False, 'has_build': False},
    'blitz starfall':         {'sizes': ['Solo', 'Duo', 'Squad', '6-Stack'], 'ranked': False, 'has_build': False},
    'blitz stranger things':  {'sizes': ['Solo', 'Duo', 'Squad', '6-Stack'], 'ranked': False, 'has_build': False},
    'o g':                    {'sizes': ['Solo', 'Duo', 'Squad'], 'ranked': False, 'has_build': True},
    'reload oasis':           {'sizes': ['Solo', 'Duo', 'Squad'], 'ranked': True,  'has_build': True},
    'reload slurp rush':      {'sizes': ['Solo', 'Duo', 'Squad'], 'ranked': True,  'has_build': True},
    'reload surfcity':        {'sizes': ['Solo', 'Duo', 'Squad'], 'ranked': True,  'has_build': True},
    'reload venture':         {'sizes': ['Solo', 'Duo', 'Squad'], 'ranked': True,  'has_build': True},
}
DEFAULT_PRESET = {'sizes': ['Solo', 'Duo', 'Trio', 'Squad'], 'ranked': True, 'has_build': True}


def _get_current_preset():
    """Get the mode preset for the currently selected map."""
    try:
        from lib.utilities.utilities import read_config
        config = read_config()
        current_map = config.get('POI', 'current_map', fallback='main')
    except Exception:
        current_map = 'main'

    map_key = current_map.lower().strip()
    if map_key in MODE_PRESETS:
        preset = MODE_PRESETS[map_key]
    else:
        map_key_normalized = map_key.replace('_', ' ')
        preset = MODE_PRESETS.get(map_key_normalized, DEFAULT_PRESET)

    logger.info(f"[lobby] preset for map '{current_map}': {preset}")
    return preset


# =====================================================================
# Detection functions
# =====================================================================

def detect_screen_type(screen):
    """Detect lobby screen type.
    Returns 'br', 'creative', or None."""
    play_px = get_px(screen, *BR_PLAY_GATE)
    done_px = get_px(screen, *BR_DONE_GATE)
    logger.info(f"[lobby] screen gate: PLAY@{BR_PLAY_GATE}={play_px} yellow={is_yellow(play_px)}, DONE@{BR_DONE_GATE}={done_px} purple={is_purple(done_px)}")
    if is_yellow(play_px) and is_purple(done_px):
        logger.info("[lobby] detected: BR screen")
        return 'br'

    creative_px = get_px(screen, *CREATIVE_PLAY_GATE)
    logger.info(f"[lobby] creative gate: PLAY@{CREATIVE_PLAY_GATE}={creative_px} yellow={is_yellow(creative_px)}")
    if is_yellow(creative_px):
        logger.info("[lobby] detected: Creative screen")
        return 'creative'

    logger.info("[lobby] detected: NONE (not on mode select screen)")
    return None


def read_build_mode(screen):
    """Returns 'Build', 'Zero Build', or None.
    Tries multiple sample positions to handle different mode layouts."""
    for bx, by in BUILD_SAMPLES:
        px = get_px(screen, bx, by)
        if is_selected(px):
            logger.info(f"[lobby] build: Build selected at ({bx},{by})={px}")
            return 'Build'

    for zx, zy in ZEROBUILD_SAMPLES:
        px = get_px(screen, zx, zy)
        if is_selected(px):
            logger.info(f"[lobby] build: Zero Build selected at ({zx},{zy})={px}")
            return 'Zero Build'

    logger.info("[lobby] build: neither detected")
    return None


def _cluster_button_pixels(button_pixels):
    """Group contiguous button pixels into clusters.
    Returns list of clusters, where each cluster is a list of (x, pixel) tuples.
    Merges nearby clusters (within 50px center-to-center) to handle
    icon gaps within a single button."""
    if not button_pixels:
        return []

    # Step 1: Group contiguous pixels with 15px gap tolerance
    raw_clusters = []
    current_cluster = [button_pixels[0]]
    for i in range(1, len(button_pixels)):
        x_prev = button_pixels[i - 1][0]
        x_curr = button_pixels[i][0]
        if x_curr - x_prev > 15:
            raw_clusters.append(current_cluster)
            current_cluster = [button_pixels[i]]
        else:
            current_cluster.append(button_pixels[i])
    raw_clusters.append(current_cluster)

    # Step 2: Compute center_x and selected state for each raw cluster
    raw_buttons = []
    for cluster in raw_clusters:
        xs = [p[0] for p in cluster]
        center_x = (min(xs) + max(xs)) // 2
        width = max(xs) - min(xs)
        selected = any(is_selected(p[1]) for p in cluster)
        raw_buttons.append({'cx': center_x, 'sel': selected, 'width': width, 'pixels': cluster})

    # Step 3: Merge clusters whose centers are within 50px (handles split buttons)
    merged = [raw_buttons[0]]
    for btn in raw_buttons[1:]:
        prev = merged[-1]
        if abs(btn['cx'] - prev['cx']) < 50:
            all_xs = [p[0] for p in prev['pixels']] + [p[0] for p in btn['pixels']]
            merged_cx = (min(all_xs) + max(all_xs)) // 2
            merged[-1] = {
                'cx': merged_cx,
                'sel': prev['sel'] or btn['sel'],
                'width': max(all_xs) - min(all_xs),
                'pixels': prev['pixels'] + btn['pixels'],
            }
        else:
            merged.append(btn)

    return merged


def _scan_team_buttons(screen, preset):
    """Scan for team size buttons by testing y-positions and validating
    that the number of detected button clusters matches the preset's expected count.
    This prevents false positives from fill toggles or BUILD/ZB buttons.

    Returns (buttons_list, scan_y) where buttons_list is [(center_x, is_selected), ...]."""

    expected_count = len(preset['sizes'])
    logger.info(f"[lobby] team scan: looking for {expected_count} buttons")

    for scan_y in range(TEAM_SCAN_Y_START, TEAM_SCAN_Y_END, TEAM_SCAN_Y_STEP):
        # Collect button-colored pixels at this y
        button_pixels = []
        for x in range(TEAM_SCAN_X_START, TEAM_SCAN_X_END, TEAM_SCAN_X_STEP):
            px = get_px(screen, x, scan_y)
            if _is_button_pixel(px):
                button_pixels.append((x, px))

        if not button_pixels:
            continue

        # Cluster them
        clusters = _cluster_button_pixels(button_pixels)

        # Filter out clusters that are too narrow (< TEAM_MIN_CLUSTER_WIDTH)
        clusters = [c for c in clusters if c['width'] >= TEAM_MIN_CLUSTER_WIDTH]

        if len(clusters) != expected_count:
            continue

        # Validate: clusters should have roughly consistent spacing
        if len(clusters) > 1:
            centers = [c['cx'] for c in clusters]
            spacings = [centers[i+1] - centers[i] for i in range(len(centers)-1)]
            if max(spacings) - min(spacings) > 40:
                logger.info(f"[lobby] team scan y={scan_y}: {len(clusters)} clusters but uneven spacing {spacings}, skipping")
                continue

        # Found a valid match
        buttons = [(c['cx'], c['sel']) for c in clusters]
        logger.info(f"[lobby] team scan: found {len(buttons)} buttons at y={scan_y}: {[(cx, 'SEL' if s else 'unsel') for cx, s in buttons]}")
        return buttons, scan_y

    # Nothing found — log diagnostic info at a few key y values
    for diag_y in [170, 250, 330, 350, 460]:
        pixels = []
        for x in range(TEAM_SCAN_X_START, TEAM_SCAN_X_END, 40):
            px = get_px(screen, x, diag_y)
            pixels.append((x, px))
        logger.info(f"[lobby] team scan DIAG y={diag_y}: {pixels}")

    logger.info(f"[lobby] team scan: no y found with {expected_count} buttons")
    return [], 0


def _find_fill_toggle_y(screen, team_y):
    """Find the fill toggle y-position by scanning below the team buttons.
    The fill toggle has either green (ON), white (OFF knob), or is absent.
    Also checks for the dark-blue toggle track (82,48,217) which is always present
    even when locked.

    Returns the y-coordinate of the fill toggle center."""
    x_start, x_end = FILL_TOGGLE_X_RANGE

    # Scan y positions below team buttons
    for y in range(team_y + 80, min(team_y + 280, 700), 10):
        green_count = 0
        white_count = 0
        track_count = 0
        for x in range(x_start, x_end, 10):
            px = get_px(screen, x, y)
            if px is None:
                continue
            r, g, b = px
            # Green/yellow = fill toggle ON
            if g > 200 and b < 80 and r > 150:
                green_count += 1
            # White = toggle knob
            elif r > 200 and g > 200 and b > 200:
                white_count += 1
            # Dark blue track = toggle track (same as unselected buttons)
            elif 50 < r < 110 and 30 < g < 70 and 180 < b < 240:
                track_count += 1

        # A fill toggle has either green+track, white+track, or just track
        if green_count >= 2 or white_count >= 2 or track_count >= 4:
            logger.info(f"[lobby] fill toggle found at y={y} (green={green_count}, white={white_count}, track={track_count})")
            return y

    # Default: estimate based on typical spacing
    default_y = team_y + 140
    logger.info(f"[lobby] fill toggle not found, using default y={default_y}")
    return default_y


def find_layout(screen):
    """Scan for team size buttons and map them to the mode preset.
    Returns (layout_dict, selected_size_name) or (None, None)."""

    preset = _get_current_preset()
    expected_sizes = preset['sizes']

    buttons, scan_y = _scan_team_buttons(screen, preset)
    if not buttons:
        return None, None

    # Find fill toggle position
    fill_y = _find_fill_toggle_y(screen, scan_y)

    # Map buttons to preset size names
    button_dict = {}
    selected_name = None
    for i, (cx, is_sel) in enumerate(buttons):
        name = expected_sizes[i] if i < len(expected_sizes) else f'Button{i+1}'
        button_dict[name] = (cx, scan_y)
        if is_sel:
            selected_name = name

    layout = {
        'buttons': button_dict,
        'team_y': scan_y,
        'fill_toggle': (FILL_TOGGLE_X_CENTER, fill_y),
        'ranked_available': preset['ranked'],
    }

    logger.info(f"[lobby] layout: {len(buttons)} buttons at y={scan_y}, fill at y={fill_y}, selected={selected_name}")
    return layout, selected_name


def _find_ranked_toggle_y(screen, team_y):
    """Find the ranked toggle y-position by scanning ABOVE the team buttons.
    The ranked toggle sits between BUILD/ZB and team size.
    Returns the y-coordinate or None if not found."""
    x_start, x_end = RANKED_TOGGLE_X_RANGE

    # Scan y positions above team buttons (between BUILD row and team row)
    search_start = max(team_y - 200, 100)
    search_end = team_y - 20

    for y in range(search_start, search_end, 10):
        green_count = 0
        white_count = 0
        track_count = 0
        for x in range(x_start, x_end, 10):
            px = get_px(screen, x, y)
            if px is None:
                continue
            r, g, b = px
            if g > 200 and b < 80 and r > 150:
                green_count += 1
            elif r > 200 and g > 200 and b > 200:
                white_count += 1
            elif 50 < r < 110 and 30 < g < 70 and 180 < b < 240:
                track_count += 1

        if green_count >= 2 or white_count >= 2:
            logger.info(f"[lobby] ranked toggle found at y={y} (green={green_count}, white={white_count})")
            return y

    logger.info(f"[lobby] ranked toggle not found above team_y={team_y}")
    return None


def read_ranked_state(screen, preset=None, team_y=None):
    """Returns 'On', 'Off', or 'Unavailable'.
    Uses preset to check availability, then scans for the toggle."""
    if preset is None:
        preset = _get_current_preset()

    if not preset['ranked']:
        logger.info("[lobby] ranked: not available per preset")
        return 'Unavailable'

    # Find the ranked toggle position dynamically
    if team_y is None:
        # Fallback: scan for team buttons first
        buttons, team_y = _scan_team_buttons(screen, preset)
        if not buttons:
            return 'Unavailable'

    ranked_y = _find_ranked_toggle_y(screen, team_y)
    if ranked_y is None:
        logger.info("[lobby] ranked: toggle not found on screen")
        return 'Unavailable'

    # Check the toggle state at the found y
    x_start, x_end = RANKED_TOGGLE_X_RANGE
    has_green = False
    has_white = False
    for y in range(ranked_y - 10, ranked_y + 15, 5):
        for x in range(x_start, x_end, 10):
            px = get_px(screen, x, y)
            if px is None:
                continue
            r, g, b = px
            if g > 200 and b < 80 and r > 150:
                has_green = True
            elif r > 200 and g > 200 and b > 200:
                has_white = True

    logger.info(f"[lobby] ranked state at y={ranked_y}: green={has_green}, white={has_white}")
    if has_green:
        return 'On'
    if has_white:
        return 'Off'
    return 'Unavailable'


def read_fill_state(screen, fill_pos):
    """Read team fill toggle state.
    Returns 'Fill', 'No Fill', or 'Locked'."""
    fx, fy = fill_pos

    green_count = 0
    white_count = 0
    total_checked = 0
    for sy in range(fy - 10, fy + 15, 5):
        for sx in range(fx - 30, fx + 40, 10):
            px = get_px(screen, sx, sy)
            if px is None:
                continue
            total_checked += 1
            r, g, b = px
            if g > 200 and b < 80 and r > 150:
                green_count += 1
            if r > 200 and g > 200 and b > 200:
                white_count += 1

    logger.info(f"[lobby] fill @({fx},{fy}): green={green_count}/{total_checked}, white={white_count}/{total_checked}")

    if green_count >= 3:
        return 'Fill'
    if white_count >= 2:
        return 'No Fill'
    return 'Locked'


def read_creative_state(screen):
    """Read creative lobby state.
    Returns (privacy_str, fill_str) — either may be None."""
    pub_px = get_px(screen, *CREATIVE_PUBLIC_SAMPLE)
    priv_px = get_px(screen, *CREATIVE_PRIVATE_SAMPLE)

    privacy = None
    if pub_px and priv_px:
        pub_bright = sum(pub_px) / 3
        priv_bright = sum(priv_px) / 3
        if pub_bright > priv_bright + 30:
            privacy = 'Public'
        elif priv_bright > pub_bright + 30:
            privacy = 'Private'

    fill_px = get_px(screen, *CREATIVE_FILL_SAMPLE)
    nofill_px = get_px(screen, *CREATIVE_NOFILL_SAMPLE)

    fill = None
    if fill_px and nofill_px:
        fill_bright = sum(fill_px) / 3
        nofill_bright = sum(nofill_px) / 3
        if fill_bright > nofill_bright + 30:
            fill = 'Fill'
        elif nofill_bright > fill_bright + 30:
            fill = 'No Fill'

    return privacy, fill


# =====================================================================
# Debug composite
# =====================================================================

def _build_debug_composite(screen, points):
    """Build a composite debug image from multiple sample points and copy to clipboard."""
    try:
        import win32clipboard
        import numpy as np
        h = 60
        tiles = []
        for (px, py, label) in points:
            y1 = max(0, py - h)
            y2 = min(screen.shape[0], py + h)
            x1 = max(0, px - h)
            x2 = min(screen.shape[1], px + h)
            tile = screen[y1:y2, x1:x2].copy()
            lx, ly = px - x1, py - y1
            for d in range(-3, 4):
                if 0 <= lx + d < tile.shape[1]:
                    tile[ly, lx + d] = (255, 0, 0)
                if 0 <= ly + d < tile.shape[0]:
                    tile[ly + d, lx] = (255, 0, 0)
            tiles.append(tile)

        if not tiles:
            return

        max_h = max(t.shape[0] for t in tiles)
        padded = []
        for t in tiles:
            if t.shape[0] < max_h:
                pad = np.zeros((max_h - t.shape[0], t.shape[1], 3), dtype=np.uint8)
                t = np.vstack([t, pad])
            padded.append(t)
        composite = np.hstack(padded)

        img = Image.fromarray(composite)
        output = io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        bmp_data = output.getvalue()[14:]
        output.close()

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
        win32clipboard.CloseClipboard()
        logger.info(f"[lobby] debug composite copied to clipboard ({len(tiles)} tiles)")
    except Exception as e:
        logger.debug(f"Composite clipboard debug failed: {e}")


# =====================================================================
# Public action functions — wired to keybinds in FA11y.py
# =====================================================================

def read_mode_status():
    """Read and announce the full lobby mode status."""
    screen = capture_screen()
    if screen is None:
        safe_speak("Cannot capture screen")
        return

    screen_type = detect_screen_type(screen)

    debug_points = [
        (*BR_PLAY_GATE, "PLAY_gate"),
        (*BR_DONE_GATE, "DONE_gate"),
    ]

    if screen_type == 'br':
        parts = []

        build = read_build_mode(screen)
        if build:
            parts.append(build)

        layout, current_size = find_layout(screen)

        if layout:
            # Add debug points for all team size buttons
            for name, (bx, by) in layout['buttons'].items():
                debug_points.append((bx, by, f"TS_{name}"))
            debug_points.append((*layout['fill_toggle'], "FILL"))

            # Read ranked state
            preset = _get_current_preset()
            ranked = read_ranked_state(screen, preset, layout.get('team_y'))
            if ranked == 'On':
                parts.append("Ranked On")
            elif ranked == 'Off':
                parts.append("Ranked Off")
            # 'Unavailable' = don't mention ranked

        if current_size:
            parts.append(current_size)

        # Read fill state, but skip for Solo (fill is always locked for Solo)
        if layout and current_size != 'Solo':
            fill = read_fill_state(screen, layout['fill_toggle'])
            if fill and fill != 'Locked':
                parts.append(fill)

        _build_debug_composite(screen, debug_points)
        safe_speak(", ".join(parts) if parts else "Could not read mode settings")

    elif screen_type == 'creative':
        privacy, fill = read_creative_state(screen)
        parts = []
        if privacy:
            parts.append(privacy)
        if fill:
            parts.append(fill)
        debug_points.append((*CREATIVE_PUBLIC_SAMPLE, "PUBLIC"))
        debug_points.append((*CREATIVE_PRIVATE_SAMPLE, "PRIVATE"))
        debug_points.append((*CREATIVE_FILL_SAMPLE, "FILL"))
        debug_points.append((*CREATIVE_NOFILL_SAMPLE, "NOFILL"))
        _build_debug_composite(screen, debug_points)
        safe_speak(", ".join(parts) if parts else "Could not read creative settings")

    else:
        _build_debug_composite(screen, debug_points)
        safe_speak("Not on a mode selection screen")


def toggle_lobby_fill():
    """Toggle team fill (BR) or fill (Creative).
    Announces new state after toggling."""
    screen = capture_screen()
    if screen is None:
        safe_speak("Cannot capture screen")
        return

    screen_type = detect_screen_type(screen)

    if screen_type == 'br':
        layout, current_size = find_layout(screen)
        if layout is None:
            safe_speak("Cannot detect mode layout")
            return

        # Solo always has locked fill
        if current_size == 'Solo':
            safe_speak("Fill not available for Solo")
            return

        fill = read_fill_state(screen, layout['fill_toggle'])
        if fill == 'Locked':
            safe_speak("Fill not available")
            return

        click_x, click_y = layout['fill_toggle']
        screen = _click_and_recapture(click_x, click_y)
        if screen is not None:
            new_fill = read_fill_state(screen, layout['fill_toggle'])
            safe_speak(new_fill if new_fill else "Fill toggled")

    elif screen_type == 'creative':
        click_x, click_y = CREATIVE_FILL_TOGGLE_CLICK
        screen = _click_and_recapture(click_x, click_y)
        if screen is not None:
            _, fill = read_creative_state(screen)
            safe_speak(fill if fill else "Fill toggled")

    else:
        safe_speak("Not on a mode selection screen")


def set_team_size(requested_name):
    """Set a specific team size by name (Solo, Duo, Trio, Squad, 6-Stack).
    Clicks the button, then announces the result."""
    screen = capture_screen()
    if screen is None:
        safe_speak("Cannot capture screen")
        return

    if detect_screen_type(screen) != 'br':
        safe_speak("Team size not available")
        return

    layout, current_size = find_layout(screen)
    if layout is None:
        safe_speak("Cannot detect team size layout")
        return

    # Already on the requested size?
    if current_size == requested_name:
        safe_speak(f"Already on {requested_name}")
        return

    # Check if requested size exists in the preset
    if requested_name not in layout['buttons']:
        safe_speak(f"{requested_name} not available")
        return

    # Check ranked + team size restriction (e.g., no ranked trios on main BR)
    preset = _get_current_preset()
    ranked_sizes = preset.get('ranked_sizes')
    if ranked_sizes is not None:
        # Check if ranked is currently on
        ranked_state = read_ranked_state(screen, preset, layout.get('team_y'))
        if ranked_state == 'On' and requested_name not in ranked_sizes:
            safe_speak(f"{requested_name} not available in ranked")
            return

    click_x, click_y = layout['buttons'][requested_name]
    _click_and_recapture(click_x, click_y, delay=0.5)
    safe_speak(requested_name)

    # Read fill state after switching (skip for Solo)
    if requested_name != 'Solo':
        time.sleep(0.2)
        screen = capture_screen()
        if screen is not None:
            fill = read_fill_state(screen, layout['fill_toggle'])
            if fill and fill != 'Locked':
                safe_speak(fill)


def toggle_ranked():
    """Toggle ranked mode on BR screen.
    Announces new ranked state."""
    screen = capture_screen()
    if screen is None:
        safe_speak("Cannot capture screen")
        return

    if detect_screen_type(screen) != 'br':
        safe_speak("Ranked not available")
        return

    preset = _get_current_preset()

    if not preset['ranked']:
        safe_speak("Ranked not available for this mode")
        return

    # Find team buttons to locate ranked toggle relative to them
    buttons, team_y = _scan_team_buttons(screen, preset)
    if not buttons:
        safe_speak("Cannot detect mode layout")
        return

    ranked_y = _find_ranked_toggle_y(screen, team_y)
    if ranked_y is None:
        safe_speak("Ranked toggle not found")
        return

    # Read state before toggle
    before = read_ranked_state(screen, preset, team_y)
    logger.info(f"[lobby] toggle_ranked: before={before}")

    if before == 'Unavailable':
        safe_speak("Ranked not available")
        return

    # If turning ranked ON, check if current team size supports ranked
    if before == 'Off':
        ranked_sizes = preset.get('ranked_sizes')
        if ranked_sizes is not None:
            # Find which button is currently selected
            _, current_size = find_layout(screen)
            if current_size and current_size not in ranked_sizes:
                safe_speak(f"Ranked not available for {current_size}")
                return

    # Click the toggle center
    click_x = (RANKED_TOGGLE_X_RANGE[0] + RANKED_TOGGLE_X_RANGE[1]) // 2
    screen = _click_and_recapture(click_x, ranked_y, delay=0.5)
    if screen is not None:
        after = read_ranked_state(screen, preset)
        logger.info(f"[lobby] toggle_ranked: after={after}")
        if after and after != 'Unavailable':
            safe_speak(f"Ranked {after}")
        else:
            safe_speak("Ranked toggled")


def toggle_build_mode():
    """Toggle between Build and Zero Build on BR screen.
    Announces the new build mode."""
    preset = _get_current_preset()
    if not preset.get('has_build', True):
        safe_speak("Build mode not available for this mode")
        return

    screen = capture_screen()
    if screen is None:
        safe_speak("Cannot capture screen")
        return

    if detect_screen_type(screen) != 'br':
        safe_speak("Build mode not available")
        return

    current = read_build_mode(screen)
    if current == 'Build':
        click_x, click_y = ZEROBUILD_CLICK
    elif current == 'Zero Build':
        click_x, click_y = BUILD_CLICK
    else:
        safe_speak("Cannot detect current build mode")
        return

    screen = _click_and_recapture(click_x, click_y)
    if screen is not None:
        new_mode = read_build_mode(screen)
        safe_speak(new_mode if new_mode else "Build mode toggled")
