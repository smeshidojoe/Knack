"""
Закрепление чужого окна поверх остальных.

По сочетанию клавиш активное окно получает WS_EX_TOPMOST — ровно то, что делает
Always On Top из PowerToys. Флаг живёт в самом окне, а не в нашем цикле событий:
пока он стоит, окно держится сверху само, что бы ни делали мы. Повторное
нажатие снимает.

Закреплённые окна помним, чтобы при выходе вернуть их в общий порядок: иначе
после закрытия Knack снять закрепление было бы нечем.

Окно, запущенное от администратора, не поддастся: SetWindowPos из обычной
программы до него не дотягивается. Та же граница, что и у смены раскладки.
"""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

from ..core import logbook

user32 = ctypes.windll.user32

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008

# Типы объявляем явно: по умолчанию ctypes считает результат 32-битным, а HWND
# на 64-битной Windows — указатель.
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                            ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowLongW.restype = wintypes.LONG
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]


class PinService(QObject):
    """pinned(окно закреплено) — для отклика в трее."""

    pinned = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pinned = set()

    # --- состояние -------------------------------------------------------- #

    @staticmethod
    def _is_topmost(hwnd):
        return bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)

    @staticmethod
    def _own_window(hwnd):
        """Наши собственные окна закреплять нечего: панель и так поверх всех."""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == ctypes.windll.kernel32.GetCurrentProcessId()

    def _set_topmost(self, hwnd, on):
        # SWP_NOACTIVATE: закрепление не должно перетаскивать фокус на окно,
        # которое человек, может быть, только что оставил.
        ok = user32.SetWindowPos(hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST,
                                 0, 0, 0, 0,
                                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        return bool(ok)

    # --- по хоткею -------------------------------------------------------- #

    def toggle(self):
        """Закрепляет активное окно или снимает закрепление."""
        hwnd = user32.GetForegroundWindow()
        if not hwnd or self._own_window(hwnd):
            return None
        on = not self._is_topmost(hwnd)
        if not self._set_topmost(hwnd, on):
            # Окна с правами администратора чужому SetWindowPos не поддаются.
            logbook.log("закрепление: окно не поддалось (запущено от админа?)")
            return None
        if on:
            self._pinned.add(hwnd)
        else:
            self._pinned.discard(hwnd)
        self.pinned.emit(on)
        return on

    def release_all(self):
        """Снимает закрепление со всех окон, которые закрепили мы."""
        for hwnd in list(self._pinned):
            if user32.IsWindow(hwnd) and self._is_topmost(hwnd):
                self._set_topmost(hwnd, False)
        self._pinned.clear()
