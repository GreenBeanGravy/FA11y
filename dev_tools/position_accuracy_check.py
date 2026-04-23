"""
Position-detection accuracy check.

Unlike ``feature_match_bench.py`` (which samples random crops and reports
aggregate statistics), this tool asks: *where does the detector actually
think you are, and is it right?*

For a given map it:

1. Identifies "snow-heavy" regions by finding pixels with high luminance
   and low saturation (the characteristic white/light-gray of Fortnite's
   snow biomes). Other region modes available: ``--region random``
   (uniform random) or ``--region manual X Y`` (one specific origin).
2. Samples N 250x250 crops that are at least 60% snow pixels.
3. Runs each detector (SIFT, AKAZE, ORB × CLAHE on/off) on each crop.
4. For every successful match, maps the crop's *center* back onto the
   map via the recovered homography and measures the distance to the
   ground-truth center (in map pixels). This is the quantity that matters
   for "where it says you are".
5. Writes a visualization PNG per (map, detector) showing ground-truth
   centers in green and detected centers in red, connected by a line.
   At a glance you can see where the detector drifts.

Usage:
    python dev_tools/position_accuracy_check.py reload_elite_stronghold
    python dev_tools/position_accuracy_check.py reload_elite_stronghold -n 50
    python dev_tools/position_accuracy_check.py blitz_stranger_things --region random
    python dev_tools/position_accuracy_check.py <map> --manual 500 300
"""
from __future__ import annotations

import argparse
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
os.chdir(_REPO_ROOT)

from lib.detection import feature_matcher  # noqa: E402
from lib.detection.feature_matcher import (  # noqa: E402
    DetectorType, MatcherConfig,
)


CAPTURE_W = 250
CAPTURE_H = 250
SNOW_FRACTION_THRESHOLD = 0.40  # Min fraction of "snowy" pixels in a crop
SNOW_L_MIN = 140                # Snow pixel: luminance >= this (0-255)
SNOW_S_MAX = 60                 # ...and saturation <= this
# Tuned against reload_elite_stronghold where snow is rendered as a slightly
# bluish off-white rather than pure 255. Lowering L_MIN from 190 -> 140 and
# S_MAX from 40 -> 60 captures the actual snow palette in compressed PNGs.
MAX_ACCEPTED_ERROR_PX = 75.0    # Anything worse is considered a failure

# Out dir
OUT_DIR = os.path.join("dev_tools", "position_accuracy_out")


@dataclass
class Sample:
    origin: Tuple[int, int]   # top-left of the crop
    center: Tuple[int, int]   # ground-truth center of the crop
    detected_center: Optional[Tuple[float, float]]
    error_px: Optional[float]
    detector: str
    clahe: bool
    latency_ms: float


def _snow_mask(bgr: np.ndarray) -> np.ndarray:
    """Boolean mask of snow-like pixels (high L, low S in HLS)."""
    hls = cv2.cvtColor(bgr, cv2.COLOR_BGR2HLS)
    L = hls[..., 1]
    S = hls[..., 2]
    return (L >= SNOW_L_MIN) & (S <= SNOW_S_MAX)


def _sample_snow_origins(
    bgr_map: np.ndarray, n: int, rng: random.Random,
    max_attempts: int = 2000,
) -> List[Tuple[int, int]]:
    """Return n crop origins whose area is >= SNOW_FRACTION_THRESHOLD snow."""
    snow = _snow_mask(bgr_map)
    h, w = snow.shape
    out: List[Tuple[int, int]] = []
    attempts = 0
    while len(out) < n and attempts < max_attempts:
        attempts += 1
        ox = rng.randint(0, w - CAPTURE_W - 1)
        oy = rng.randint(0, h - CAPTURE_H - 1)
        patch = snow[oy:oy + CAPTURE_H, ox:ox + CAPTURE_W]
        frac = float(patch.mean())
        if frac >= SNOW_FRACTION_THRESHOLD:
            out.append((ox, oy))
    if len(out) < n:
        print(
            f"  (only found {len(out)}/{n} crops with >= "
            f"{SNOW_FRACTION_THRESHOLD:.0%} snow after {attempts} attempts)"
        )
    return out


