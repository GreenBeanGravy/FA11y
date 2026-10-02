"""Names and descriptions for native controls, through Windows dynamic annotation.

Screen readers read a control's description after its name, role and
value ("Announce ammo, check box, checked, Says when ammo runs low").
Native controls have no description of their own, and some (number boxes)
take focus in an inner window that wx.Accessible can't reach.
IAccPropServices.SetHwndPropStr annotates the window Windows itself
reports, so the name and description come from the control, and FA11y
never speaks over the screen reader.
"""
from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from typing import List, Optional

import wx

logger = logging.getLogger(__name__)


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text: str) -> "_GUID":
        guid = cls()
        ctypes.oledll.ole32.CLSIDFromString(text, ctypes.byref(guid))
        return guid


CLSID_ACC_PROP_SERVICES = "{b5f8350b-0548-48b1-a6ee-88bd00b4a5e7}"
IID_IACC_PROP_SERVICES = "{6e26e776-04f0-495d-80e4-3330352e3169}"
PROPID_ACC_NAME = "{608d3df8-8128-4aa7-a428-f55e49267291}"
PROPID_ACC_DESCRIPTION = "{4d48dfe4-bd3f-491f-a648-492d6f20c588}"
OBJID_CLIENT = 0xFFFFFFFC
CHILDID_SELF = 0
UDM_GETBUDDY = 0x046A
CLSCTX_INPROC_SERVER = 1

# IAccPropServices vtable slots, after IUnknown's three.
_SET_HWND_PROP_STR = 7
_CLEAR_HWND_PROPS = 9

_SetHwndPropStr = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.HWND, wintypes.DWORD,
                                     wintypes.DWORD, _GUID, wintypes.LPCWSTR)
_ClearHwndProps = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, wintypes.HWND, wintypes.DWORD,
                                     wintypes.DWORD, ctypes.POINTER(_GUID), ctypes.c_int)

_service: Optional[ctypes.c_void_p] = None
_send_message = ctypes.windll.user32.SendMessageW
_send_message.restype = ctypes.c_ssize_t
_send_message.argtypes = [wintypes.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]


def _services() -> Optional[ctypes.c_void_p]:
    global _service
    if _service is None:
        try:
            ctypes.oledll.ole32.CoInitialize(None)
        except OSError:
            pass  # already initialised by wx
        pointer = ctypes.c_void_p()
        ctypes.oledll.ole32.CoCreateInstance(
            ctypes.byref(_GUID.parse(CLSID_ACC_PROP_SERVICES)), None, CLSCTX_INPROC_SERVER,
            ctypes.byref(_GUID.parse(IID_IACC_PROP_SERVICES)), ctypes.byref(pointer))
        _service = pointer
    return _service


def _method(index: int, prototype):
    service = _services()
    vtable = ctypes.cast(ctypes.cast(service, ctypes.POINTER(ctypes.c_void_p))[0],
                         ctypes.POINTER(ctypes.c_void_p))
    return service, prototype(vtable[index])


def _focus_windows(window: wx.Window) -> List[int]:
    """Handles of the windows that take focus for ``window``."""
    handles = [window.GetHandle()]
    if isinstance(window, wx.SpinCtrl):
        # A native spin control is an up-down control plus an edit box
        # beside it, and focus goes to the edit box.
        buddy = _send_message(window.GetHandle(), UDM_GETBUDDY, 0, 0)
        if buddy:
            handles.append(buddy)
    for child in window.GetChildren():
        if isinstance(child, wx.TextCtrl):  # SpinCtrlDouble's own edit box
            handles.append(child.GetHandle())
    return handles


def annotate(window: wx.Window, name: Optional[str] = None, description: Optional[str] = None) -> None:
    """Give ``window`` a screen reader name and/or description."""
    if not name and not description:
        return
    try:
        service, set_prop = _method(_SET_HWND_PROP_STR, _SetHwndPropStr)
        handles = _focus_windows(window)
        for handle in handles:
            if name:
                set_prop(service, handle, OBJID_CLIENT, CHILDID_SELF, _GUID.parse(PROPID_ACC_NAME), name)
            if description:
                set_prop(service, handle, OBJID_CLIENT, CHILDID_SELF,
                         _GUID.parse(PROPID_ACC_DESCRIPTION), description)
    except OSError as e:
        logger.debug(f"Annotating {window} failed: {e}")
        return
    if not getattr(window, "_annotated", False):
        window._annotated = True
        window.Bind(wx.EVT_WINDOW_DESTROY, lambda e, h=handles: (_clear(h), e.Skip()))


def _clear(handles: List[int]) -> None:
    # Annotations are keyed by window handle, which Windows reuses.
    try:
        service, clear = _method(_CLEAR_HWND_PROPS, _ClearHwndProps)
        props = (_GUID * 2)(_GUID.parse(PROPID_ACC_NAME), _GUID.parse(PROPID_ACC_DESCRIPTION))
        for handle in handles:
            clear(service, handle, OBJID_CLIENT, CHILDID_SELF, props, 2)
    except OSError:
        pass
