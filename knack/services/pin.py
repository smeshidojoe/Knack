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

from PySide6.QtCore import QObject

from ..core import logbook

user32 = ctypes.windll.user32

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200
SWP_ASYNCWINDOWPOS = 0x4000
GWL_EXSTYLE = -20
GWL_STYLE = -16
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_MINIMIZE = 0x20000000

# Окна оболочки: рабочий стол, панель задач, слой обоев. Поднять их поверх всех
# значит накрыть ими экран — снаружи это выглядит как «всё перестало работать».
SHELL_CLASSES = {"progman", "workerw", "shell_traywnd", "shell_secondarytraywnd",
                 "button", "dv2controlhost", "windows.ui.core.corewindow",
                 "multitaskingviewframe", "foregroundstaging"}

# Типы объявляем явно: по умолчанию ctypes считает результат 32-битным, а HWND
# на 64-битной Windows — указатель.
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetForegroundWindow.argtypes = []
user32.IsWindow.restype = wintypes.BOOL
user32.IsWindow.argtypes = [wintypes.HWND]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                            ctypes.POINTER(wintypes.DWORD)]
user32.GetShellWindow.restype = wintypes.HWND
user32.GetShellWindow.argtypes = []
user32.GetDesktopWindow.restype = wintypes.HWND
user32.GetDesktopWindow.argtypes = []
user32.GetClassNameW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongW.restype = wintypes.LONG
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowPos.restype = wintypes.BOOL
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wintypes.UINT]


class PinService(QObject):
    """Закрепление чужих окон поверх остальных."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pinned = set()

    # --- состояние -------------------------------------------------------- #

    @staticmethod
    def is_topmost(hwnd):
        return bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)

    @staticmethod
    def class_name(hwnd):
        buffer = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buffer, len(buffer))
        return buffer.value.lower()

    @classmethod
    def pinnable(cls, hwnd):
        """
        Годится ли окно в закрепление.

        Хоткей ловит то окно, что сейчас активно, а активным бывает и рабочий
        стол — щёлкнул по обоям, и вот он. Подняв его поверх всех, мы накрыли бы
        им экран: окна остались бы на месте, но выглядело бы это как намертво
        зависший рабочий стол.
        """
        if hwnd in (user32.GetShellWindow(), user32.GetDesktopWindow()):
            return False
        if cls.class_name(hwnd) in SHELL_CLASSES:
            return False
        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if style & WS_MINIMIZE:
            return False       # свёрнутое поверх всех не поднимешь
        return True

    @staticmethod
    def own_window(hwnd):
        """Наши собственные окна закреплять нечего: панель и так поверх всех."""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value == ctypes.windll.kernel32.GetCurrentProcessId()

    def _set_topmost(self, hwnd, on):
        # NOMOVE|NOSIZE — трогаем только порядок, положение и размер остаются за
        # окном: тащить его мышью можно как обычно. NOACTIVATE — закрепление не
        # перетаскивает фокус на окно, которое человек только что оставил.
        # ASYNCWINDOWPOS — запрос уходит в очередь чужого окна и не подвешивает
        # нас, если оно сейчас занято (например, его как раз тащат).
        flags = (SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE
                 | SWP_NOOWNERZORDER | SWP_ASYNCWINDOWPOS)
        ok = user32.SetWindowPos(hwnd, HWND_TOPMOST if on else HWND_NOTOPMOST,
                                 0, 0, 0, 0, flags)
        return bool(ok)

    # --- по хоткею -------------------------------------------------------- #

    def toggle(self):
        """Закрепляет активное окно или снимает закрепление."""
        hwnd = user32.GetForegroundWindow()
        if not hwnd or self.own_window(hwnd):
            return None
        if not self.pinnable(hwnd):
            logbook.log("закрепление: это окно не закрепляем —",
                        self.class_name(hwnd))
            return None
        return self.toggle_window(hwnd)

    def toggle_window(self, hwnd):
        """То же для конкретного окна — по клику на значке."""
        if not hwnd or not user32.IsWindow(hwnd):
            return None
        on = not self.is_topmost(hwnd)
        if not self._set_topmost(hwnd, on):
            # Окна с правами администратора чужому SetWindowPos не поддаются.
            logbook.log("закрепление: окно не поддалось (запущено от админа?)")
            return None
        if on:
            self._pinned.add(hwnd)
        else:
            self._pinned.discard(hwnd)
        return on

    def release_all(self):
        """Снимает закрепление со всех окон, которые закрепили мы."""
        for hwnd in list(self._pinned):
            if user32.IsWindow(hwnd) and self.is_topmost(hwnd):
                self._set_topmost(hwnd, False)
        self._pinned.clear()
