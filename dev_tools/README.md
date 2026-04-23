# FA11y Developer Tools

Standalone utilities for working on FA11y. **Not imported by the runtime
application** — these are scripts you run manually from the repo root when
you're developing or debugging.

## Rules

1. Every script here is runnable as `python dev_tools/<name>.py`.
2. Scripts here may import from `lib/`, but `lib/` must never import from
   `dev_tools/`.
3. Scripts should be single-file and self-contained where possible.

## Available tools

| Script | Purpose |
|---|---|
| `pixel_picker.py` | Click-through magnifier overlay. Reads pixel colors and coordinates the way FA11y sees them (via `mss`). `F8` toggle, `C` copy, `Esc` quit. |
| `clear_pycache.py` | Recursively deletes every `__pycache__` folder under the repo. |
| `health_shield_debugger.py` | Live visualization of health/shield bar detection. Interactively tune start positions, tolerance, and decrease pattern. |
| `health_calibrator.py` | Auto-calibrate the health-bar decrease pattern. Steps through HP values 100→1, writing `health_calibration.json` when done. |
| `ppi_configurator.py` | Visualize and tune PPI (minimap SIFT matching). Tweaks capture region, Lowe ratio, min matches; shows keypoints and match lines live. |
| `direction_configurator.py` | Visualize and tune minimap icon direction detection (contour + triangle-tip arctan2). |
| `feature_match_bench.py` | Benchmark SIFT / AKAZE / ORB (with / without CLAHE) against every map by sampling synthetic 250×250 crops. Reports success rate, median reprojection error, latency per (map, detector) pair. Use to pick per-map detector overrides (`coordinate_config.MAP_MATCHER_OVERRIDES`). |
| `position_accuracy_check.py` | Targeted accuracy test for a single map. Samples crops from snow-heavy regions (`--region snow`) or random regions, optionally degrades them (`--degrade light/heavy`) to simulate in-game UI overlay / scale / rotation / JPEG compression, and writes overlay PNGs under `dev_tools/position_accuracy_out/`. Has a `--capture <path>` mode to run all detectors against a real in-game minimap screenshot. |
| `minimap_recorder.py` | Run alongside FA11y during live play. `F10` saves the current minimap frame to `dev_tools/captures/<map_slug>/`; `F11` saves it flagged BAD (for when FA11y got your position wrong). Each capture also writes a JSON sidecar with every detector's result on that frame. Feed the saved PNGs into `position_accuracy_check.py --capture` to debug offline. |
| `clientsettings_roundtrip.py` | Download the authenticated user's cloud `ClientSettings.Sav`, parse + re-serialize it, and report byte-level differences. Optional `--edit Name=Value` to include a scalar edit. Use to diagnose why Fortnite rejects our edits. Outputs under `dev_tools/clientsettings_diag/`. |

## Adding a new tool

1. Drop a single `<name>.py` file in this folder.
2. Put a usage block at the top (`"""docstring"""`) with controls/flags.
3. Add a row to the table above.
4. If it needs FA11y's config or detection code, import from `lib/` — don't
   duplicate logic.
