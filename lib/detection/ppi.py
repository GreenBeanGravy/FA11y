"""
Player Position Interface (PPI) module for FA11y
Handles map-based position detection using computer vision.

Feature-matching backend is pluggable (SIFT / AKAZE / ORB) with optional
CLAHE preprocessing. See ``lib.detection.feature_matcher`` for the
abstraction and ``lib.detection.coordinate_config`` for per-map defaults
(Reload / Stranger Things maps override to AKAZE+CLAHE or SIFT+CLAHE).
"""
import cv2
import logging
import numpy as np
import os
from enum import Enum
from typing import Optional, Tuple
from lib.managers.screenshot_manager import capture_region
from lib.utilities.utilities import (
    read_config, on_config_change, get_config_boolean, get_config_value,
)
from lib.detection import feature_matcher
from lib.detection.feature_matcher import DetectorType, MatcherConfig, MatchOutcome
from lib.detection.coordinate_config import get_matcher_config as _get_map_matcher_override

logger = logging.getLogger(__name__)


class MatchFailure(Enum):
    """Reason the feature-matching pipeline failed — set on the module's
    ``last_match_failure`` global so debuggers / dev tools can inspect
    why a silent ``None`` came back."""
    NO_CAPTURE_FEATURES = "no keypoints in capture"
    NO_MAP_DESCRIPTORS = "map descriptors not loaded"
    FEW_GOOD_MATCHES = "too few matches survived Lowe's ratio test"
    HOMOGRAPHY_FAIL = "cv2.findHomography returned None or non-finite"
    NON_FINITE_TRANSFORM = "perspectiveTransform produced non-finite points"
    CV_ERROR = "cv2 raised an error during transform"


# Legacy tunables — kept for backwards compat. The live values now come
# from ``MatcherConfig`` (per-map in ``coordinate_config``, or falling back
# to the global config keys ``POI.feature_detector`` / ``POI.feature_clahe``).
LOWE_RATIO = 0.75
MIN_GOOD_MATCHES = 25
HOMOGRAPHY_REPROJ_THRESHOLD = 5.0

# Last failure reason (None if last match succeeded). Observable from dev tools.
last_match_failure: Optional[MatchFailure] = None

# Last match outcome, full detail — exposed for bench / dev tools.
last_match_outcome: Optional[MatchOutcome] = None

# Check if OpenCL is available and enable it. OpenCV's T-API will handle the rest.
use_gpu = cv2.ocl.haveOpenCL()
if use_gpu:
    cv2.ocl.setUseOpenCL(True)
    # Corrected, safe print statement
    # print("OpenCL-compatible GPU found. Enabling GPU acceleration.")
# else:
    # print("No OpenCL-compatible GPU found. Using CPU for PPI.")

# PPI constants - Current/Default
PPI_CAPTURE_REGION = {"top": 33, "left": 1637, "width": 250, "height": 250}

# Core constants for screen regions (imported from player_position for consistency)
ROI_START_ORIG = (524, 84)
ROI_END_ORIG = (1390, 1010)

# Legacy PPI constants (for "o g" map)
PPI_CAPTURE_REGION_LEGACY = {"top": 20, "left": 1600, "width": 300, "height": 300}
ROI_START_ORIG_LEGACY = (524, 84)
ROI_END_ORIG_LEGACY = (1390, 1010)

# Detection region dimensions
WIDTH, HEIGHT = ROI_END_ORIG[0] - ROI_START_ORIG[0], ROI_END_ORIG[1] - ROI_START_ORIG[1]

# Cached current map from config (updated via config change events)
_cached_current_map = 'main'

def _on_config_change(config):
    """Update cached config values when config changes.

    Also drop cached SIFT data for the old map so a fresh .png on disk
    (e.g. a user replacing a map asset) is picked up on the next match.
    """
    global _cached_current_map
    new_map = config.get('POI', 'current_map', fallback='main')
    if new_map != _cached_current_map:
        try:
            map_manager.map_load_cache.pop(_cached_current_map, None)
        except Exception:
            pass
    _cached_current_map = new_map

