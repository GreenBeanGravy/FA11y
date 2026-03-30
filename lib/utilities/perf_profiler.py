"""
Performance profiler for FA11y.

Two modes:
  --benchmark   One-shot navigation pipeline benchmark (save to txt)
  --profile     Real-time per-function profiling across ALL modules (live + save)

Usage:
    python FA11y.py --benchmark              # Single navigation cycle
    python FA11y.py --benchmark --runs 5     # 5 cycles
    python FA11y.py --profile                # Normal FA11y with live profiling
    python FA11y.py --profile --interval 10  # Print summary every 10s (default 15)

All profiling is zero-cost when neither flag is passed.
"""
import time
import os
import sys
import atexit
import threading
import functools
import statistics
from datetime import datetime
from typing import Optional, List, Dict, Callable
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════════════
#  Shared state
# ═══════════════════════════════════════════════════════════════════════

_enabled = False        # True for --benchmark mode
_profile_enabled = False  # True for --profile mode
_output_file = "benchmark_results.txt"
_profile_file = "profile_results.txt"

# ── Benchmark (--benchmark) state ────────────────────────────────────
_current_run: Optional[Dict] = None
_all_runs: List[Dict] = []
_lock = threading.Lock()

# ── Profile (--profile) state ────────────────────────────────────────
_func_stats: Dict[str, List[float]] = defaultdict(list)  # name -> [durations_ms]
_func_stats_lock = threading.Lock()
_profile_start_time: Optional[float] = None
_profile_interval = 15.0  # seconds between live summary prints
_profile_timer: Optional[threading.Timer] = None
_call_counts_since_print: Dict[str, int] = defaultdict(int)


def enable(output_file: str = "benchmark_results.txt"):
    """Enable --benchmark mode."""
    global _enabled, _output_file
    _enabled = True
    _output_file = output_file


def enable_profile(output_file: str = "profile_results.txt", interval: float = 15.0):
    """Enable --profile mode with live periodic summaries."""
    global _profile_enabled, _profile_file, _profile_interval, _profile_start_time
    _profile_enabled = True
    _profile_file = output_file
    _profile_interval = interval
    _profile_start_time = time.perf_counter()
    _schedule_profile_print()
    atexit.register(save_profile_results)
    print(f"[PROFILE] Live profiling enabled. Summary every {interval:.0f}s. Output -> {output_file}")


def is_enabled() -> bool:
    return _enabled


def is_profile_enabled() -> bool:
    return _profile_enabled


def start_run(label: str = ""):
    """Begin a new profiling run (one full navigation cycle)."""
    global _current_run
    if not _enabled:
        return
    with _lock:
        _current_run = {
            "label": label,
            "start": time.perf_counter(),
            "steps": [],
            "end": None,
        }


def mark(step_name: str):
    """Record a named timestamp within the current run."""
    if not _enabled or _current_run is None:
        return
    with _lock:
        _current_run["steps"].append((step_name, time.perf_counter()))


def end_run():
    """Finish the current run and store it."""
    global _current_run
    if not _enabled or _current_run is None:
        return
    with _lock:
        _current_run["end"] = time.perf_counter()
        _all_runs.append(_current_run)
        _current_run = None


