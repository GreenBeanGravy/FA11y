"""
FA11y Feature-Match Benchmark

Compares SIFT / AKAZE / ORB (with and without CLAHE preprocessing) against
every map .png in ``maps/``. Since we don't have real minimap captures here,
the harness fabricates "synthetic captures" by cropping random 250x250
regions out of each map — this simulates a perfect in-game minimap match
(no UI overlay, no lossy scaling, exact terrain).

What the bench reports per (map, detector, clahe) tuple:

* ``success_rate``   — fraction of crops that produced a valid homography
* ``median_inliers`` — median RANSAC inlier count on successful matches
* ``median_reproj_px`` — how close the homography put the recovered crop
  corners to the ground-truth crop origin (pixels; lower is better)
* ``median_ms``      — per-frame capture-side detect+match+homography time

Usage::

    python dev_tools/feature_match_bench.py                 # all maps, all algos
    python dev_tools/feature_match_bench.py reload_venture  # single map
    python dev_tools/feature_match_bench.py --csv out.csv   # dump CSV

Synthetic captures are not a substitute for real in-game minimap data — UI
overlays, zoom mismatch, compression, and partial occlusion all change
real-world match quality. But relative ranking between algorithms on the
same terrain is a reasonable proxy, and absolute rates here serve as an
upper bound for real-world performance.
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

# Let us import from lib/ without being installed as a package.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
os.chdir(_REPO_ROOT)

from lib.detection import feature_matcher  # noqa: E402
from lib.detection.feature_matcher import (  # noqa: E402
    DetectorType, MatcherConfig,
)


# Capture size matches what PPI actually grabs in-game.
CAPTURE_W = 250
CAPTURE_H = 250
DEFAULT_NUM_SAMPLES = 20
DEFAULT_RANDOM_SEED = 42


@dataclass
class BenchRow:
    map_name: str
    detector: str
    clahe: bool
    samples: int
    successes: int
    median_inliers: Optional[float]
    median_reproj_px: Optional[float]
    median_ms: Optional[float]
    median_capture_kpts: Optional[float]
    map_kpts: int

    @property
    def success_rate(self) -> float:
        return 0.0 if self.samples == 0 else self.successes / self.samples

    @property
    def label(self) -> str:
        tag = "+clahe" if self.clahe else ""
        return f"{self.detector}{tag}"


def _list_maps() -> List[Tuple[str, str]]:
    """Return [(slug, png_path)] for every map .png in maps/."""
    pairs: List[Tuple[str, str]] = []
    for p in sorted(glob.glob("maps/*.png")):
        slug = os.path.splitext(os.path.basename(p))[0]
        pairs.append((slug, p))
    return pairs


def _sample_crop_origins(map_img: np.ndarray, n: int, rng: random.Random
                         ) -> List[Tuple[int, int]]:
    h, w = map_img.shape[:2]
    max_x = w - CAPTURE_W - 1
    max_y = h - CAPTURE_H - 1
    if max_x <= 0 or max_y <= 0:
        return []
    return [(rng.randint(0, max_x), rng.randint(0, max_y)) for _ in range(n)]


def _run_one(map_name: str, map_path: str, cfg: MatcherConfig,
             samples: int, rng: random.Random) -> BenchRow:
    gray = cv2.imread(map_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        return BenchRow(
            map_name=map_name, detector=cfg.detector.value, clahe=cfg.preprocess_clahe,
            samples=0, successes=0, median_inliers=None, median_reproj_px=None,
            median_ms=None, median_capture_kpts=None, map_kpts=0,
        )

    # Precompute map-side keypoints/descriptors — mirrors the MapManager cache.
    pre_map = feature_matcher.preprocess_image(gray, cfg)
    map_det = feature_matcher.build_map_detector(cfg)
    map_kp, map_des = map_det.detectAndCompute(pre_map, None)
    if map_des is None or len(map_kp) == 0:
        return BenchRow(
            map_name=map_name, detector=cfg.detector.value, clahe=cfg.preprocess_clahe,
            samples=samples, successes=0, median_inliers=None, median_reproj_px=None,
            median_ms=None, median_capture_kpts=None, map_kpts=0,
        )

    # Reusable per-call pieces.
    cap_det = feature_matcher.build_capture_detector(cfg)
    matcher = feature_matcher.build_matcher(cfg)

    origins = _sample_crop_origins(gray, samples, rng)
    inliers: List[int] = []
    reproj_errs: List[float] = []
    latencies: List[float] = []
    cap_kpts: List[int] = []
    successes = 0

    for (ox, oy) in origins:
        crop = gray[oy:oy + CAPTURE_H, ox:ox + CAPTURE_W]
        t0 = time.perf_counter()
        out = feature_matcher.match(
            crop, map_kp, map_des, cfg,
            capture_detector=cap_det, matcher=matcher,
        )
        latencies.append((time.perf_counter() - t0) * 1000.0)
        if out.num_capture_keypoints:
            cap_kpts.append(out.num_capture_keypoints)

        if out.corners_on_map is None or out.homography is None:
            continue

        # Reprojection error: transform crop origin (0,0) via homography,
        # compare to ground-truth (ox, oy).
        pt = np.float32([[[0.0, 0.0]]])
        mapped = cv2.perspectiveTransform(pt, out.homography)
        mx, my = float(mapped[0, 0, 0]), float(mapped[0, 0, 1])
        err = ((mx - ox) ** 2 + (my - oy) ** 2) ** 0.5
        # Reject wildly wrong matches (>50 px) as not a success.
        if err <= 50.0:
            successes += 1
            inliers.append(out.num_inliers)
            reproj_errs.append(err)

    def _median(xs):
        return statistics.median(xs) if xs else None

    return BenchRow(
        map_name=map_name,
        detector=cfg.detector.value,
        clahe=cfg.preprocess_clahe,
        samples=samples,
        successes=successes,
        median_inliers=_median(inliers),
        median_reproj_px=_median(reproj_errs),
        median_ms=_median(latencies),
        median_capture_kpts=_median(cap_kpts),
        map_kpts=len(map_kp),
    )


def _build_configs() -> List[MatcherConfig]:
    """Six configs: each detector with and without CLAHE."""
    out = []
    for det in (DetectorType.SIFT, DetectorType.AKAZE, DetectorType.ORB):
        for clahe in (False, True):
            out.append(MatcherConfig(detector=det, preprocess_clahe=clahe))
    return out


def _format_row(r: BenchRow) -> str:
    inl = f"{r.median_inliers:5.0f}" if r.median_inliers is not None else "   - "
    reproj = f"{r.median_reproj_px:5.2f}" if r.median_reproj_px is not None else "   - "
    ms = f"{r.median_ms:5.1f}" if r.median_ms is not None else "   - "
    ckp = f"{r.median_capture_kpts:5.0f}" if r.median_capture_kpts is not None else "   - "
    rate = f"{r.success_rate * 100:5.1f}%"
    return (
        f"  {r.label:<12}  "
        f"success={rate}  "
        f"inliers={inl}  "
        f"reproj={reproj}px  "
        f"latency={ms}ms  "
        f"cap_kpts={ckp}  "
        f"map_kpts={r.map_kpts}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("map", nargs="?", default=None,
                        help="Slug of a single map to bench (default: all maps in maps/).")
    parser.add_argument("-n", "--samples", type=int, default=DEFAULT_NUM_SAMPLES,
                        help=f"Number of random crops per (map, config). Default {DEFAULT_NUM_SAMPLES}.")
    parser.add_argument("--seed", type=int, default=DEFAULT_RANDOM_SEED,
                        help=f"Random seed (default {DEFAULT_RANDOM_SEED}).")
    parser.add_argument("--csv", type=str, default=None,
                        help="Write full results to this CSV path.")
    args = parser.parse_args()

    all_maps = _list_maps()
    if args.map:
        all_maps = [(slug, path) for (slug, path) in all_maps if slug == args.map]
        if not all_maps:
            print(f"No map found with slug {args.map!r}")
            sys.exit(2)

    configs = _build_configs()

    print(f"# FA11y feature-match bench — {args.samples} synthetic crops/config, seed={args.seed}\n")
    rows: List[BenchRow] = []
    for slug, path in all_maps:
        print(f"[{slug}]")
        # Fresh RNG per map so config comparisons are fair within a map.
        for cfg in configs:
            rng = random.Random(args.seed)
            row = _run_one(slug, path, cfg, args.samples, rng)
            rows.append(row)
            print(_format_row(row))
        # Highlight winner by success rate (ties broken by lower reproj error).
        map_rows = [r for r in rows if r.map_name == slug]
        if map_rows:
            winner = max(
                map_rows,
                key=lambda r: (r.success_rate,
                               -(r.median_reproj_px if r.median_reproj_px is not None else 1e9)),
            )
            print(f"  winner: {winner.label}\n")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                "map", "detector", "clahe", "samples", "successes",
                "success_rate", "median_inliers", "median_reproj_px",
                "median_ms", "median_capture_kpts", "map_kpts",
            ])
            for r in rows:
                w.writerow([
                    r.map_name, r.detector, r.clahe, r.samples, r.successes,
                    f"{r.success_rate:.4f}",
                    "" if r.median_inliers is None else f"{r.median_inliers:.2f}",
                    "" if r.median_reproj_px is None else f"{r.median_reproj_px:.3f}",
                    "" if r.median_ms is None else f"{r.median_ms:.3f}",
                    "" if r.median_capture_kpts is None else f"{r.median_capture_kpts:.2f}",
                    r.map_kpts,
                ])
        print(f"wrote {args.csv}")


if __name__ == "__main__":
    main()
