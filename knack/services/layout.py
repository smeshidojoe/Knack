"""
Смена раскладки у выделенного текста.

«Ghbdtn» вместо «Привет» — набрал, не переключив раскладку. По сочетанию клавиш
выделенный текст переписывается так, как если бы раскладка была правильной.
Направление выбирается само, по преобладанию букв.

Прочитать выделение в чужом окне нельзя — такого API нет. Поэтому работаем так
же, как Punto Switcher: посылаем в активное окно Ctrl+C, забираем текст из
буфера, переписываем, кладём обратно и посылаем Ctrl+V. Прежнее содержимое
буфера возвращается следом, чтобы фокус на нём не потерялся.

Ждём не «на глазок», а по номеру буфера обмена: Windows увеличивает его на
каждое изменение, и это единственный надёжный признак, что программа успела
ответить на Ctrl+C.
"""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QMimeData, QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from ..core import logbook

# --- таблица позиций клавиш -------------------------------------------------- #
# Строки идут по рядам клавиатуры и соответствуют друг другу посимвольно.
_LOWER_EN = "`qwertyuiop[]asdfghjkl;'zxcvbnm,./"
_LOWER_RU = "ёйцукенгшщзхъфывапролджэячсмитьбю."
_UPPER_EN = '~QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>?'
_UPPER_RU = "ЁЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,"

EN_TO_RU = {}
RU_TO_EN = {}
for _en, _ru in ((_LOWER_EN, _LOWER_RU), (_UPPER_EN, _UPPER_RU)):
    for _a, _b in zip(_en, _ru):
        EN_TO_RU[_a] = _b
        RU_TO_EN[_b] = _a

_CYRILLIC = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
                "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")


# --- раскладки, установленные в системе -------------------------------------- #
#
# Встроенная таблица выше знает только про русскую и английскую. У человека с
# немецкой или украинской она бы врала, поэтому таблицы строим у самой Windows:
# для каждой установленной раскладки спрашиваем, какой символ даёт каждая
# клавиша. Встроенная остаётся запасным вариантом, если спросить не вышло.

# Клавиши, которые вообще участвуют: буквы, цифры и знаки основного блока.
_VK_CODES = (tuple(range(0x30, 0x3A)) + tuple(range(0x41, 0x5B))
             + (0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF, 0xC0,
                0xDB, 0xDC, 0xDD, 0xDE, 0xE2))

MAPVK_VK_TO_VSC = 0
VK_SHIFT_STATE = 0x10


def installed_layouts():
    """Список HKL установленных раскладок клавиатуры."""
    try:
        user32 = ctypes.windll.user32
        count = user32.GetKeyboardLayoutList(0, None)
        if count <= 0:
            return []
        buffer = (ctypes.c_void_p * count)()
        user32.GetKeyboardLayoutList(count, buffer)
        return [h for h in buffer if h]
    except Exception:
        logbook.exc("layout list")
        return []


def _layout_tables(hkl):
    """
    Для одной раскладки: символ -> (клавиша, шифт) и обратно.

    ToUnicodeEx умеет оставить в состоянии клавиатуры «мёртвую» клавишу, и
    следующий настоящий ввод пользователя пришёл бы искажённым. Поэтому после
    каждого такого ответа состояние сбрасывается повторным вызовом.
    """
    user32 = ctypes.windll.user32
    to_char, from_key = {}, {}
    state = (ctypes.c_ubyte * 256)()
    buffer = ctypes.create_unicode_buffer(8)
    for vk in _VK_CODES:
        scan = user32.MapVirtualKeyExW(vk, MAPVK_VK_TO_VSC, hkl)
        for shift in (0, 1):
            state[VK_SHIFT_STATE] = 0x80 if shift else 0
            written = user32.ToUnicodeEx(vk, scan, state, buffer, len(buffer),
                                         0, hkl)
            if written < 0:
                # Мёртвая клавиша: повторяем вызов, чтобы очистить состояние.
                user32.ToUnicodeEx(vk, scan, state, buffer, len(buffer), 0, hkl)
                continue
            if written != 1:
                continue
            char = buffer[0]
            if not char.isprintable() or char == " ":
                continue
            key = (vk, shift)
            to_char.setdefault(char, key)
            from_key.setdefault(key, char)
    return to_char, from_key


