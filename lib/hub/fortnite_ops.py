"""What the Fortnite page shows and does, without any window code.

Shared by the wx Fortnite page and the requests the new window sends.
"""
from __future__ import annotations

import os
import shutil
from typing import Optional

API_CHOICES = [("default", "Default"), ("dx11", "DirectX 11"), ("dx12", "DirectX 12"),
               ("performance", "Performance mode")]

SIGNIN_TEXT = "Downloads, updates and Play need your Epic account."
CHECKING_TEXT = "Checking your Fortnite install…"
MOUSE_PROMPT = "Move the mouse you play with now."
NO_MOUSE_PREFIX = "No mouse moved, so nothing changed. "


def size_text(size_bytes: int) -> str:
    if size_bytes <= 0:
        return ""
    gb = size_bytes / 1024 ** 3
    return f"{gb:.0f} GB" if gb >= 10 else f"{gb:.1f} GB"


def free_space_text(path: str) -> str:
    probe = path
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        return f"{shutil.disk_usage(probe).free / 1024 ** 3:.0f} GB free"
    except OSError:
        return ""


def short_version(build: str) -> str:
    """'++Fortnite+Release-42.20-CL-58011042-Windows' -> '42.20'."""
    marker = "Release-"
    if marker in build:
        return build.split(marker, 1)[1].split("-", 1)[0]
    return build


def install_question(base: str) -> str:
    """The question asked before installing into base."""
    free = free_space_text(base)
    return (f"Install Fortnite in {os.path.join(base, 'Fortnite')}? "
            f"It needs about 100 GB{' (' + free + ')' if free else ''}.")


def summary_text(st) -> str:
    """The one line under the page heading."""
    if st is None:
        return CHECKING_TEXT
    if not st.legendary_available:
        return st.error
    if st.installed:
        parts = [short_version(st.version) or "Installed", "managed by FA11y", st.install_path,
                 size_text(st.install_size_bytes)]
        if st.update_available:
            parts.append(f"update available ({st.remote_version})")
        elif st.needs_verification:
            parts.append("needs verifying")
        return " · ".join(p for p in parts if p)
    if st.egl_install_path:
        return "Installed through the Epic Games Launcher."
    return "Fortnite isn't installed."


def egl_text(st) -> str:
    version = f", version {short_version(st.egl_version)}" if st.egl_version else ""
    return f"Fortnite is installed through the Epic Games Launcher at {st.egl_install_path}{version}."


def check_message(st) -> str:
    """What is said after a manual update check."""
    if st.update_available:
        return f"Update available: {st.remote_version}."
    return st.error or "Fortnite is up to date."


def describe_status(st) -> dict:
    """The status as the new window needs it: the summary and which controls apply."""
    if st is None:
        return {"checked": False, "summary": CHECKING_TEXT}
    installed = bool(st.installed)
    egl_only = bool(not installed and st.egl_install_path)
    legendary_ok = bool(st.legendary_available)
    return {
        "checked": True,
        "summary": summary_text(st),
        "installed": installed,
        "egl_only": egl_only,
        "legendary_ok": legendary_ok,
        "show_signin": legendary_ok and not st.logged_in,
        "show_install": legendary_ok and not installed and not egl_only,
        "update_available": bool(st.update_available),
        "egl_text": egl_text(st) if egl_only else "",
        "install_path": st.install_path or "",
        "remote_version": st.remote_version or "",
    }


def launch_options() -> dict:
    from lib.fortnite import load_launch_options
    options = load_launch_options()
    keys = [c[0] for c in API_CHOICES]
    return {"api": options.api if options.api in keys else "default",
            "skip_splash": bool(options.skip_splash), "extra": options.extra or ""}


def save_launch_options(api: str, skip_splash: bool, extra: str) -> bool:
    from lib.fortnite import LaunchOptions, save_launch_options as save
    if api not in [c[0] for c in API_CHOICES]:
        api = "default"
    return save(LaunchOptions(api=api, skip_splash=bool(skip_splash), extra=extra or ""))


def mouse_info() -> dict:
    """The mouse passthrough text and whether the Detect button applies."""
    try:
        from lib.mouse_passthrough import get_mouse_passthrough
        service = get_mouse_passthrough()
        return {"available": True, "text": service.describe(), "detected": bool(service.target_device)}
    except Exception as e:
        return {"available": False, "text": f"Mouse passthrough isn't available: {e}", "detected": False}


def mouse_after_detect(device) -> dict:
    """The mouse state after Detect mouse finished; device is None when no mouse moved."""
    info = mouse_info()
    if device is None:
        info["text"] = NO_MOUSE_PREFIX + info["text"]
    info["found"] = device is not None
    return info


def open_install_folder(path: Optional[str]) -> bool:
    if path and os.path.isdir(path):
        os.startfile(path)
        return True
    return False
