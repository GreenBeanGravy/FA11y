"""
Pluggable feature-matching backend for PPI.

PPI's SIFT-only path struggles on two kinds of terrain:

* **Low-contrast snow / ice / sand** — SIFT's default contrast threshold
  throws away keypoints that the minimap genuinely needs.
* **Reload arenas** — smaller, more uniformly-textured maps. SIFT finds
  enough keypoints but matches are noisier because the discriminative
  signal per keypoint is lower.

This module introduces a uniform interface across SIFT, AKAZE, and ORB,
plus an optional CLAHE preprocessing step. The right backend + preprocessing
varies per map (see ``coordinate_config`` for per-map overrides).

Design notes:

* SIFT uses float descriptors with L2 distance. AKAZE and ORB use binary
  (MLDB / BRIEF-family) descriptors with Hamming distance. ``build_matcher``
  picks the right norm automatically.
* The *map-side* detector is built with defaults (runs once per map, can be
  thorough). The *capture-side* detector is the one that runs every frame
  and carries the tunables — SIFT's ``contrastThreshold``, ORB's feature
  budget, AKAZE's threshold.
* CLAHE is applied uniformly to both sides when enabled. Applying it only
  to the capture would mean the descriptors don't compare — the map side
  needs the same histogram equalization.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class DetectorType(Enum):
    SIFT = "sift"
    AKAZE = "akaze"
    ORB = "orb"


@dataclass
class MatcherConfig:
    """All tunables for a single feature-matching pipeline."""

    detector: DetectorType = DetectorType.SIFT

    # SIFT tunables — applied to the capture-side detector.
    sift_n_features: int = 0              # 0 = unlimited
    sift_contrast_threshold: float = 0.03 # Lower catches snow / ice features
    sift_edge_threshold: float = 10.0

    # ORB tunables.
    orb_n_features: int = 2000
    orb_scale_factor: float = 1.2
    orb_n_levels: int = 8

    # AKAZE tunables.
    akaze_threshold: float = 0.001

    # Preprocessing — CLAHE dramatically improves match rate on
    # low-contrast terrain (snow, ice, uniform sand).
    preprocess_clahe: bool = False
    clahe_clip_limit: float = 2.0
    clahe_tile_grid: int = 8

    # Match filtering.
    lowe_ratio: float = 0.75
    min_good_matches: int = 25
    homography_reproj_threshold: float = 5.0

    @classmethod
    def from_name(cls, detector_name: str, **overrides) -> "MatcherConfig":
        """Build a config from a string detector name plus optional overrides."""
        try:
            det = DetectorType(detector_name.lower().strip())
        except ValueError:
            logger.warning(
                "Unknown detector %r, falling back to sift", detector_name
            )
            det = DetectorType.SIFT
        cfg = cls(detector=det)
        for k, v in overrides.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
        return cfg


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


def build_capture_detector(cfg: MatcherConfig):
    """Detector applied to every captured frame — keep it fast."""
    if cfg.detector is DetectorType.SIFT:
        return cv2.SIFT_create(
            nfeatures=cfg.sift_n_features,
            contrastThreshold=cfg.sift_contrast_threshold,
            edgeThreshold=cfg.sift_edge_threshold,
        )
    if cfg.detector is DetectorType.AKAZE:
        return cv2.AKAZE_create(threshold=cfg.akaze_threshold)
    if cfg.detector is DetectorType.ORB:
        return cv2.ORB_create(
            nfeatures=cfg.orb_n_features,
            scaleFactor=cfg.orb_scale_factor,
            nlevels=cfg.orb_n_levels,
        )
    raise ValueError(f"Unknown detector: {cfg.detector}")


def build_map_detector(cfg: MatcherConfig):
    """Detector applied once per map image (computed on load, cached)."""
    if cfg.detector is DetectorType.SIFT:
        # Unconstrained SIFT on the map — we only pay this cost once.
        return cv2.SIFT_create()
    # AKAZE and ORB don't benefit enough from "thorough" settings to warrant
    # a separate instance; reuse the capture-side config.
    return build_capture_detector(cfg)


def build_matcher(cfg: MatcherConfig) -> cv2.BFMatcher:
    """BFMatcher with the right norm for the detector family."""
    if cfg.detector is DetectorType.SIFT:
        return cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    # AKAZE MLDB and ORB rBRIEF are binary descriptors.
    return cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------


def preprocess_image(image: np.ndarray, cfg: MatcherConfig) -> np.ndarray:
    """CLAHE on the luminance channel — identity when disabled.

    This must be applied symmetrically to both the map image and each
    capture frame; otherwise descriptors drift apart.
    """
    if not cfg.preprocess_clahe:
        return image
    if image is None:
        return image
    # Work on grayscale. Caller is expected to pass gray already (PPI does).
    if image.ndim == 3:
        image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(
        clipLimit=cfg.clahe_clip_limit,
        tileGridSize=(cfg.clahe_tile_grid, cfg.clahe_tile_grid),
    )
    return clahe.apply(image)


# ---------------------------------------------------------------------------
# High-level helper
# ---------------------------------------------------------------------------


@dataclass
class MatchOutcome:
    """Rich result from a single match attempt — lets bench/dev tools inspect
    what happened even on partial failures."""

    corners_on_map: Optional[np.ndarray] = None  # (4, 1, 2) float32
    num_capture_keypoints: int = 0
    num_map_keypoints: int = 0
    num_knn_pairs: int = 0
    num_good_matches: int = 0
    num_inliers: int = 0
    homography: Optional[np.ndarray] = None
    failure_reason: Optional[str] = None


def match(
    capture_image: np.ndarray,
    map_keypoints: List,
    map_descriptors: np.ndarray,
    cfg: MatcherConfig,
    capture_detector=None,
    matcher=None,
) -> MatchOutcome:
    """Run a single capture->map match.

    Takes precomputed map keypoints/descriptors so callers control map-side
    caching. ``capture_detector`` and ``matcher`` may be passed in to avoid
    per-call construction cost; otherwise they're built from ``cfg``.
    """
    out = MatchOutcome()

    if capture_detector is None:
        capture_detector = build_capture_detector(cfg)
    if matcher is None:
        matcher = build_matcher(cfg)

    preprocessed = preprocess_image(capture_image, cfg)
    kp1, des1 = capture_detector.detectAndCompute(preprocessed, None)
    out.num_capture_keypoints = 0 if kp1 is None else len(kp1)

    if des1 is None:
        out.failure_reason = "no_capture_features"
        return out
    if map_descriptors is None:
        out.failure_reason = "no_map_descriptors"
        return out

    out.num_map_keypoints = 0 if map_keypoints is None else len(map_keypoints)

    pairs = matcher.knnMatch(des1, map_descriptors, k=2)
    out.num_knn_pairs = len(pairs)

    good = []
    for pair in pairs:
        if len(pair) == 2:
            m, n = pair
            if m.distance < cfg.lowe_ratio * n.distance:
                good.append(m)
    out.num_good_matches = len(good)

    if len(good) <= cfg.min_good_matches:
        out.failure_reason = "few_good_matches"
        return out

    src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([map_keypoints[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    M, mask = cv2.findHomography(
        src_pts, dst_pts, cv2.RANSAC, cfg.homography_reproj_threshold
    )
    if M is None or not np.all(np.isfinite(M)):
        out.failure_reason = "homography_fail"
        return out

    out.homography = M
    out.num_inliers = int(mask.sum()) if mask is not None else 0

    try:
        h, w = capture_image.shape[:2]
        pts = np.float32([[0, 0], [0, h - 1], [w - 1, h - 1], [w - 1, 0]]).reshape(-1, 1, 2)
        corners = cv2.perspectiveTransform(pts, M)
        if np.all(np.isfinite(corners)):
            out.corners_on_map = corners
        else:
            out.failure_reason = "non_finite_transform"
    except cv2.error as e:
        out.failure_reason = f"cv_error:{e}"
    return out
