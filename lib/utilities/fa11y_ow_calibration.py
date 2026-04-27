"""Per-map calibration that lets FA11y-OW's GEP `location` event substitute
for FA11y's visual minimap detection.

Workflow:
    1. User opens the full map (PPI needs the map screen on-screen).
    2. User binds and triggers ``Calibrate FA11y-OW Position`` while
       standing at three distinct points. Each press records the FA11y
       PPI coordinate and the corresponding GEP location simultaneously.
    3. After the third sample we solve for the 2-D affine transform
        OW (x, y) -> FA11y (px, py)
       and persist it to ``config/fa11y_ow_calibration.json`` keyed by
       the map name.

GEP's `location` is documented as a 0-3000 grid (top-left = 0,0;
bottom-right = 3000,3000) but FA11y stores minimap coords in pixel
units that depend on each map's image resolution and ROI. A per-map
affine handles both scale and any axis-flip / origin offset between
the two systems without us having to model them.

Once the transform exists, ``transform_ow_to_fa11y`` returns the same
shape as PPI's ``find_player_position`` — an ``(int, int)`` tuple — so
callers can treat it as a drop-in replacement.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_FILE_PATH = os.path.join('config', 'fa11y_ow_calibration.json')
# Bundled with FA11y so users have a working transform out of the box.
# User calibrations in _FILE_PATH override per-map; ``_DEFAULT_KEY`` is
# the catch-all entry — every Fortnite map shares the same screen scale
# and rotation in FA11y's ROI, so one transform covers them all.
_DEFAULTS_PATH = os.path.join('lib', 'data', 'default_calibrations.json')
_DEFAULT_KEY = '_default'
_REQUIRED_SAMPLES = 3
# Reject sample sets where the OW points are nearly colinear — the affine
# matrix is well-defined mathematically (det ~= 0 still solves) but the
# transform is unstable and any extrapolation will be wrong by orders of
# magnitude. 0.5 in 0-3000 space is forgiving (about a few pixels).
_MIN_DETERMINANT = 0.5


Point2 = Tuple[float, float]
SamplePair = Tuple[Point2, Point2]   # (ow_xy, fa11y_xy)


class CalibrationManager:
    def __init__(
        self,
        file_path: str = _FILE_PATH,
        defaults_path: str = _DEFAULTS_PATH,
    ):
        self._file_path = file_path
        self._defaults_path = defaults_path
        self._lock = threading.RLock()
        # Bundled defaults ship with FA11y so common maps work out of the
        # box. User calibrations override per-map. Stored separately so a
        # save() doesn't bake the bundled defaults into the user file —
        # that would freeze them at the user's installed version even if
        # we ship updated defaults later.
        self._defaults: Dict[str, dict] = self._load_file(self._defaults_path)
        self._user: Dict[str, dict] = self._load_file(self._file_path)
        # Pending samples are kept in memory only — we don't want a
        # half-finished calibration to survive a crash.
        self._pending: Dict[str, List[SamplePair]] = {}

    # --- persistence ----------------------------------------------------

    @staticmethod
    def _load_file(path: str) -> Dict[str, dict]:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("calibration: failed to load %s: %s", path, e)
            return {}

    def _save_user(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._file_path) or '.', exist_ok=True)
            with open(self._file_path, 'w', encoding='utf-8') as f:
                json.dump(self._user, f, indent=2)
        except OSError as e:
            logger.warning("calibration: failed to save %s: %s", self._file_path, e)

    def _resolve(self, map_name: str) -> Optional[dict]:
        """Lookup priority: user-specific -> bundled-specific ->
        user-default -> bundled-default. The default entries
        (``_DEFAULT_KEY``) act as a universal fallback because every
        Fortnite map is rendered at the same scale / rotation."""
        return (
            self._user.get(map_name)
            or self._defaults.get(map_name)
            or self._user.get(_DEFAULT_KEY)
            or self._defaults.get(_DEFAULT_KEY)
        )

    # --- public API -----------------------------------------------------

    def has_calibration(self, map_name: str) -> bool:
        with self._lock:
            return self._resolve(map_name) is not None

    def calibrated_maps(self) -> List[str]:
        with self._lock:
            # De-dupe across user + defaults.
            return sorted(set(self._user.keys()) | set(self._defaults.keys()))

    def pending_count(self, map_name: str) -> int:
        with self._lock:
            return len(self._pending.get(map_name, []))

    def reset_pending(self, map_name: Optional[str] = None) -> None:
        with self._lock:
            if map_name is None:
                self._pending.clear()
            else:
                self._pending.pop(map_name, None)

    def remove(self, map_name: str) -> bool:
        """Remove the user override for ``map_name``. The bundled default,
        if any, remains in effect afterwards."""
        with self._lock:
            existed = map_name in self._user
            self._user.pop(map_name, None)
            self._pending.pop(map_name, None)
            if existed:
                self._save_user()
            return existed

    def add_sample(
        self,
        ow_pos: Point2,
        fa11y_pos: Point2,
        save_key: str = _DEFAULT_KEY,
    ) -> Tuple[int, bool, str]:
        """Record a calibration sample.

        Saves to ``save_key`` once three samples have been captured.
        Defaults to the universal ``_default`` slot — one calibration
        covers every map. Pass a specific map name only if you want a
        per-map override.

        Returns ``(captured_count, complete, message)``.
        """
        with self._lock:
            samples = self._pending.setdefault(save_key, [])
            samples.append((tuple(ow_pos), tuple(fa11y_pos)))
            n = len(samples)

            if n < _REQUIRED_SAMPLES:
                return n, False, (
                    f"Calibration sample {n} of {_REQUIRED_SAMPLES} captured. "
                    f"Move to a different position and press the keybind again."
                )

            # n == _REQUIRED_SAMPLES → fit.
            try:
                matrix, det = self._fit(samples)
            except np.linalg.LinAlgError:
                self._pending[save_key] = []
                return n, False, (
                    "Calibration failed: the three positions were colinear. "
                    "Try again with points spread out across the map."
                )

            if abs(det) < _MIN_DETERMINANT:
                self._pending[save_key] = []
                return n, False, (
                    "Calibration failed: the three positions were too close "
                    "together. Try again with points spread out across the map."
                )

            self._user[save_key] = {
                'matrix': matrix.tolist(),
                'samples': [
                    {'ow': list(s[0]), 'fa11y': list(s[1])} for s in samples
                ],
                'calibrated_at': datetime.utcnow().isoformat() + 'Z',
            }
            self._save_user()
            self._pending[save_key] = []
            if save_key == _DEFAULT_KEY:
                msg = "Calibration complete. Applies to every map."
            else:
                msg = f"Calibration complete for {save_key}."
            return n, True, msg

    def transform_ow_to_fa11y(
        self,
        ow_pos: Point2,
        map_name: str,
    ) -> Optional[Tuple[int, int]]:
        """Apply the saved affine to ``ow_pos`` and return ``(int, int)``
        FA11y minimap coords, or ``None`` if no calibration exists."""
        with self._lock:
            entry = self._resolve(map_name)
            if not entry:
                return None
            matrix = np.array(entry['matrix'])
        v = np.array([ow_pos[0], ow_pos[1], 1.0])
        result = matrix @ v
        return int(round(result[0])), int(round(result[1]))

    # --- math -----------------------------------------------------------

    @staticmethod
    def _fit(samples: List[SamplePair]) -> Tuple[np.ndarray, float]:
        """Solve the 2-D affine transform from three (ow, fa11y) pairs.

        Returns ``(matrix, abs_determinant_of_input)``. Raises
        ``np.linalg.LinAlgError`` if the OW points are colinear.
        """
        # Each sample contributes one row [ow_x, ow_y, 1]. The right-hand
        # side is the FA11y coord. Solve once per output axis.
        A = np.array([[s[0][0], s[0][1], 1.0] for s in samples])
        bx = np.array([s[1][0] for s in samples])
        by = np.array([s[1][1] for s in samples])
        row_x = np.linalg.solve(A, bx)
        row_y = np.linalg.solve(A, by)
        return np.array([row_x, row_y]), float(np.linalg.det(A))


# Module-level singleton.
calibration_manager = CalibrationManager()


# ---------------------------------------------------------------------------
# Keybind action: capture one sample, fit when 3 are gathered.
# ---------------------------------------------------------------------------

def calibrate_fa11y_ow_position() -> None:
    """Action handler for the ``Calibrate FA11y-OW Position`` keybind."""
    from accessible_output2.outputs.auto import Auto

    speaker = Auto()

    # Imports kept local so the calibration module stays cheap to import.
    from lib.utilities.utilities import read_config
    from lib.utilities.fa11y_ow_client import client as ow_client

    if not ow_client.is_connected():
        speaker.speak(
            "FA11y-OW is not connected. Start FA11y-OW and join a match before calibrating."
        )
        return

    state = ow_client.get_state()
    location = state.get('location') or {}
    ow_x = location.get('x')
    ow_y = location.get('y')
    if ow_x is None or ow_y is None or (ow_x == 0 and ow_y == 0):
        speaker.speak(
            "FA11y-OW has no location yet. Make sure you are in an active match."
        )
        return

    # Visual position. PPI needs the full map open on-screen.
    # Bypass the find_player_position() wrapper here on purpose: the
    # wrapper short-circuits to the OW-derived position when a calibration
    # already exists, which would make a recalibration just re-fit the old
    # transform against itself. We always want fresh PPI samples.
    from lib.detection.ppi import find_player_position as _ppi_find
    fa11y_pos = _ppi_find()
    if not fa11y_pos:
        speaker.speak(
            "FA11y could not detect your position. Open the full map first, then press the keybind."
        )
        return

    # find_player_position can return either ``(x, y)`` (PPI) or
    # ``((x, y), angle)`` from older code paths; handle both.
    if (
        len(fa11y_pos) == 2
        and isinstance(fa11y_pos[0], tuple)
    ):
        fa11y_xy = fa11y_pos[0]
    else:
        fa11y_xy = fa11y_pos

    _, complete, message = calibration_manager.add_sample(
        (float(ow_x), float(ow_y)),
        (float(fa11y_xy[0]), float(fa11y_xy[1])),
    )
    speaker.speak(message)
    logger.info(
        "calibration sample ow=%s fa11y=%s complete=%s",
        (ow_x, ow_y), tuple(fa11y_xy), complete,
    )


# ---------------------------------------------------------------------------
# Helper for callers that want OW-derived position with visual fallback.
# ---------------------------------------------------------------------------

def get_position_from_ow() -> Optional[Tuple[int, int]]:
    """Return FA11y-coord position derived from FA11y-OW's GEP location, or
    ``None`` if the helper isn't connected, no calibration exists for the
    current map, or no location is available.

    Caller is responsible for the visual fallback when this returns ``None``.
    """
    from lib.utilities.utilities import read_config
    from lib.utilities.fa11y_ow_client import client as ow_client

    if not ow_client.is_connected():
        return None

    state = ow_client.get_state()
    location = state.get('location') or {}
    ow_x = location.get('x')
    ow_y = location.get('y')
    if ow_x is None or ow_y is None or (ow_x == 0 and ow_y == 0):
        return None

    cfg = read_config()
    map_name = cfg.get('POI', 'current_map', fallback='main')
    return calibration_manager.transform_ow_to_fa11y(
        (float(ow_x), float(ow_y)), map_name
    )
