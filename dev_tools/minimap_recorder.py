"""
Minimap recorder — build a corpus of real in-game minimap captures.

Runs alongside FA11y while you play. On hotkey, grabs the current minimap
crop (250x250 from the PPI capture region), runs every feature detector
against it, and saves a PNG + JSON metadata pair under
``dev_tools/captures/<map_slug>/``.

Why this exists: synthetic crops of our shipped map .pngs match with
sub-pixel accuracy under every algorithm, but users still report position
errors in live play. That means the real-world capture → live rendering →
map.png pipeline has discrepancies we can't simulate. This tool captures
real frames so we can debug them later with
``dev_tools/position_accuracy_check.py --capture``.

Hotkeys:

  F10 - save the current minimap frame
  F11 - save the current frame flagged as BAD (FA11y was wrong on this one)
  Esc - quit

Output layout::

    dev_tools/captures/<map_slug>/
      <iso_timestamp>.png              # raw 250x250 minimap capture
      <iso_timestamp>.json             # metadata (map, detector results, etc.)
      <iso_timestamp>_BAD.png          # if recorded via F11
      <iso_timestamp>_BAD.json

You can feed any of these back into the accuracy checker::

    python dev_tools/position_accuracy_check.py <map_slug> \\
        --capture dev_tools/captures/<map_slug>/<ts>.png
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from mss import mss
from pynput import keyboard

# Path setup so we can import lib/
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
os.chdir(_REPO_ROOT)

from lib.detection import feature_matcher  # noqa: E402
from lib.detection.feature_matcher import DetectorType, MatcherConfig  # noqa: E402
from lib.detection.ppi import (  # noqa: E402
    PPI_CAPTURE_REGION,
    PPI_CAPTURE_REGION_LEGACY,
    _resolve_matcher_config,
)
from lib.utilities.utilities import read_config, get_config_value  # noqa: E402


CAPTURE_ROOT = Path("dev_tools") / "captures"


def _current_map_slug() -> str:
    """Read FA11y's current_map from config — tolerant of the tool not
    having cached a copy yet."""
    try:
        cfg = read_config()
        slug, _ = get_config_value(cfg, "current_map", fallback="main")
        return slug or "main"
    except Exception:
        return "main"


def _current_capture_region(map_slug: str) -> dict:
    """Pick the right PPI capture region for this map.

    Mirrors ``ppi.get_ppi_coordinates`` so a recorder run matches what the
    live game would grab.
    """
    if map_slug == "o_g":
        return PPI_CAPTURE_REGION_LEGACY
    return PPI_CAPTURE_REGION


def _capture_minimap(sct: mss, region: dict) -> np.ndarray:
    """Grab a BGR image of the PPI capture region."""
    raw = np.array(sct.grab({
        "top": region["top"],
        "left": region["left"],
        "width": region["width"],
        "height": region["height"],
    }))  # BGRA
    return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)


def _try_all_detectors(gray_capture: np.ndarray, map_slug: str) -> dict:
    """Run every (detector × clahe) combo against the cached map .png.

    Returns a dict shaped for the metadata JSON. Silently skips detector
    attempts if the map .png isn't present.
    """
    map_path = Path("maps") / f"{map_slug}.png"
    results: dict = {"map_png_exists": map_path.exists(), "attempts": []}
    if not map_path.exists():
        return results

    gray_map = cv2.imread(str(map_path), cv2.IMREAD_GRAYSCALE)
    if gray_map is None:
        results["map_png_read_error"] = True
        return results

    for det in (DetectorType.SIFT, DetectorType.AKAZE, DetectorType.ORB):
        for clahe in (False, True):
            cfg = MatcherConfig(detector=det, preprocess_clahe=clahe)
            pre_map = feature_matcher.preprocess_image(gray_map, cfg)
            map_det = feature_matcher.build_map_detector(cfg)
            map_kp, map_des = map_det.detectAndCompute(pre_map, None)
            t0 = time.perf_counter()
            out = feature_matcher.match(
                gray_capture, map_kp, map_des, cfg,
            )
            latency_ms = (time.perf_counter() - t0) * 1000.0
            mapped_center = None
            if out.homography is not None:
                cap_h, cap_w = gray_capture.shape[:2]
                c = np.float32([[[cap_w / 2.0, cap_h / 2.0]]])
                mapped = cv2.perspectiveTransform(c, out.homography)
                mapped_center = [float(mapped[0, 0, 0]), float(mapped[0, 0, 1])]
            results["attempts"].append({
                "detector": det.value,
                "clahe": clahe,
                "latency_ms": round(latency_ms, 2),
                "num_capture_keypoints": out.num_capture_keypoints,
                "num_map_keypoints": out.num_map_keypoints,
                "num_good_matches": out.num_good_matches,
                "num_inliers": out.num_inliers,
                "mapped_center": mapped_center,
                "failure_reason": out.failure_reason,
            })
    return results


def _effective_config_snapshot(map_slug: str) -> dict:
    """Capture what FA11y *would* do on this map right now."""
    cfg = _resolve_matcher_config(map_slug)
    return {
        "detector": cfg.detector.value,
        "clahe": cfg.preprocess_clahe,
        "lowe_ratio": cfg.lowe_ratio,
        "min_good_matches": cfg.min_good_matches,
    }


def _save_capture(frame_bgr: np.ndarray, bad: bool) -> None:
    """Save PNG + JSON metadata for one captured minimap frame."""
    map_slug = _current_map_slug()
    out_dir = CAPTURE_ROOT / map_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    suffix = "_BAD" if bad else ""
    png_path = out_dir / f"{ts}{suffix}.png"
    json_path = out_dir / f"{ts}{suffix}.json"

    cv2.imwrite(str(png_path), frame_bgr)

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    meta = {
        "timestamp_utc": ts,
        "map_slug": map_slug,
        "bad": bad,
        "capture_region": _current_capture_region(map_slug),
        "effective_config": _effective_config_snapshot(map_slug),
        "capture_shape": [int(gray.shape[0]), int(gray.shape[1])],
        "detector_results": _try_all_detectors(gray, map_slug),
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    label = " [BAD]" if bad else ""
    print(f"captured{label} -> {png_path}")
    # Short per-detector summary to console so user can eyeball live.
    for attempt in meta["detector_results"].get("attempts", []):
        tag = f"{attempt['detector']}{'+clahe' if attempt['clahe'] else ''}"
        if attempt.get("mapped_center"):
            cx, cy = attempt["mapped_center"]
            print(f"  {tag:<12}  placed @ ({cx:6.1f}, {cy:6.1f})  "
                  f"inliers={attempt['num_inliers']}  "
                  f"latency={attempt['latency_ms']}ms")
        else:
            print(f"  {tag:<12}  FAILED: {attempt.get('failure_reason')}")


class Recorder:
    """Background capture thread + hotkey listener."""

    def __init__(self) -> None:
        self._running = False
        self._lock = threading.Lock()
        self._latest: Optional[np.ndarray] = None
        self._latest_region: Optional[dict] = None
        self._thread: Optional[threading.Thread] = None
        self._listener: Optional[keyboard.Listener] = None
        self._last_press_ts = 0.0

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.start()

    def _capture_loop(self) -> None:
        """Continuously grab the current minimap region so the hotkey
        handler has a fresh frame without blocking on mss."""
        sct = mss()
        try:
            while self._running:
                slug = _current_map_slug()
                region = _current_capture_region(slug)
                try:
                    frame = _capture_minimap(sct, region)
                except Exception:
                    time.sleep(0.05)
                    continue
                with self._lock:
                    self._latest = frame
                    self._latest_region = region
                time.sleep(1.0 / 30.0)
        finally:
            try:
                sct.close()
            except Exception:
                pass

    def _on_press(self, key) -> Optional[bool]:
        # Debounce — pynput fires repeat events while the key is held.
        now = time.time()
        if now - self._last_press_ts < 0.25:
            return None
        if key == keyboard.Key.esc:
            self._running = False
            return False  # stop listener
        if key == keyboard.Key.f10:
            self._last_press_ts = now
            self._grab_and_save(bad=False)
        elif key == keyboard.Key.f11:
            self._last_press_ts = now
            self._grab_and_save(bad=True)
        return None

    def _grab_and_save(self, *, bad: bool) -> None:
        with self._lock:
            frame = None if self._latest is None else self._latest.copy()
        if frame is None:
            print("no frame captured yet — is the game focused?")
            return
        try:
            _save_capture(frame, bad=bad)
        except Exception as e:
            print(f"save failed: {e}")

    def stop(self) -> None:
        self._running = False
        if self._listener is not None:
            self._listener.stop()


def main() -> None:
    print("FA11y minimap recorder — running (Esc to quit)")
    print(f"  F10 - save current minimap frame")
    print(f"  F11 - save current minimap frame, flagged BAD")
    print(f"  captures go under {CAPTURE_ROOT}/<map_slug>/")
    rec = Recorder()
    rec.start()
    try:
        while rec._running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        rec.stop()


if __name__ == "__main__":
    main()