def save_results():
    """Write all collected runs to the output file."""
    if not _enabled or not _all_runs:
        return

    lines = []
    lines.append("=" * 80)
    lines.append(f"  FA11y Navigation Pipeline Benchmark")
    lines.append(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"  Runs: {len(_all_runs)}")
    lines.append("=" * 80)

    # Per-run breakdown
    for i, run in enumerate(_all_runs):
        run_start = run["start"]
        run_end = run["end"] or run_start
        total_ms = (run_end - run_start) * 1000
        label = run["label"] or f"Run {i+1}"

        lines.append(f"\n--- {label} (total: {total_ms:.1f}ms) ---")
        lines.append(f"  {'Step':<45} {'Elapsed':>8}  {'Cumulative':>10}")
        lines.append(f"  {'-'*65}")

        prev_t = run_start
        for step_name, step_t in run["steps"]:
            delta_ms = (step_t - prev_t) * 1000
            cumul_ms = (step_t - run_start) * 1000
            lines.append(f"  {step_name:<45} {delta_ms:>7.2f}ms  {cumul_ms:>9.2f}ms")
            prev_t = step_t

        # Final delta to end
        if run["end"] and run["steps"]:
            last_step_t = run["steps"][-1][1]
            final_delta = (run["end"] - last_step_t) * 1000
            lines.append(f"  {'(end of run)':<45} {final_delta:>7.2f}ms  {total_ms:>9.2f}ms")

    # Summary across runs
    if len(_all_runs) > 1:
        lines.append(f"\n{'=' * 80}")
        lines.append(f"  SUMMARY ACROSS {len(_all_runs)} RUNS")
        lines.append(f"{'=' * 80}")

        totals = [(r["end"] - r["start"]) * 1000 for r in _all_runs if r["end"]]
        if totals:
            import statistics
            lines.append(f"  Total time:  min={min(totals):.1f}ms  avg={statistics.mean(totals):.1f}ms  max={max(totals):.1f}ms")
            if len(totals) > 1:
                lines.append(f"               stdev={statistics.stdev(totals):.1f}ms")

        # Per-step averages
        step_names = []
        if _all_runs[0]["steps"]:
            step_names = [s[0] for s in _all_runs[0]["steps"]]

        if step_names:
            lines.append(f"\n  {'Step':<45} {'Avg':>8}  {'Min':>8}  {'Max':>8}")
            lines.append(f"  {'-'*75}")

            for sname in step_names:
                deltas = []
                for run in _all_runs:
                    steps = run["steps"]
                    for j, (name, t) in enumerate(steps):
                        if name == sname:
                            prev = run["start"] if j == 0 else steps[j-1][1]
                            deltas.append((t - prev) * 1000)
                            break
                if deltas:
                    avg = statistics.mean(deltas)
                    mn = min(deltas)
                    mx = max(deltas)
                    lines.append(f"  {sname:<45} {avg:>7.2f}ms  {mn:>7.2f}ms  {mx:>7.2f}ms")

    text = "\n".join(lines) + "\n"

    with open(_output_file, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"\nBenchmark results saved to: {os.path.abspath(_output_file)}")
    print(text)


# ═══════════════════════════════════════════════════════════════════════
#  --profile mode: per-function decorator and live summaries
# ═══════════════════════════════════════════════════════════════════════

def profile_func(name: Optional[str] = None):
    """Decorator that records per-call timing when --profile is active.

    Usage:
        @profile_func()                     # auto-names as "module.func"
        @profile_func("ppi.find_position")  # explicit name
        def my_function(...):
            ...

    Zero overhead when profiling is disabled — the decorator returns
    the original function unwrapped at decoration time.
    """
    def decorator(fn: Callable) -> Callable:
        # Early exit: if profile isn't enabled at import time, return unwrapped.
        # Functions decorated before enable_profile() is called will NOT be tracked.
        # That's fine — we re-decorate after enable_profile() in the module hooks.
        if not _profile_enabled:
            # Store the label so we can re-wrap later
            fn._profile_name = name or f"{fn.__module__}.{fn.__qualname__}"
            return fn

        label = name or f"{fn.__module__}.{fn.__qualname__}"

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                with _func_stats_lock:
                    _func_stats[label].append(elapsed_ms)
                    _call_counts_since_print[label] += 1
        return wrapper
    return decorator


def record_call(name: str, elapsed_ms: float):
    """Manually record a function call timing (for cases where decorator doesn't fit)."""
    if not _profile_enabled:
        return
    with _func_stats_lock:
        _func_stats[name].append(elapsed_ms)
        _call_counts_since_print[name] += 1


def wrap_function(fn: Callable, name: Optional[str] = None) -> Callable:
    """Wrap an existing function with profiling. Use when you can't use the decorator.

    Returns the original function if profiling is disabled.
    """
    if not _profile_enabled:
        return fn

    label = name or f"{fn.__module__}.{fn.__qualname__}"

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            with _func_stats_lock:
                _func_stats[label].append(elapsed_ms)
                _call_counts_since_print[label] += 1
    return wrapper


def _schedule_profile_print():
    """Schedule the next periodic summary print."""
    global _profile_timer
    if not _profile_enabled:
        return
    _profile_timer = threading.Timer(_profile_interval, _print_profile_summary)
    _profile_timer.daemon = True
    _profile_timer.start()