on_config_change(_on_config_change)
# Initialize from current config
try:
    _init_config = read_config()
    _cached_current_map = _init_config.get('POI', 'current_map', fallback='main')
except Exception:
    pass

def get_ppi_coordinates(map_name: str) -> dict:
    """Get appropriate PPI capture region based on map name"""
    if map_name == "o_g":
        return PPI_CAPTURE_REGION_LEGACY
    return PPI_CAPTURE_REGION

def get_roi_coordinates(map_name: str) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """Get appropriate ROI start/end coordinates based on map name"""
    if map_name == "o_g":
        return ROI_START_ORIG_LEGACY, ROI_END_ORIG_LEGACY
    return ROI_START_ORIG, ROI_END_ORIG

def _resolve_matcher_config(map_name: str) -> MatcherConfig:
    """Return the effective MatcherConfig for the given map.

    Resolution order:
    1. Per-map override from coordinate_config.MAP_MATCHER_OVERRIDES
    2. Global config: [POI] feature_detector + feature_clahe
    3. Fallback: SIFT with legacy defaults
    """
    override = _get_map_matcher_override(map_name)
    if override is not None:
        return override
    try:
        cfg = read_config()
        # ``get_config_value`` strips the quoted description suffix.
        detector_name, _ = get_config_value(cfg, 'feature_detector', fallback='sift')
        clahe = get_config_boolean(cfg, 'feature_clahe', False)
    except Exception:
        detector_name = 'sift'
        clahe = False
    return MatcherConfig.from_name(detector_name or 'sift', preprocess_clahe=clahe)


class MapManager:
    """Manages map data and matching for position detection.

    The detector + matcher + preprocessing pipeline is pluggable via
    ``MatcherConfig``. Cache is keyed by ``(map_name, detector, clahe)`` so
    changing detectors doesn't leave stale descriptors hanging around.
    """

    def __init__(self):
        self.current_map: Optional[str] = None
        self.current_image_dims = None
        self.current_keypoints = None
        self.current_descriptors = None
        self.current_matcher_cfg: Optional[MatcherConfig] = None
        self._capture_detector = None
        self._matcher = None

        # Cache keyed by (map_name, detector, clahe) — see _cache_key.
        self.map_load_cache: dict = {}
        self.last_map_printed: Optional[str] = None

    @staticmethod
    def _cache_key(map_name: str, cfg: MatcherConfig) -> tuple:
        return (map_name, cfg.detector.value, cfg.preprocess_clahe)

    def _rebuild_capture_tools(self, cfg: MatcherConfig) -> None:
        """Rebuild the capture-side detector and matcher for this config."""
        self._capture_detector = feature_matcher.build_capture_detector(cfg)
        self._matcher = feature_matcher.build_matcher(cfg)
        self.current_matcher_cfg = cfg

    def switch_map(self, map_name: str) -> bool:
        """Switch to a different map. Rebuilds cache if detector changed."""
        cfg = _resolve_matcher_config(map_name)
        key = self._cache_key(map_name, cfg)

        # Already loaded with the same detector config — just repoint.
        if self.current_map == map_name and self.current_matcher_cfg == cfg:
            return True

        if key in self.map_load_cache:
            entry = self.map_load_cache[key]
            self.current_map = map_name
            self.current_image_dims = entry['dims']
            self.current_keypoints = entry['keypoints']
            self.current_descriptors = entry['descriptors']
            self._rebuild_capture_tools(cfg)
            return True

        map_file = f"data/maps/{map_name}.png"
        if not os.path.exists(map_file):
            if self.last_map_printed != map_name:
                print(f"Map file not found: {map_file}")
                self.last_map_printed = map_name
            return False

        cpu_image = cv2.imread(map_file, cv2.IMREAD_GRAYSCALE)
        if cpu_image is None:
            return False
        self.current_map = map_name
        self.current_image_dims = cpu_image.shape

        # Apply identical preprocessing to the map image as will run on captures.
        pre = feature_matcher.preprocess_image(cpu_image, cfg)

        map_detector = feature_matcher.build_map_detector(cfg)
        self.current_keypoints, self.current_descriptors = map_detector.detectAndCompute(
            pre, None
        )
        self._rebuild_capture_tools(cfg)

        self.map_load_cache[key] = {
            'dims': self.current_image_dims,
            'keypoints': self.current_keypoints,
            'descriptors': self.current_descriptors,
        }
        logger.info(
            "PPI: loaded map %s with detector=%s clahe=%s kpts=%d",
            map_name,
            cfg.detector.value,
            cfg.preprocess_clahe,
            len(self.current_keypoints) if self.current_keypoints is not None else 0,
        )
        return True

