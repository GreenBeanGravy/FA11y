"""Requests for first-run setup, which the window shows instead of the sidebar and pages.

The steps and their texts live in the window. These requests give it what
only the core knows (who is signed in, what Fortnite looks like, the test
sound) and save the answers when setup finishes or is skipped. Signing in
uses account.sign_in.
"""
from __future__ import annotations

from lib.hub import get_hub, setup_ops
from lib.shell.bridge import handler

_audio = setup_ops.AudioTester()


@handler("setup.signin_state")
def signin_state(_params: dict) -> dict:
    return setup_ops.signin_state()


@handler("setup.fortnite")
def fortnite_step(_params: dict) -> dict:
    return setup_ops.fortnite_step_state()


@handler("setup.test_sound")
def test_sound(params: dict) -> dict:
    return {"message": _audio.play(params.get("volume", 100))}


@handler("setup.finish")
def finish(params: dict) -> dict:
    """Setup ended. save is false when it was skipped; egl is "manage", "sync" or null."""
    from lib.hub import settings, sounds
    hub = get_hub()
    save = bool(params.get("save"))
    values = setup_ops.collect_values(params.get("answers") or {}) if save else {}
    speak = hub.services.speak if hub is not None else None
    saved = setup_ops.save_setup(values, speak=speak)
    _audio.cleanup()
    egl = params.get("egl") if save and params.get("egl") in ("manage", "sync") else None
    sounds.set_enabled(settings.flag("NavigationSounds", True))
    if save:
        sounds.ui("done")
    if hub is not None:
        hub.finish_onboarding(egl)
    return {"saved": saved}