def _sample_random_origins(
    bgr_map: np.ndarray, n: int, rng: random.Random,
) -> List[Tuple[int, int]]:
    h, w = bgr_map.shape[:2]
    return [
        (rng.randint(0, w - CAPTURE_W - 1), rng.randint(0, h - CAPTURE_H - 1))
        for _ in range(n)
    ]


def _degrade_crop(
    crop: np.ndarray,
    *,
    scale: float = 1.0,
    overlay_icon: bool = False,
    overlay_border: bool = False,
    jpeg_quality: Optional[int] = None,
    rotation_deg: float = 0.0,
    rng: Optional[random.Random] = None,
) -> np.ndarray:
    """Simulate real-world minimap quirks on a clean crop.

    * ``scale != 1.0`` resamples the crop at that factor and pads/crops back
      to 250x250 — simulates in-game zoom ≠ 1:1 with shipped map.png.
    * ``overlay_icon`` paints a small triangle + circle in the center, the
      way the live minimap draws the player icon.
    * ``overlay_border`` mimics compass ticks and UI edges.
    * ``jpeg_quality`` re-encodes through JPEG at this quality (0–100).
    * ``rotation_deg`` rotates the crop about its center.
    """
    rng = rng or random.Random()
    out = crop.copy()
    h, w = out.shape[:2]

    if abs(scale - 1.0) > 1e-3:
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resized = cv2.resize(out, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.zeros_like(out)
        if scale > 1.0:
            # Too big — center-crop back to (h, w)
            sx = (new_w - w) // 2
            sy = (new_h - h) // 2
            out = resized[sy:sy + h, sx:sx + w]
        else:
            # Too small — pad with gray
            canvas[:] = 80
            sx = (w - new_w) // 2
            sy = (h - new_h) // 2
            canvas[sy:sy + new_h, sx:sx + new_w] = resized
            out = canvas

    if abs(rotation_deg) > 1e-3:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), rotation_deg, 1.0)
        out = cv2.warpAffine(out, M, (w, h), borderValue=80)

    if overlay_icon:
        cx, cy = w // 2, h // 2
        # White triangle + outline, matching the minimap player icon scale
        tri = np.array(
            [[cx, cy - 8], [cx - 7, cy + 6], [cx + 7, cy + 6]], dtype=np.int32
        )
        cv2.fillConvexPoly(out, tri, 255)
        cv2.circle(out, (cx, cy), 11, 30, 1)

    if overlay_border:
        # Thin dark border & four tick marks (N/E/S/W) like the minimap edge.
        cv2.rectangle(out, (0, 0), (w - 1, h - 1), 40, 2)
        for (x, y) in ((w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)):
            cv2.line(out, (x, y), (x, y), 255, 3)

    if jpeg_quality is not None and 1 <= jpeg_quality <= 100:
        ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
        if ok:
            out = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
            if out is None:
                out = crop
    return out