def _print_profile_summary():
    """Print a live summary of profiled function calls since last print."""
    if not _profile_enabled:
        return

    with _func_stats_lock:
        if not _call_counts_since_print:
            _schedule_profile_print()
            return

        elapsed_total = time.perf_counter() - _profile_start_time
        lines = []
        lines.append(f"\n[PROFILE] Live summary @ {elapsed_total:.0f}s uptime")
        lines.append(f"  {'Function':<50} {'Calls':>6} {'Avg':>8} {'Min':>8} {'Max':>8} {'Total':>9}")
        lines.append(f"  {'-'*95}")

        # Sort by total time descending
        entries = []
        for fname, count in _call_counts_since_print.items():
            all_times = _func_stats[fname]
            recent = all_times[-count:] if count <= len(all_times) else all_times
            if recent:
                entries.append((fname, count, recent))

        entries.sort(key=lambda e: sum(e[2]), reverse=True)

        for fname, count, recent in entries:
            avg = statistics.mean(recent)
            mn = min(recent)
            mx = max(recent)
            total = sum(recent)
            lines.append(f"  {fname:<50} {count:>6} {avg:>7.2f}ms {mn:>7.2f}ms {mx:>7.2f}ms {total:>8.1f}ms")

        # Reset recent counts
        _call_counts_since_print.clear()

    print("\n".join(lines))

    # Save full results to disk each interval so data survives crashes / os._exit()
    save_profile_results()

    _schedule_profile_print()


