"""
Кто сейчас звучит — по аудиосессиям Windows.

Запасной путь для вкладки «Музыка». Обычный путь — SMTC: браузер или плеер сам
публикует, что играет, с названием, обложкой и кнопками. Но сессию заводят не
все: реклама, короткие ролики, звонки и часть плееров звучат мимо неё, а в
сборках Chromium её нередко нет вовсе. Тогда панель показывала «ничего не
играет», хотя звук идёт.

Здесь мы спрашиваем не «что играет», а «кто шумит»: у устройства вывода есть
список сессий, и у каждой видно процесс, собственная громкость и текущий уровень
сигнала. Уровень тут главный: открытый звуковой поток держат и монтажки, и игры,
и голосовые программы — молча, часами. Берём ту сессию, которая громче всех.
Названия трека и кнопок отсюда не получить — вместо названия берём заголовок
окна процесса, у браузера это заголовок вкладки.

Как и громкость, ходим в COM через ctypes: ради нескольких вызовов тянуть в
сборку pycaw с comtypes незачем.
"""

import ctypes
import os
import time
from ctypes import POINTER, byref, c_float, c_int, c_uint, c_void_p, wintypes

from PySide6.QtCore import QFileInfo, QObject
from PySide6.QtWidgets import QFileIconProvider

from ..core import logbook
from .media import app_name
from .volume import (CLSCTX_ALL, CLSID_MMDeviceEnumerator, E_RENDER, GUID,
                     IID_IMMDeviceEnumerator, ROLE_MULTIMEDIA, _method,
                     _release, ensure_com, ole32)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

IID_IAudioSessionManager2 = "{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}"
IID_IAudioSessionControl2 = "{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}"
IID_ISimpleAudioVolume = "{87CE5498-68D6-44E5-9215-6DA47EF883D8}"
IID_IAudioMeterInformation = "{C02216F6-8C67-4B5B-9D00-D008E73E0064}"

# Номера методов в таблицах (первые три — от IUnknown).
DEV_ENUM_GET_DEFAULT = 4
DEVICE_ACTIVATE = 3
MGR_GET_ENUMERATOR = 5            # IAudioSessionManager2::GetSessionEnumerator
ENUM_GET_COUNT = 3
ENUM_GET_SESSION = 4
CTL_GET_STATE = 3                 # IAudioSessionControl::GetState
CTL_GET_DISPLAY_NAME = 4
CTL2_GET_PROCESS_ID = 14          # IAudioSessionControl2::GetProcessId
CTL2_IS_SYSTEM_SOUNDS = 15
VOL_SET_MASTER = 3                # ISimpleAudioVolume::SetMasterVolume
VOL_GET_MASTER = 4
VOL_SET_MUTE = 5
VOL_GET_MUTE = 6
METER_GET_PEAK = 3                # IAudioMeterInformation::GetPeakValue

STATE_ACTIVE = 1                  # у сессии открыт поток вывода

# Открытый поток ещё не значит «звучит»: монтажки, игры и голосовые программы
# держат его всё время работы, даже в полной тишине. Настоящий признак — уровень
# сигнала, его и спрашиваем.
PEAK_SILENCE = 1e-4
# Тишина между репликами не должна выбрасывать источник: пару секунд считаем,
# что играет всё тот же.
PEAK_MEMORY_S = 3.0

PROCESS_QUERY_LIMITED = 0x1000

user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                            POINTER(wintypes.DWORD)]
_ENUM_PROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def process_path(pid):
    """Полный путь к exe процесса. Пустая строка — не спросить."""
    if not pid:
        return ""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
    if not handle:
        return ""
    try:
        buffer = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(len(buffer))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, byref(size)):
            return buffer.value
    finally:
        kernel32.CloseHandle(handle)
    return ""


def process_name(pid):
    """Имя exe по номеру процесса."""
    return os.path.basename(process_path(pid))


def window_title(pid):
    """
    Заголовок окна процесса — им подменяем название трека.

    Берём самое большое видимое окно с непустым заголовком: у браузера это
    главное окно, и его заголовок совпадает с названием открытой вкладки.
    """
    best = {"area": 0, "title": ""}

    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, byref(owner))
        if owner.value != pid:
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, byref(rect))
        area = max(0, rect.right - rect.left) * max(0, rect.bottom - rect.top)
        if area > best["area"]:
            best["area"] = area
            best["title"] = buffer.value
        return True

    try:
        user32.EnumWindows(_ENUM_PROC(visit), 0)
    except Exception:
        logbook.exc("заголовок окна")
    return best["title"]


