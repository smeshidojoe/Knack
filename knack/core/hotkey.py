"""
Глобальный хоткей через RegisterHotKey.

Без сторонних пакетов и без низкоуровневых хуков клавиатуры: сочетание
регистрирует сама Windows, а WM_HOTKEY прилетает в очередь сообщений потока
(hWnd = NULL) — Qt прогоняет её через nativeEventFilter, оттуда и ловим.
"""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

MOD_ALT     = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT   = 0x0004
MOD_WIN     = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312

_MODS = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN, "meta": MOD_WIN,
}

_KEYS = {
    "space": 0x20, "esc": 0x1B, "escape": 0x1B, "tab": 0x09,
    "enter": 0x0D, "return": 0x0D, "backspace": 0x08, "insert": 0x2D,
    "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
}
for _i in range(1, 25):
    _KEYS["f%d" % _i] = 0x6F + _i


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd",    wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam",  wintypes.WPARAM),
        ("lParam",  wintypes.LPARAM),
        ("time",    wintypes.DWORD),
        ("pt_x",    wintypes.LONG),
        ("pt_y",    wintypes.LONG),
    ]


def parse(combo):
    """'ctrl+alt+k' -> (mods, vk). Возвращает None, если разобрать не вышло."""
    mods, vk = 0, None
    for part in str(combo).lower().replace(" ", "").split("+"):
        if not part:
            continue
        if part in _MODS:
            mods |= _MODS[part]
        elif part in _KEYS:
            vk = _KEYS[part]
        elif len(part) == 1 and (part.isdigit() or ("a" <= part <= "z")):
            vk = ord(part.upper())
        else:
            return None
    if vk is None or mods == 0:
        return None            # без модификатора хоткей перехватил бы обычную клавишу
    return mods, vk


class HotkeyManager(QObject, QAbstractNativeEventFilter):
    """Регистрирует сочетания и превращает WM_HOTKEY в сигнал `triggered(name)`."""

    triggered = Signal(str)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self._by_id = {}       # id -> имя
        self._by_name = {}     # имя -> id
        self._next_id = 1
        self._installed = False

    def install(self, app):
        if not self._installed:
            app.installNativeEventFilter(self)
            self._installed = True

    def register(self, name, combo):
        """Перерегистрирует сочетание под именем `name`. True — получилось."""
        self.unregister(name)
        parsed = parse(combo)
        if parsed is None:
            return False
        mods, vk = parsed
        hk_id = self._next_id
        self._next_id += 1
        try:
            ok = ctypes.windll.user32.RegisterHotKey(
                None, hk_id, mods | MOD_NOREPEAT, vk)
        except Exception:
            ok = False
        if not ok:
            return False       # сочетание занято другой программой
        self._by_id[hk_id] = name
        self._by_name[name] = hk_id
        return True

    def unregister(self, name):
        hk_id = self._by_name.pop(name, None)
        if hk_id is None:
            return
        self._by_id.pop(hk_id, None)
        try:
            ctypes.windll.user32.UnregisterHotKey(None, hk_id)
        except Exception:
            pass

    def unregister_all(self):
        for name in list(self._by_name):
            self.unregister(name)

    def nativeEventFilter(self, event_type, message):
        if event_type != b"windows_generic_MSG":
            return False, 0
        try:
            msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
        except (TypeError, ValueError):
            return False, 0
        if msg.message == WM_HOTKEY:
            name = self._by_id.get(int(msg.wParam))
            if name:
                self.triggered.emit(name)
                return True, 0
        return False, 0