def save_profile_results():
    """Write final profile summary to file. Called from signal handler and finally blocks.

    Must be safe to call from a signal handler context — no locks that could deadlock,
    minimal allocations, flush+sync to survive os._exit() immediately after.
    """
    if not _profile_enabled:
        return

    # Cancel pending timer
    global _profile_timer
    try:
        if _profile_timer:
            _profile_timer.cancel()
    except Exception:
        pass

    try:
        elapsed_total = time.perf_counter() - (_profile_start_time or time.perf_counter())
        lines = []
        lines.append("=" * 100)
        lines.append(f"  FA11y Real-Time Profile Results")
        lines.append(f"  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  Session duration: {elapsed_total:.1f}s")
        lines.append("=" * 100)

        # Copy stats without holding the lock long (signal handler safety)
        stats_copy = dict(_func_stats)

        if stats_copy:
            lines.append(f"\n  {'Function':<50} {'Calls':>6} {'Avg':>8} {'Min':>8} {'Max':>8} {'Total':>9} {'%':>6}")
            lines.append(f"  {'-'*100}")

            grand_total = sum(sum(times) for times in stats_copy.values())

            entries = sorted(stats_copy.items(), key=lambda e: sum(e[1]), reverse=True)

            for fname, times in entries:
                count = len(times)
                avg = sum(times) / count
                mn = min(times)
                mx = max(times)
                total = sum(times)
                pct = (total / grand_total * 100) if grand_total > 0 else 0
                lines.append(f"  {fname:<50} {count:>6} {avg:>7.2f}ms {mn:>7.2f}ms {mx:>7.2f}ms {total:>8.1f}ms {pct:>5.1f}%")

            lines.append(f"\n  Grand total profiled time: {grand_total:.1f}ms")
        else:
            lines.append("\n  (No profiled function calls recorded)")

        lines.append(f"  Session wall time: {elapsed_total*1000:.1f}ms")

        text = "\n".join(lines) + "\n"

        # Write with explicit flush + fsync to ensure data hits disk before os._exit()
        with open(_profile_file, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

        print(f"\n[PROFILE] Results saved to: {os.path.abspath(_profile_file)}")
        print(text)
    except Exception as e:
        # Last resort: try to at least print to console
        try:
            print(f"\n[PROFILE] Could not save results: {e}")
        except Exception:
            pass


def _hook(target, attr, name):
    """Safely wrap target.attr with profiling under the given name."""
    fn = getattr(target, attr, None)
    if fn is not None:
        setattr(target, attr, wrap_function(fn, name))
        return True
    return False


def install_profile_hooks():
    """Wrap functions across ALL FA11y modules with profiling.

    Called once after enable_profile() so that all wrapping happens
    while _profile_enabled is True.
    """
    if not _profile_enabled:
        return

    hooked = 0

    # ── PPI ─────────────────────────────────────────────────────────
    try:
        from lib.detection import ppi
        for fn in ['find_player_position', 'find_best_match', 'capture_map_screen', '_match_at_scale']:
            hooked += _hook(ppi, fn, f"ppi.{fn}")
    except Exception as e:
        print(f"[PROFILE] ppi: {e}")

    # ── Player position ─────────────────────────────────────────────
    try:
        from lib.detection import player_position as pp
        for fn in [
            'start_icon_detection', 'icon_detection_cycle', 'get_player_info_ppi',
            'get_player_info', 'find_minimap_icon_direction', 'find_player_icon_location',
            'find_player_icon_location_with_direction', 'handle_poi_selection',
            'play_spatial_poi_sound', 'perform_poi_actions', 'process_screenshot',
            'auto_turn_towards_poi', 'calculate_poi_info', 'generate_poi_message',
            'speak_auto_turn_result', 'check_for_minimap', 'check_for_full_map',
            'handle_closed_map_ppi', 'speak_minimap_direction', 'find_triangle_tip',
            'get_position_with_fallback',
        ]:
            hooked += _hook(pp, fn, f"player_pos.{fn}")
        # Position tracker methods
        if hasattr(pp, 'position_tracker') and pp.position_tracker:
            for fn in ['get_position_and_angle', 'start_monitoring', 'stop_monitoring', '_monitor_loop']:
                hooked += _hook(pp.position_tracker, fn, f"pos_tracker.{fn}")
    except Exception as e:
        print(f"[PROFILE] player_position: {e}")

    # ── Screenshot manager ──────────────────────────────────────────
    try:
        from lib.managers import screenshot_manager as sm
        mgr = sm.screenshot_manager
        for fn in ['capture_region', 'get_pixel', 'capture_full_screen', 'capture_coordinates']:
            hooked += _hook(mgr, fn, f"screenshot.{fn}")
    except Exception as e:
        print(f"[PROFILE] screenshot_manager: {e}")

    # ── Match tracker ───────────────────────────────────────────────
    try:
        from lib.detection import match_tracker as mt
        tracker = mt.match_tracker
        for fn in [
            '_monitor_loop', '_update_player_position', '_check_nearby_game_objects',
            '_check_height_indicator_transition', '_start_new_match', '_mark_object_visited',
            'get_position_update_interval',
        ]:
            hooked += _hook(tracker, fn, f"match_tracker.{fn}")
    except Exception as e:
        print(f"[PROFILE] match_tracker: {e}")

    # ── Spatial audio ───────────────────────────────────────────────
    try:
        from lib.utilities.spatial_audio import SpatialAudio
        for fn in ['play_audio', 'stop', 'calculate_distance_and_angle', 'get_volume_from_config']:
            hooked += _hook(SpatialAudio, fn, f"spatial_audio.{fn}")
    except Exception as e:
        print(f"[PROFILE] spatial_audio: {e}")

    # ── Audio engine ────────────────────────────────────────────────
    try:
        from lib.audio import get_engine
        engine = get_engine()
        if engine:
            for fn in ['play_sound', 'stop_sound', 'is_sound_playing']:
                hooked += _hook(engine, fn, f"audio_engine.{fn}")
    except Exception:
        pass  # Engine may not be initialized yet

    # ── Config reads/writes ─────────────────────────────────────────
    try:
        from lib.utilities import utilities as util
        for fn in ['read_config', 'save_config']:
            hooked += _hook(util, fn, f"config.{fn}")
    except Exception as e:
        print(f"[PROFILE] utilities: {e}")

    # ── Config manager ──────────────────────────────────────────────
    try:
        from lib.config.config_manager import config_manager as cm
        for fn in ['get', 'set', 'reload']:
            hooked += _hook(cm, fn, f"config_mgr.{fn}")
    except Exception:
        pass

    # ── Dynamic object finder ───────────────────────────────────────
    try:
        from lib.detection import dynamic_object_finder as dof
        finder = getattr(dof, 'optimized_finder', None)
        if finder:
            for fn in ['fast_multi_scale_match', 'batch_detect_dynamic_objects', 'detect_dynamic_object']:
                hooked += _hook(finder, fn, f"dynamic_obj.{fn}")
    except Exception:
        pass

    # ── Height monitor ──────────────────────────────────────────────
    try:
        from lib.monitors import height_monitor as hm
        for fn in ['is_height_indicator_visible', 'check_height', 'start_height_monitor']:
            hooked += _hook(hm, fn, f"height_mon.{fn}")
    except Exception:
        pass

    # ── Background monitor ──────────────────────────────────────────
    try:
        from lib.monitors import background_monitor as bm
        mon = getattr(bm, 'monitor', None)
        if mon:
            for fn in ['check_map_status', 'check_inventory_status', 'monitor_loop']:
                hooked += _hook(mon, fn, f"bg_monitor.{fn}")
    except Exception:
        pass

    # ── Storm monitor ───────────────────────────────────────────────
    try:
        from lib.monitors import storm_monitor as stm
        smon = getattr(stm, 'storm_monitor', None)
        if smon:
            for fn in ['detection_loop', 'detect_purple_tint', 'detect_storm_on_minimap']:
                hooked += _hook(smon, fn, f"storm_mon.{fn}")
    except Exception:
        pass

    # ── Bloom monitor ───────────────────────────────────────────────
    try:
        from lib.monitors import bloom_monitor as blm
        bmon = getattr(blm, 'bloom_monitor', None)
        if bmon:
            for fn in ['_monitor_loop', '_detect_bloom', '_is_center_crosshair', '_play_bloom_tone']:
                hooked += _hook(bmon, fn, f"bloom_mon.{fn}")
    except Exception:
        pass

    # ── Material monitor ────────────────────────────────────────────
    try:
        from lib.monitors import material_monitor as mm
        mmon = getattr(mm, 'material_monitor', None)
        if mmon:
            for fn in ['monitor_loop', 'detect_material', 'detect_count']:
                hooked += _hook(mmon, fn, f"material_mon.{fn}")
    except Exception:
        pass

    # ── Resource monitor ────────────────────────────────────────────
    try:
        from lib.monitors import resource_monitor as rm
        rmon = getattr(rm, 'resource_monitor', None)
        if rmon:
            for fn in ['monitor_loop', 'detect_resource', 'detect_count']:
                hooked += _hook(rmon, fn, f"resource_mon.{fn}")
    except Exception:
        pass

    # ── Dynamic object monitor ──────────────────────────────────────
    try:
        from lib.monitors import dynamic_object_monitor as dom
        dmon = getattr(dom, 'dynamic_object_monitor', None)
        if dmon:
            for fn in ['detection_loop', '_play_spatial_audio']:
                hooked += _hook(dmon, fn, f"dynobj_mon.{fn}")
    except Exception:
        pass

    # ── Hotbar manager ──────────────────────────────────────────────
    try:
        from lib.managers import hotbar_manager as hb
        for fn in [
            'detect_hotbar_item', 'detect_hotbar_item_thread', 'check_slot',
            'detect_rarity_for_slot', 'detect_rarity_by_color', '_ocr_detect_item_name',
            'announce_ammo', 'announce_ammo_manually', 'announce_attachments',
            'detect_ammo', 'detect_ammo_count',
        ]:
            hooked += _hook(hb, fn, f"hotbar.{fn}")
    except Exception:
        pass

    # ── OCR manager ─────────────────────────────────────────────────
    try:
        from lib.managers import ocr_manager as om
        mgr = getattr(om, 'ocr_manager', None) or getattr(om, 'OCRManager', None)
        if mgr and not isinstance(mgr, type):
            for fn in ['read_numbers', 'read_text']:
                hooked += _hook(mgr, fn, f"ocr.{fn}")
    except Exception:
        pass

    # ── Game object manager ─────────────────────────────────────────
    try:
        from lib.managers import game_object_manager as gom
        mgr = getattr(gom, 'game_object_manager', None)
        if mgr:
            for fn in [
                'get_game_objects_for_map', 'find_nearest_unvisited_object_of_type',
                'load_game_objects',
            ]:
                hooked += _hook(mgr, fn, f"game_obj.{fn}")
    except Exception:
        pass

    # ── POI data manager ────────────────────────────────────────────
    try:
        from lib.managers import poi_data_manager as pdm
        for fn in ['get_poi_data', 'get_current_map']:
            hooked += _hook(pdm, fn, f"poi_data.{fn}")
        # FavoritesManager
        fmgr = getattr(pdm, 'favorites_manager', None)
        if fmgr:
            for fn in ['add_favorite', 'remove_favorite', 'is_favorite', 'get_favorites']:
                hooked += _hook(fmgr, fn, f"favorites.{fn}")
    except Exception:
        pass

    # ── Custom POI manager ──────────────────────────────────────────
    try:
        from lib.managers import custom_poi_manager as cpm
        for fn in ['update_poi_handler', 'get_custom_pois', 'save_custom_poi']:
            hooked += _hook(cpm, fn, f"custom_poi.{fn}")
    except Exception:
        pass

    # ── Lobby reader ────────────────────────────────────────────────
    try:
        from lib.detection import lobby_reader as lr
        for fn in [
            'detect_screen_type', 'read_build_mode', 'find_layout',
            'read_ranked_state', 'read_fill_state', 'toggle_lobby_fill',
            'set_team_size', 'toggle_ranked', 'toggle_build_mode',
        ]:
            hooked += _hook(lr, fn, f"lobby.{fn}")
    except Exception:
        pass

    # ── Exit match ──────────────────────────────────────────────────
    try:
        from lib.detection import exit_match as em
        for fn in ['exit_match', 'check_pixel_color']:
            hooked += _hook(em, fn, f"exit_match.{fn}")
    except Exception:
        pass

    # ── HSR (health/shield/rarity) ──────────────────────────────────
    try:
        from lib.detection import hsr
        for fn in ['check_health_shields', 'check_rarity']:
            hooked += _hook(hsr, fn, f"hsr.{fn}")
    except Exception:
        pass

    # ── Mouse utilities ─────────────────────────────────────────────
    try:
        from lib.utilities import mouse as mu
        for fn in ['move_to', 'move_to_and_click', 'move_to_and_right_click', 'click_mouse', 'smooth_move_mouse']:
            hooked += _hook(mu, fn, f"mouse.{fn}")
    except Exception:
        pass

    # ── Mouse passthrough service ───────────────────────────────────
    try:
        from lib.mouse_passthrough import get_mouse_passthrough
        svc = get_mouse_passthrough()
        if svc:
            for fn in ['toggle', 'recapture_mouse', 'update_dpi']:
                hooked += _hook(svc, fn, f"mouse_pt.{fn}")
    except Exception:
        pass

    # ── Input utilities ─────────────────────────────────────────────
    try:
        from lib.utilities import input as inp
        for fn in ['is_key_pressed', 'is_key_combination_pressed', 'parse_key_combination']:
            hooked += _hook(inp, fn, f"input.{fn}")
    except Exception:
        pass

    # ── Epic auth ───────────────────────────────────────────────────
    try:
        from lib.utilities import epic_auth as ea
        auth = getattr(ea, 'epic_auth', None)
        if auth:
            for fn in [
                'query_locker_items', 'get_equipped_cosmetics', 'get_saved_loadouts',
                'fetch_owned_cosmetics', 'fetch_cosmetics_from_api',
            ]:
                hooked += _hook(auth, fn, f"epic_auth.{fn}")
        locker = getattr(ea, 'locker_api', None)
        if locker:
            for fn in ['equip_cosmetic', 'save_loadout', 'load_loadout']:
                hooked += _hook(locker, fn, f"locker_api.{fn}")
    except Exception:
        pass

    # ── Social / Discovery ──────────────────────────────────────────
    try:
        from lib.managers import social_manager as socm
        mgr = getattr(socm, 'social_manager', None)
        if mgr:
            for fn in ['get_friends_list', 'get_party_members']:
                hooked += _hook(mgr, fn, f"social.{fn}")
    except Exception:
        pass

    try:
        from lib.utilities import epic_discovery as ed
        for fn in ['search_islands', 'lookup_island_code', 'get_creator_islands']:
            hooked += _hook(ed, fn, f"discovery.{fn}")
    except Exception:
        pass

    print(f"[PROFILE] {hooked} function hooks installed across all modules.")
