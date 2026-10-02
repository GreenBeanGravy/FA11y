"""Make accessible_output2 cheap to construct.

FA11y modules each create their own ``Auto()`` speaker at import time.
For every screen reader DLL, accessible_output2 finds its own folder with
``inspect.stack()``, which reads the source of every frame on the stack.
Inside FA11y's deep import chain that adds about a second to startup.
install() swaps in a lookup that uses the package's __file__ instead.
"""
from __future__ import annotations

import ctypes
import os


def install() -> None:
    try:
        import accessible_output2
        import accessible_output2.outputs.base as base
    except Exception:
        return
    original = accessible_output2.load_library
    lib_dir = os.path.join(os.path.dirname(os.path.abspath(accessible_output2.__file__)), "lib")

    def load_library(libname, cdll=False):
        path = os.path.join(lib_dir, libname)
        if not os.path.exists(path):
            return original(libname, cdll=cdll)
        return ctypes.cdll[path] if cdll else ctypes.windll[path]

    accessible_output2.load_library = load_library
    base.load_library = load_library