# Global map manager instance
map_manager = MapManager()

# Last matched region (4 corners on map image) — used by storm monitor for scale
last_matched_region = None


def capture_map_screen(map_name: str = "main"):
    """Capture the map area of the screen using appropriate coordinates for the map"""
    region = get_ppi_coordinates(map_name)
    return capture_region(region, convert_format='gray')

def _fail(reason: MatchFailure, extra: str = ""):
    """Record and log a match failure; return None."""
    global last_match_failure
    last_match_failure = reason
    if extra:
        logger.debug("PPI match failed: %s (%s)", reason.value, extra)
    else:
        logger.debug("PPI match failed: %s", reason.value)
    return None


_FAILURE_REASON_MAP = {
    "no_capture_features":  MatchFailure.NO_CAPTURE_FEATURES,
    "no_map_descriptors":   MatchFailure.NO_MAP_DESCRIPTORS,
    "few_good_matches":     MatchFailure.FEW_GOOD_MATCHES,
    "homography_fail":      MatchFailure.HOMOGRAPHY_FAIL,
    "non_finite_transform": MatchFailure.NON_FINITE_TRANSFORM,
}


def _match_at_scale(captured_area, scale_factor=1):
    """Core matching logic. ``scale_factor > 1`` means capture was downscaled.

    Delegates to ``feature_matcher.match`` using the MapManager's currently
    bound detector + matcher (set by ``switch_map``). The src points returned
    by ``feature_matcher`` are in *small-capture* coordinates — they are
    scaled back to full capture space here before the homography is applied
    to the corners.
    """
    global last_match_failure, last_match_outcome

    if map_manager.current_matcher_cfg is None:
        # switch_map was never called — bail politely
        return _fail(MatchFailure.NO_MAP_DESCRIPTORS, "switch_map not called")

    cfg = map_manager.current_matcher_cfg

    if scale_factor > 1:
        small = cv2.resize(
            captured_area,
            (captured_area.shape[1] // scale_factor,
             captured_area.shape[0] // scale_factor),
        )
    else:
        small = captured_area

    # Run the match pipeline on the (possibly downscaled) capture.
    outcome = feature_matcher.match(
        small,
        map_manager.current_keypoints,
        map_manager.current_descriptors,
        cfg,
        capture_detector=map_manager._capture_detector,
        matcher=map_manager._matcher,
    )
    last_match_outcome = outcome

    if outcome.corners_on_map is None:
        reason = _FAILURE_REASON_MAP.get(
            outcome.failure_reason or "", MatchFailure.CV_ERROR
        )
        return _fail(reason, f"scale={scale_factor}")

    corners = outcome.corners_on_map

    # If the capture was downscaled, the homography was computed on
    # small-coord corners. We need to re-transform the full-size capture
    # rectangle using the same homography so the corners live in map-space
    # at the correct scale. The simplest fix: compute the full-size
    # rectangle and apply the homography to it with src_pts already in
    # small-space — but since corners came from small-space, we instead
    # scale the 4 corner points back out.
    if scale_factor > 1 and outcome.homography is not None:
        try:
            h_full, w_full = captured_area.shape[:2]
            pts_full = np.float32([
                [0, 0], [0, h_full - 1], [w_full - 1, h_full - 1], [w_full - 1, 0]
            ]).reshape(-1, 1, 2)
            # Convert full-size capture corners into small-space for the
            # small-space homography, then let it map to map space.
            pts_small = pts_full / float(scale_factor)
            corners = cv2.perspectiveTransform(pts_small, outcome.homography)
            if not np.all(np.isfinite(corners)):
                return _fail(MatchFailure.NON_FINITE_TRANSFORM)
        except cv2.error as e:
            return _fail(MatchFailure.CV_ERROR, str(e))

    last_match_failure = None
    return corners


def find_best_match(captured_area):
    """Find the best match between captured area and current map.

    Downscales the capture 2x for speed (3-4x faster SIFT + matching).
    Falls back to full resolution if the downscaled attempt fails.
    """
    # Fast path: downscaled capture (125x125 instead of 250x250)
    result = _match_at_scale(captured_area, scale_factor=2)
    if result is not None:
        return result

    # Fallback: full resolution for difficult areas
    return _match_at_scale(captured_area, scale_factor=1)

def find_player_position() -> Optional[Tuple[int, int]]:
    """Find player position using the map"""
    current_map_id = _cached_current_map

    # Extract actual map name for file loading
    if current_map_id == 'main':
        map_filename_to_load = 'main'
    else:
        if current_map_id.startswith("map_") and "_pois" in current_map_id:
            map_name_parts = current_map_id.split("_pois")
            base_name = map_name_parts[0]
            if base_name.startswith("map_"):
                base_name = base_name[4:]
            map_filename_to_load = base_name
        else:
            map_filename_to_load = current_map_id

    if not map_manager.switch_map(map_filename_to_load):
        return None

    # Get appropriate coordinates based on map name
    roi_start, roi_end = get_roi_coordinates(map_filename_to_load)
    roi_width = roi_end[0] - roi_start[0]
    roi_height = roi_end[1] - roi_start[1]

    captured_area = capture_map_screen(map_filename_to_load)
    matched_region = find_best_match(captured_area)

    global last_matched_region
    if matched_region is not None:
        last_matched_region = matched_region
        center = np.mean(matched_region, axis=0).reshape(-1)

        map_h, map_w = map_manager.current_image_dims
        x = int(center[0] * (roi_width / map_w) + roi_start[0])
        y = int(center[1] * (roi_height / map_h) + roi_start[1])

        return (x, y)
    return None

def get_ppi_status() -> dict:
    """Get current PPI system status for debugging"""
    # Descriptors can be UMat, get() retrieves them as numpy arrays to count
    desc = map_manager.current_descriptors
    desc_count = 0
    if desc is not None:
        # Check if the descriptor object is a UMat before calling .get()
        if isinstance(desc, cv2.UMat):
            desc_count = desc.get().shape[0]
        else: # It's a numpy array on CPU
            desc_count = desc.shape[0]

    return {
        'current_map': map_manager.current_map,
        'map_loaded': map_manager.current_image_dims is not None,
        'using_gpu_acceleration': use_gpu,
        'keypoints_count': len(map_manager.current_keypoints) if map_manager.current_keypoints else 0,
        'descriptors_count': desc_count,
        'cached_maps': list(map_manager.map_load_cache.keys())
    }

def cleanup_ppi():
    """Clean up PPI resources"""
    global map_manager
    if map_manager:
        map_manager.map_load_cache.clear()
        map_manager.current_map = None
        map_manager.current_image_dims = None
        map_manager.current_keypoints = None
        map_manager.current_descriptors = None