class _SystemLayouts:
    """Таблицы раскладок системы; перестраиваются, если список изменился."""

    def __init__(self):
        self._hkls = []
        self._tables = {}

    def refresh(self):
        hkls = installed_layouts()
        if hkls == self._hkls and self._tables:
            return bool(self._tables)
        self._hkls, self._tables = hkls, {}
        for hkl in hkls:
            try:
                self._tables[hkl] = _layout_tables(hkl)
            except Exception:
                logbook.exc("layout table")
        return len(self._tables) >= 2

    def pick(self, text):
        """(откуда, куда) — по тому, какой раскладке текст подходит больше."""
        letters = [c for c in text if c.isalpha()]
        if not letters or len(self._tables) < 2:
            return None, None
        scores = {}
        for hkl, (to_char, _from_key) in self._tables.items():
            scores[hkl] = sum(1 for c in letters if c in to_char)
        source = max(scores, key=lambda h: scores[h])
        if not scores[source]:
            return None, None
        # Цель — следующая раскладка по кругу: при двух установленных это
        # единственная оставшаяся, при трёх и больше даёт предсказуемый порядок.
        order = [h for h in self._hkls if h in self._tables]
        target = order[(order.index(source) + 1) % len(order)]
        return source, target

    def convert(self, text):
        source, target = self.pick(text)
        if source is None:
            return None
        to_char = self._tables[source][0]
        from_key = self._tables[target][1]
        out = []
        for char in text:
            key = to_char.get(char)
            out.append(from_key.get(key, char) if key else char)
        return "".join(out)


_system = _SystemLayouts()


def convert(text, use_system=True):
    """
    Переписывает текст в другой раскладке. Направление — по буквам.

    Знаки препинания переводятся вместе с выбранным направлением: точка в
    русской раскладке набирается той же клавишей, что слэш в английской.
    """
    if not text:
        return text
    if use_system:
        try:
            if _system.refresh():
                result = _system.convert(text)
                if result is not None:
                    return result
        except Exception:
            logbook.exc("layout system convert")

    cyrillic = sum(1 for char in text if char in _CYRILLIC)
    latin = sum(1 for char in text if ("a" <= char <= "z") or ("A" <= char <= "Z"))
    if not cyrillic and not latin:
        return text
    table = RU_TO_EN if cyrillic >= latin else EN_TO_RU
    return "".join(table.get(char, char) for char in text)


# --- синтетический ввод ------------------------------------------------------ #

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

VK_CONTROL, VK_MENU, VK_SHIFT = 0x11, 0x12, 0x10
VK_LWIN, VK_RWIN = 0x5B, 0x5C
VK_C, VK_V = 0x43, 0x56


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


def _key(vk, up=False):
    event = _INPUT()
    event.type = INPUT_KEYBOARD
    event.union.ki = _KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP if up else 0, 0, None)
    return event


def _send(events):
    if not events:
        return
    array = (_INPUT * len(events))(*events)
    ctypes.windll.user32.SendInput(len(events), ctypes.byref(array),
                                   ctypes.sizeof(_INPUT))


def _down(vk):
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def _send_combo(vk):
    """
    Ctrl+<клавиша> в активное окно.

    Сочетание вызова всё ещё зажато физически, и если не отпустить Alt с Shift,
    в окно уедет Ctrl+Alt+C вместо Ctrl+C.
    """
    events = []
    for modifier in (VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN):
        if _down(modifier):
            events.append(_key(modifier, up=True))
    events += [_key(VK_CONTROL), _key(vk), _key(vk, up=True),
               _key(VK_CONTROL, up=True)]
    _send(events)


