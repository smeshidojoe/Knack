"""
Где стоит панель задач — от этого зависит, из какого края экрана выезжает Knack.

SHAppBarMessage(ABM_GETTASKBARPOS) отдаёт положение ОСНОВНОЙ панели задач.
Вторичные панели на других мониторах повторяют край основной, так что одного
запроса хватает.
"""

import ctypes
from ctypes import wintypes

ABM_GETTASKBARPOS = 0x00000005

_EDGES = {0: "left", 1: "top", 2: "right", 3: "bottom"}


class _APPBARDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize",           wintypes.DWORD),
        ("hWnd",             wintypes.HWND),
        ("uCallbackMessage", wintypes.UINT),
        ("uEdge",            wintypes.UINT),
        ("rc",               wintypes.RECT),
        ("lParam",           wintypes.LPARAM),
    ]


def taskbar_edge():
    """'left' | 'top' | 'right' | 'bottom'; 'bottom' — если спросить не вышло."""
    try:
        data = _APPBARDATA()
        data.cbSize = ctypes.sizeof(_APPBARDATA)
        shell = ctypes.windll.shell32
        shell.SHAppBarMessage.restype = ctypes.c_size_t
        shell.SHAppBarMessage.argtypes = [wintypes.DWORD, ctypes.POINTER(_APPBARDATA)]
        if shell.SHAppBarMessage(ABM_GETTASKBARPOS, ctypes.byref(data)):
            return _EDGES.get(data.uEdge, "bottom")
    except Exception:
        pass
    return "bottom"


def panel_edge():
    """
    Край экрана, из которого выезжает панель: противоположный панели задач.

    Для боковых панелей задач (left/right) верх свободен — выезжаем сверху.
    """
    return "bottom" if taskbar_edge() == "top" else "top"