class _PROCESSENTRY32(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_char * 260)]


def parent_pid(pid):
    """Родитель процесса. 0 — не нашли."""
    TH32CS_SNAPPROCESS = 0x2
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == -1:
        return 0
    try:
        entry = _PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32First(snapshot, byref(entry)):
            return 0
        while True:
            if entry.th32ProcessID == pid:
                return entry.th32ParentProcessID
            if not kernel32.Process32Next(snapshot, byref(entry)):
                return 0
    finally:
        kernel32.CloseHandle(snapshot)


def title_for(pid):
    """
    Заголовок окна процесса или ближайшего предка с окном.

    Звук браузер выводит из дочернего процесса — у него окон нет вовсе. Идём
    вверх по родителям, пока не найдём процесс с видимым окном: у Chrome это
    главное окно браузера, а его заголовок и есть название вкладки.
    """
    seen = set()
    for _ in range(4):
        if not pid or pid in seen:
            break
        seen.add(pid)
        title = window_title(pid)
        if title:
            return title
        pid = parent_pid(pid)
    return ""


class AudioApp:
    """Приложение, которое сейчас звучит."""

    def __init__(self, pid, exe, label, title):
        self.pid = pid
        self.exe = exe
        self.label = label      # понятное имя: подпись сессии или имя exe
        self.title = title      # заголовок окна — вместо названия трека

    def key(self):
        return "%s|%s" % (self.pid, self.title)