def _run_samples(
    gray_map: np.ndarray,
    origins: Sequence[Tuple[int, int]],
    cfg: MatcherConfig,
    *,
    degrade_kwargs: Optional[dict] = None,
) -> List[Sample]:
    pre_map = feature_matcher.preprocess_image(gray_map, cfg)
    map_det = feature_matcher.build_map_detector(cfg)
    map_kp, map_des = map_det.detectAndCompute(pre_map, None)
    if map_des is None or len(map_kp) == 0:
        return []
    cap_det = feature_matcher.build_capture_detector(cfg)
    matcher = feature_matcher.build_matcher(cfg)

    samples: List[Sample] = []
    for (ox, oy) in origins:
        crop = gray_map[oy:oy + CAPTURE_H, ox:ox + CAPTURE_W]
        gt_cx = ox + CAPTURE_W / 2.0
        gt_cy = oy + CAPTURE_H / 2.0
        if degrade_kwargs:
            crop = _degrade_crop(crop, **degrade_kwargs)
        t0 = time.perf_counter()
        out = feature_matcher.match(
            crop, map_kp, map_des, cfg,
            capture_detector=cap_det, matcher=matcher,
        )
        latency_ms = (time.perf_counter() - t0) * 1000.0
        detected = None
        error = None
        if out.homography is not None:
            center_pt = np.float32([[[CAPTURE_W / 2.0, CAPTURE_H / 2.0]]])
            mapped = cv2.perspectiveTransform(center_pt, out.homography)
            mx, my = float(mapped[0, 0, 0]), float(mapped[0, 0, 1])
            err = ((mx - gt_cx) ** 2 + (my - gt_cy) ** 2) ** 0.5
            if err <= MAX_ACCEPTED_ERROR_PX:
                detected = (mx, my)
                error = err
        samples.append(Sample(
            origin=(ox, oy),
            center=(int(gt_cx), int(gt_cy)),
            detected_center=detected,
            error_px=error,
            detector=cfg.detector.value,
            clahe=cfg.preprocess_clahe,
            latency_ms=latency_ms,
        ))
    return samples


