# Contributing to FA11y

Development rules for FA11y. Follow these for every change, whether you're a maintainer or submitting a PR.

## Always update the changelog for user-visible changes

`CHANGELOG.txt` is not just a dev log — FA11y downloads it and offers to open it every time a user receives an update (`lib/app/updater_check.py`). Blind and low-vision users read it with a screen reader to learn what changed.

**If a user would notice the change, it goes in the changelog.** That includes:

- New features, keybinds, settings, or GUI elements
- Changed defaults or behavior
- Removed features
- Bug fixes users would have experienced

Rules for entries:

- Add a new block at the **top** of `CHANGELOG.txt`, formatted `M/D/YYYY #N:` (N counts multiple releases on the same day, starting at 1)
- One `- ` bullet per change
- Write in plain language describing what the **user** experiences — not internals. Say "Added the Check Display Mode keybind (Left Alt + R)", not "Refactored display detection module"
- Mention default keybinds and setting names so users can find them
- Purely internal changes (refactors, test changes, CI) do **not** need an entry

## Bump VERSION on every release

The updater detects updates by comparing the local `VERSION` file against the one on GitHub. **If you don't bump `VERSION`, users never receive your change.**

- Increment the patch number (e.g. `18.8.5` → `18.8.6`) for normal changes
- Docs-only changes (like this file) don't need a bump

## Settings and keybinds

- All default settings and keybinds live in `lib/utilities/utilities.py`, each with a quoted description string
- The description is read aloud by screen readers in the configuration menu — write it as a clear, complete sentence
- Never rename or remove a setting/keybind without checking the key listener handles the stale name gracefully (unknown actions in a user's existing config are skipped, so removal is safe)

## Accessibility first

FA11y exists for screen-reader users. For any change:

- Every user-visible event needs spoken feedback
- New GUIs must use the existing accessible wxPython patterns (see `AccessibleDialog` usage in `FortniteManager.py`) — full keyboard navigation, no mouse-only interactions
- Never rely on color or visuals alone to convey information

## Dependencies

- Add new packages to `requirements.txt`; the updater installs them automatically on user machines
- Keep additions compatible with the pinned `numpy==1.26.4`
- Pin a version only when a newer release is known to break

## Before you push

1. Run the test suite: `python -m pytest tests -q`
2. Byte-compile to catch syntax/import errors: `python -m compileall -q FA11y.py updater.py FortniteManager.py lib`
3. Search for leftover references when removing a feature (imports, keybind handlers, config defaults, monitor start/stop calls in `FA11y.py`)

## Code patterns

- Background features are monitors: subclass `BaseMonitor` (`lib/monitors/base.py`), expose a module-level instance, and wire `start_monitoring()`/`stop_monitoring()` into `FA11y.py`
- Keybind actions are lowercase names in the `action_handlers` dict in `FA11y.py`, matched to the keybind names in `lib/utilities/utilities.py`
- Keep commit messages short and descriptive