class AudioSessions(QObject):
    """
    Список сессий устройства вывода.

    Интерфейс диспетчера держим открытым, а сами сессии перечитываем на каждый
    опрос: список меняется, когда приложение начинает или заканчивает играть.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._manager = None
        self._broken = False
        self._volume_of = {}     # pid -> ISimpleAudioVolume
        self._title_owner = {}   # pid звучащего процесса -> pid процесса с окном
        self._icons = {}         # путь к exe -> значок приложения
        self._last_loud = (None, 0.0)   # кто звучал последним и когда

    # --- подключение ------------------------------------------------------ #

    def _get_manager(self):
        if self._manager or self._broken:
            return self._manager
        enumerator = device = None
        try:
            ensure_com()
            enumerator = c_void_p()
            hr = ole32.CoCreateInstance(byref(GUID(CLSID_MMDeviceEnumerator)),
                                        None, CLSCTX_ALL,
                                        byref(GUID(IID_IMMDeviceEnumerator)),
                                        byref(enumerator))
            if hr < 0 or not enumerator:
                raise OSError("CoCreateInstance 0x%08X" % (hr & 0xFFFFFFFF))
            device = c_void_p()
            hr = _method(enumerator, DEV_ENUM_GET_DEFAULT, c_int, c_int,
                         POINTER(c_void_p))(enumerator, E_RENDER,
                                            ROLE_MULTIMEDIA, byref(device))
            if hr < 0 or not device:
                raise OSError("GetDefaultAudioEndpoint 0x%08X" % (hr & 0xFFFFFFFF))
            manager = c_void_p()
            hr = _method(device, DEVICE_ACTIVATE, POINTER(GUID), c_uint,
                         c_void_p, POINTER(c_void_p))(
                device, byref(GUID(IID_IAudioSessionManager2)), CLSCTX_ALL,
                None, byref(manager))
            if hr < 0 or not manager:
                raise OSError("Activate 0x%08X" % (hr & 0xFFFFFFFF))
            self._manager = manager
        except Exception:
            logbook.exc("аудиосессии: не удалось подключиться")
            self._broken = True
        finally:
            _release(device)
            _release(enumerator)
        return self._manager

    def available(self):
        return self._get_manager() is not None

    # --- опрос ------------------------------------------------------------ #

    def playing(self):
        """Кто сейчас выводит звук. None — тишина или спросить не у кого."""
        manager = self._get_manager()
        if not manager:
            return None
        sessions = c_void_p()
        hr = _method(manager, MGR_GET_ENUMERATOR, POINTER(c_void_p))(
            manager, byref(sessions))
        if hr < 0 or not sessions:
            self._forget()
            return None
        best = None
        best_peak = 0.0
        alive = set()
        try:
            count = c_int()
            if _method(sessions, ENUM_GET_COUNT, POINTER(c_int))(
                    sessions, byref(count)) < 0:
                return None
            # Перебираем все сессии и берём самую громкую: открытых потоков
            # обычно несколько, а звучит из них один.
            for index in range(count.value):
                item = self._read_session(sessions, index, alive)
                if item is None:
                    continue
                peak, app_info = item
                if peak > best_peak:
                    best_peak, best = peak, app_info
        finally:
            _release(sessions)
        self._drop_gone(alive)

        now = time.monotonic()
        if best is not None and best_peak > PEAK_SILENCE:
            self._last_loud = (best, now)
            return best
        # Все молчат: пару секунд держим прежний источник, чтобы вкладка не
        # мигала на паузе между репликами.
        remembered, when = self._last_loud
        if remembered is not None and now - when < PEAK_MEMORY_S:
            return remembered
        self._last_loud = (None, 0.0)
        return None

    def pid_for_exe(self, name):
        """
        Номер процесса живой сессии по имени файла.

        Нужен, чтобы привязать ползунок громкости к источнику, который
        назвал SMTC: там известно только имя вроде chrome.exe.
        """
        name = (name or "").lower()
        if not name.endswith(".exe"):
            return 0
        best, best_peak = 0, -1.0
        manager = self._get_manager()
        if not manager:
            return 0
        sessions = c_void_p()
        if _method(manager, MGR_GET_ENUMERATOR, POINTER(c_void_p))(
                manager, byref(sessions)) < 0 or not sessions:
            return 0
        try:
            count = c_int()
            _method(sessions, ENUM_GET_COUNT, POINTER(c_int))(sessions,
                                                              byref(count))
            for index in range(count.value):
                item = self._read_session(sessions, index)
                if item is None:
                    continue
                peak, app_info = item
                # Процессов с одним именем бывает много (тот же браузер):
                # берём тот, что действительно звучит.
                if app_info.exe.lower() == name and peak > best_peak:
                    best, best_peak = app_info.pid, peak
        finally:
            _release(sessions)
        return best

    def icon_for(self, pid):
        """Значок приложения — им подменяем обложку, когда её нет."""
        path = process_path(pid)
        if not path:
            return None
        cached = self._icons.get(path)
        if cached is not None:
            return cached
        icon = QFileIconProvider().icon(QFileInfo(path))
        pixmap = icon.pixmap(256, 256) if not icon.isNull() else None
        if pixmap is not None and pixmap.isNull():
            pixmap = None
        self._icons[path] = pixmap
        return pixmap

    def _drop_gone(self, alive):
        """
        Отпускаем интерфейсы приложений, которых в списке больше нет.

        Программа отыграла и закрылась — держать её громкость незачем, а
        сама по себе ссылка не освободится.
        """
        for pid in [p for p in self._volume_of if p not in alive]:
            _release(self._volume_of.pop(pid))
        for pid in [p for p in self._title_owner if p not in alive]:
            self._title_owner.pop(pid, None)

    def _read_session(self, sessions, index, alive=None):
        control = c_void_p()
        if _method(sessions, ENUM_GET_SESSION, c_int, POINTER(c_void_p))(
                sessions, index, byref(control)) < 0 or not control:
            return None
        control2 = c_void_p()
        try:
            if _method(control, 0, POINTER(GUID), POINTER(c_void_p))(
                    control, byref(GUID(IID_IAudioSessionControl2)),
                    byref(control2)) < 0 or not control2:
                return None
            state = c_int()
            if _method(control2, CTL_GET_STATE, POINTER(c_int))(
                    control2, byref(state)) < 0:
                return None
            if state.value != STATE_ACTIVE:
                return None
            peak = self._peak(control)
            # Системные звуки — не музыка: щелчки и уведомления показывать нечего.
            if _method(control2, CTL2_IS_SYSTEM_SOUNDS)(control2) == 0:
                return None
            pid = wintypes.DWORD()
            _method(control2, CTL2_GET_PROCESS_ID, POINTER(wintypes.DWORD))(
                control2, byref(pid))
            if not pid.value:
                return None
            if alive is not None:
                alive.add(pid.value)
            name = ctypes.c_wchar_p()
            _method(control2, CTL_GET_DISPLAY_NAME,
                    POINTER(ctypes.c_wchar_p))(control2, byref(name))
            exe = process_name(pid.value)
            label = (name.value or "").strip()
            # Подпись сессии у большинства приложений либо пустая, либо ссылка на
            # строку в ресурсах вида @%SystemRoot%\...,-202 — тогда берём имя по
            # файлу, тем же справочником, что и обычный путь через SMTC.
            if not label or label.startswith("@"):
                label = app_name(exe)
            return peak, AudioApp(pid.value, exe, label, self._title(pid.value))
        finally:
            _release(control2)
            _release(control)

    @staticmethod
    def _peak(control):
        """Текущий уровень сигнала сессии, 0..1. Тишина — ровно ноль."""
        meter = c_void_p()
        if _method(control, 0, POINTER(GUID), POINTER(c_void_p))(
                control, byref(GUID(IID_IAudioMeterInformation)),
                byref(meter)) < 0 or not meter:
            return 0.0
        try:
            value = c_float()
            if _method(meter, METER_GET_PEAK, POINTER(c_float))(
                    meter, byref(value)) < 0:
                return 0.0
            return float(value.value)
        finally:
            _release(meter)

    def _title(self, pid):
        """
        Заголовок окна с запоминанием, чьё это окно.

        Поиск родителя стоит около 10 мс — снимок списка процессов не бесплатен.
        Найденного владельца окна запоминаем, и дальше опрос стоит полмиллисекунды.
        """
        owner = self._title_owner.get(pid)
        if owner:
            title = window_title(owner)
            if title:
                return title
        title = ""
        walker = pid
        seen = set()
        for _ in range(4):
            if not walker or walker in seen:
                break
            seen.add(walker)
            title = window_title(walker)
            if title:
                self._title_owner[pid] = walker
                return title
            walker = parent_pid(walker)
        self._title_owner.pop(pid, None)
        return title

    # --- громкость приложения ---------------------------------------------- #

    def _simple_volume(self, pid):
        """ISimpleAudioVolume нужной сессии. Держим по процессу, пока живёт."""
        cached = self._volume_of.get(pid)
        if cached:
            return cached
        manager = self._get_manager()
        if not manager:
            return None
        sessions = c_void_p()
        if _method(manager, MGR_GET_ENUMERATOR, POINTER(c_void_p))(
                manager, byref(sessions)) < 0 or not sessions:
            return None
        try:
            count = c_int()
            _method(sessions, ENUM_GET_COUNT, POINTER(c_int))(sessions,
                                                              byref(count))
            for index in range(count.value):
                control = c_void_p()
                if _method(sessions, ENUM_GET_SESSION, c_int,
                           POINTER(c_void_p))(sessions, index,
                                              byref(control)) < 0:
                    continue
                control2 = c_void_p()
                try:
                    _method(control, 0, POINTER(GUID), POINTER(c_void_p))(
                        control, byref(GUID(IID_IAudioSessionControl2)),
                        byref(control2))
                    if not control2:
                        continue
                    owner = wintypes.DWORD()
                    _method(control2, CTL2_GET_PROCESS_ID,
                            POINTER(wintypes.DWORD))(control2, byref(owner))
                    if owner.value != pid:
                        continue
                    volume = c_void_p()
                    _method(control, 0, POINTER(GUID), POINTER(c_void_p))(
                        control, byref(GUID(IID_ISimpleAudioVolume)),
                        byref(volume))
                    if volume:
                        self._volume_of[pid] = volume
                        return volume
                finally:
                    _release(control2)
                    _release(control)
        finally:
            _release(sessions)
        return None

    def level(self, pid):
        ptr = self._simple_volume(pid)
        if not ptr:
            return None
        value = c_float()
        if _method(ptr, VOL_GET_MASTER, POINTER(c_float))(ptr, byref(value)) < 0:
            self._volume_of.pop(pid, None)
            return None
        return max(0.0, min(1.0, float(value.value)))

    def muted(self, pid):
        ptr = self._simple_volume(pid)
        if not ptr:
            return False
        state = c_int()
        if _method(ptr, VOL_GET_MUTE, POINTER(c_int))(ptr, byref(state)) < 0:
            self._volume_of.pop(pid, None)
            return False
        return bool(state.value)

    def set_level(self, pid, value):
        ptr = self._simple_volume(pid)
        if not ptr:
            return False
        value = max(0.0, min(1.0, float(value)))
        if _method(ptr, VOL_SET_MASTER, c_float, POINTER(GUID))(
                ptr, c_float(value), None) < 0:
            self._volume_of.pop(pid, None)
            return False
        if value > 0 and self.muted(pid):
            self.set_muted(pid, False)
        return True

    def set_muted(self, pid, muted):
        ptr = self._simple_volume(pid)
        if not ptr:
            return False
        if _method(ptr, VOL_SET_MUTE, c_int, POINTER(GUID))(
                ptr, 1 if muted else 0, None) < 0:
            self._volume_of.pop(pid, None)
            return False
        return True

    # --- уборка ------------------------------------------------------------ #

    def _forget(self):
        for ptr in self._volume_of.values():
            _release(ptr)
        self._volume_of.clear()
        self._title_owner.clear()
        _release(self._manager)
        self._manager = None

    def shutdown(self):
        self._forget()