def _sequence():
    try:
        return int(ctypes.windll.user32.GetClipboardSequenceNumber())
    except Exception:
        return 0


class LayoutSwitcher(QObject):
    """Сигнал `finished(True)` — текст заменён, `finished(False)` — не вышло."""

    finished = Signal(bool)

    POLL_MS = 15         # как часто спрашиваем, ответило ли окно на Ctrl+C
    POLL_TRIES = 34      # суммарно около полусекунды
    PASTE_MS = 120       # пауза перед возвратом прежнего буфера

    def __init__(self, settings, clipboard, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.clipboard = clipboard
        self._busy = False
        self._saved = None
        self._seq = 0
        self._tries = 0

        self._poll = QTimer(self)
        self._poll.setInterval(self.POLL_MS)
        self._poll.timeout.connect(self._check_clipboard)

    def enabled(self):
        return bool(self.settings.get("layout_switch_enabled", True))

    # --- ход работы -------------------------------------------------------- #

    def trigger(self):
        """Вызывается по горячей клавише."""
        if self._busy or not self.enabled():
            return
        self._busy = True
        self._saved = self._read_clipboard()
        self._seq = _sequence()
        self._tries = self.POLL_TRIES
        self.clipboard.suppress()
        try:
            _send_combo(VK_C)
        except Exception:
            logbook.exc("layout copy")
            self._abort()
            return
        self._poll.start()

    def _check_clipboard(self):
        self.clipboard.suppress()
        if _sequence() == self._seq:
            self._tries -= 1
            if self._tries <= 0:
                # Окно не ответило: выделения нет либо программа не принимает
                # синтетический ввод (так ведут себя окна с правами админа).
                self._poll.stop()
                self._abort()
            return

        self._poll.stop()
        text = QGuiApplication.clipboard().text()
        result = convert(text)
        if not text.strip() or result == text:
            self._abort()
            return

        self.clipboard.suppress()
        QGuiApplication.clipboard().setText(result)
        try:
            _send_combo(VK_V)
        except Exception:
            logbook.exc("layout paste")
        QTimer.singleShot(self.PASTE_MS, self._restore)
        self.finished.emit(True)

    def _abort(self):
        self._restore()
        self.finished.emit(False)

    def _restore(self):
        if not self._busy:
            return
        self._busy = False
        if self.settings.get("layout_restore_clipboard", True):
            self.clipboard.suppress()
            self._write_clipboard(self._saved)
        self._saved = None

    # --- сохранение и возврат буфера ---------------------------------------- #

    @staticmethod
    def _read_clipboard():
        """
        Слепок буфера, который переживёт наши записи.

        Забираем значения сразу: QMimeData из буфера принадлежит Qt и меняется
        вместе с ним. Возвращаем текст, картинку и ссылки на файлы — форматы,
        которыми пользуются; внутренние форматы отдельных программ не восстановим.
        """
        try:
            mime = QGuiApplication.clipboard().mimeData()
            if mime is None:
                return None
            return {
                "text": mime.text() if mime.hasText() else None,
                "image": mime.imageData() if mime.hasImage() else None,
                "urls": list(mime.urls()) if mime.hasUrls() else None,
            }
        except Exception:
            logbook.exc("layout read clipboard")
            return None

    @staticmethod
    def _write_clipboard(saved):
        if not saved:
            return
        try:
            mime = QMimeData()
            empty = True
            if saved.get("text"):
                mime.setText(saved["text"])
                empty = False
            if saved.get("image") is not None:
                mime.setImageData(saved["image"])
                empty = False
            if saved.get("urls"):
                mime.setUrls(saved["urls"])
                empty = False
            if not empty:
                QGuiApplication.clipboard().setMimeData(mime)
        except Exception:
            logbook.exc("layout restore clipboard")
