"""Import every third-party dependency and every FA11y module.

Run with the venv's interpreter from the repository root:

    python tools/smoke_imports.py

Exits non-zero and lists each failure if any import fails. CI runs this
after installing requirements.lock, so a missing or broken dependency is
caught before a release ships.
"""
import importlib
import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "hide")

# Import names for every top-level entry in requirements.txt.
DEPENDENCIES = [
    "accessible_output2",
    "cloudscraper",
    "cv2",
    "mss",
    "numpy",
    "onnxruntime",
    "packaging",
    "PIL",
    "psutil",
    "pyaudio",
    "pyautogui",
    "pygame",
    "pyperclip",
    "pythonnet",
    "rapidocr",
    "soundfile",
    "win32api",
    "win32com.client",
    "winshell",
    "wx",
]


def lib_modules():
    # Walk files rather than pkgutil: several lib/ folders are namespace
    # packages without __init__.py, which pkgutil.walk_packages skips.
    for dirpath, dirnames, filenames in os.walk(os.path.join(ROOT, "lib")):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, filename), ROOT)
            module = rel[:-3].replace(os.sep, ".")
            if module.endswith(".__init__"):
                module = module[: -len(".__init__")]
            yield module


def main():
    failures = []
    names = DEPENDENCIES + sorted(lib_modules())
    for name in names:
        try:
            importlib.import_module(name)
        except Exception:
            failures.append((name, traceback.format_exc(limit=3)))

    print(f"Imported {len(names) - len(failures)}/{len(names)} modules")
    for name, tb in failures:
        print(f"\nFAILED: {name}\n{tb}")
    sys.stdout.flush()
    # Daemon threads (e.g. the OCR loader) must not keep the process alive.
    os._exit(1 if failures else 0)


if __name__ == "__main__":
    main()