def _save_overlay(
    bgr_map: np.ndarray,
    samples: List[Sample],
    out_path: str,
    label: str,
) -> None:
    """Draw GT centers (green), detected centers (red) with connecting lines."""
    vis = bgr_map.copy()
    for s in samples:
        cx, cy = s.center
        cv2.circle(vis, (cx, cy), 4, (0, 255, 0), -1)
        if s.detected_center is None:
            # Mark missed GT with a red X
            cv2.line(vis, (cx - 6, cy - 6), (cx + 6, cy + 6), (0, 0, 255), 2)
            cv2.line(vis, (cx + 6, cy - 6), (cx - 6, cy + 6), (0, 0, 255), 2)
            continue
        dx, dy = int(s.detected_center[0]), int(s.detected_center[1])
        cv2.circle(vis, (dx, dy), 4, (0, 0, 255), -1)
        cv2.line(vis, (cx, cy), (dx, dy), (255, 255, 255), 1)

    # Legend + label banner
    banner_h = 60
    h, w = vis.shape[:2]
    banner = np.zeros((banner_h, w, 3), dtype=np.uint8)
    cv2.putText(banner, label, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    successes = sum(1 for s in samples if s.detected_center is not None)
    errs = [s.error_px for s in samples if s.error_px is not None]
    median_err = statistics.median(errs) if errs else None
    info = (
        f"success: {successes}/{len(samples)}   "
        f"median error: {'-' if median_err is None else f'{median_err:.2f} px'}   "
        f"(green=ground truth, red=detected, red X=no match)"
    )
    cv2.putText(banner, info, (10, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    stacked = np.vstack([banner, vis])
    cv2.imwrite(out_path, stacked)


def _summary_line(samples: List[Sample]) -> str:
    if not samples:
        return "no samples"
    successes = sum(1 for s in samples if s.detected_center is not None)
    errs = [s.error_px for s in samples if s.error_px is not None]
    lat = [s.latency_ms for s in samples]
    det = samples[0].detector
    tag = "+clahe" if samples[0].clahe else ""
    label = f"{det}{tag}"
    return (
        f"  {label:<12}  "
        f"success={successes:3d}/{len(samples)} ({100*successes/len(samples):5.1f}%)  "
        f"median_err={('-' if not errs else f'{statistics.median(errs):6.2f}px'):>10}  "
        f"p95_err={('-' if not errs else f'{sorted(errs)[min(len(errs)-1, int(0.95*len(errs)))]:6.2f}px'):>10}  "
        f"median_latency={statistics.median(lat):5.1f}ms"
    )


def _build_configs(clahe_both: bool = True) -> List[MatcherConfig]:
    configs = []
    for det in (DetectorType.SIFT, DetectorType.AKAZE, DetectorType.ORB):
        for clahe in ((False, True) if clahe_both else (False,)):
            configs.append(MatcherConfig(detector=det, preprocess_clahe=clahe))
    return configs


def _run_real_capture(
    map_name: str,
    bgr_map: np.ndarray,
    gray_map: np.ndarray,
    capture_path: str,
    no_viz: bool,
) -> None:
    """Single real minimap screenshot → try every detector, save overlays.

    Use this when the user reports position issues: drop the offending
    minimap PNG into e.g. ``dev_tools/test_captures/`` and run::

        python dev_tools/position_accuracy_check.py reload_elite_stronghold \\
            --capture dev_tools/test_captures/bad.png

    You can't compute an automatic error (we don't know where the player
    *actually* was) — but the overlay shows where each detector places the
    crop, so you can visually compare against your remembered position.
    """
    if not os.path.exists(capture_path):
        print(f"capture not found: {capture_path}")
        sys.exit(2)

    cap_bgr = cv2.imread(capture_path, cv2.IMREAD_COLOR)
    if cap_bgr is None:
        print(f"could not read {capture_path}")
        sys.exit(2)
    if cap_bgr.shape[0] != CAPTURE_H or cap_bgr.shape[1] != CAPTURE_W:
        print(
            f"warning: capture is {cap_bgr.shape[1]}x{cap_bgr.shape[0]}, "
            f"expected {CAPTURE_W}x{CAPTURE_H}. Resizing."
        )
        cap_bgr = cv2.resize(cap_bgr, (CAPTURE_W, CAPTURE_H))
    cap_gray = cv2.cvtColor(cap_bgr, cv2.COLOR_BGR2GRAY)

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"# real-capture test: {map_name}  capture={capture_path}\n")
    configs = _build_configs()
    for cfg in configs:
        pre_map = feature_matcher.preprocess_image(gray_map, cfg)
        map_det = feature_matcher.build_map_detector(cfg)
        map_kp, map_des = map_det.detectAndCompute(pre_map, None)
        cap_det = feature_matcher.build_capture_detector(cfg)
        matcher = feature_matcher.build_matcher(cfg)
        t0 = time.perf_counter()
        out = feature_matcher.match(
            cap_gray, map_kp, map_des, cfg,
            capture_detector=cap_det, matcher=matcher,
        )
        latency = (time.perf_counter() - t0) * 1000.0
        tag = f"{cfg.detector.value}{'+clahe' if cfg.preprocess_clahe else ''}"
        if out.homography is None:
            print(
                f"  {tag:<12}  FAILED: {out.failure_reason}  "
                f"(cap_kpts={out.num_capture_keypoints}, "
                f"map_kpts={out.num_map_keypoints}, "
                f"good={out.num_good_matches}, "
                f"latency={latency:.1f}ms)"
            )
            continue
        # Place crop center on map
        center_pt = np.float32([[[CAPTURE_W / 2.0, CAPTURE_H / 2.0]]])
        mapped = cv2.perspectiveTransform(center_pt, out.homography)
        mx, my = float(mapped[0, 0, 0]), float(mapped[0, 0, 1])
        corners = out.corners_on_map
        print(
            f"  {tag:<12}  OK   placed_at=({mx:6.1f}, {my:6.1f})  "
            f"inliers={out.num_inliers}  latency={latency:.1f}ms"
        )
        if no_viz:
            continue
        vis = bgr_map.copy()
        if corners is not None:
            pts = corners.reshape(-1, 2).astype(np.int32)
            cv2.polylines(vis, [pts], True, (0, 0, 255), 2)
        cv2.circle(vis, (int(mx), int(my)), 6, (0, 255, 0), -1)
        out_path = os.path.join(
            OUT_DIR,
            f"{map_name}_realcapture_{tag}.png",
        )
        cv2.imwrite(out_path, vis)
    if not no_viz:
        print(f"\noverlay PNGs saved under {OUT_DIR}/")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("map", help="Map slug (e.g. reload_elite_stronghold)")
    parser.add_argument("-n", "--samples", type=int, default=30,
                        help="Number of crops per config (default 30).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--region", choices=("snow", "random"), default="snow",
                        help="Crop selection strategy (default: snow).")
    parser.add_argument("--manual", nargs=2, type=int, metavar=("X", "Y"),
                        default=None,
                        help="If given, test a single crop whose top-left is at (X, Y).")
    parser.add_argument("--no-viz", action="store_true",
                        help="Skip writing per-config overlay PNGs.")
    parser.add_argument("--degrade", default="clean",
                        choices=("clean", "light", "heavy"),
                        help="Simulate real-world capture degradation. "
                             "clean = synthetic (default), "
                             "light = UI icon + border + mild JPEG, "
                             "heavy = light + scale mismatch + rotation.")
    parser.add_argument("--capture", type=str, default=None,
                        help="Path to a real minimap screenshot (PNG). "
                             "When set, runs every detector against this one "
                             "image and reports where on MAP it's placed — no "
                             "ground truth available, so you have to eyeball "
                             "the overlay PNGs.")
    args = parser.parse_args()

    map_path = os.path.join("maps", f"{args.map}.png")
    if not os.path.exists(map_path):
        print(f"map not found: {map_path}")
        sys.exit(2)

    bgr_map = cv2.imread(map_path, cv2.IMREAD_COLOR)
    gray_map = cv2.cvtColor(bgr_map, cv2.COLOR_BGR2GRAY)

    if args.capture is not None:
        _run_real_capture(args.map, bgr_map, gray_map, args.capture, args.no_viz)
        return

    if args.manual is not None:
        origins = [tuple(args.manual)]
    elif args.region == "snow":
        rng = random.Random(args.seed)
        origins = _sample_snow_origins(bgr_map, args.samples, rng)
        if not origins:
            print(f"No snow-heavy crops found on {args.map}. Try --region random.")
            sys.exit(2)
    else:
        rng = random.Random(args.seed)
        origins = _sample_random_origins(bgr_map, args.samples, rng)

    degrade_kwargs = None
    if args.degrade == "light":
        degrade_kwargs = dict(
            overlay_icon=True,
            overlay_border=True,
            jpeg_quality=80,
        )
    elif args.degrade == "heavy":
        degrade_kwargs = dict(
            scale=0.82,          # in-game zoom shows slightly less ground
            overlay_icon=True,
            overlay_border=True,
            jpeg_quality=70,
            rotation_deg=6.0,    # minor residual rotation
        )

    print(
        f"# position accuracy check: {args.map} "
        f"({len(origins)} crops, region={args.region}, degrade={args.degrade})\n"
    )

    os.makedirs(OUT_DIR, exist_ok=True)
    configs = _build_configs()
    for cfg in configs:
        samples = _run_samples(gray_map, origins, cfg, degrade_kwargs=degrade_kwargs)
        print(_summary_line(samples))
        if not args.no_viz and samples:
            tag = f"{cfg.detector.value}{'+clahe' if cfg.preprocess_clahe else ''}"
            out_path = os.path.join(
                OUT_DIR,
                f"{args.map}_{args.region}_{args.degrade}_{tag}.png",
            )
            label = (
                f"{args.map}  detector={cfg.detector.value}  "
                f"clahe={cfg.preprocess_clahe}  region={args.region}  "
                f"degrade={args.degrade}"
            )
            _save_overlay(bgr_map, samples, out_path, label)
    if not args.no_viz:
        print(f"\nvisualizations saved under {OUT_DIR}/")


if __name__ == "__main__":
    main()
