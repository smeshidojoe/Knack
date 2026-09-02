"""
Значок закрепления в углу чужого окна.

Маленькая кнопка-кнопка с канцелярской кнопкой: держится в правом верхнем углу
активного окна и ходит за ним. Клик закрепляет окно поверх остальных, повторный
снимает; закреплённое видно по перечёркнутому значку.

Значок один на всех: рисовать его сразу над каждым окном значило бы держать
столько же окошек и следить за каждым. Он переезжает к тому окну, с которым
человек сейчас работает, — а закреплённых окон при этом может быть сколько
угодно, флаг живёт в них самих.

Место под значок спрашиваем у самой Windows: DWM знает, где у окна кнопки
«свернуть/развернуть/закрыть», и мы встаём вплотную слева от них, а высоту берём
по ним же — получается ещё одна кнопка в том же ряду. У окон, которые рисуют
заголовок сами и границы кнопок не отдают, остаётся запасная прикидка по
системным метрикам.

Позицию считаем в физических пикселях и ставим окно через SetWindowPos: Qt
работает в логических точках, а GetWindowRect чужого окна отдаёт физические, и
на мониторе с масштабом смешивать их нельзя.
"""

import ctypes
from ctypes import wintypes

import time

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..core import icons
from . import theme

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

_HOOK_PROC = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD,
                                wintypes.HWND, wintypes.LONG, wintypes.LONG,
                                wintypes.DWORD, wintypes.DWORD)

# Типы объявляем явно: без них ctypes считает HWND обычным int, и окно с
# большим номером роняет вызов с OverflowError.
user32.GetWindowRect.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetWindowLongW.restype = wintypes.LONG
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
user32.SetWinEventHook.restype = wintypes.HANDLE
user32.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD,
                                   wintypes.HMODULE, _HOOK_PROC,
                                   wintypes.DWORD, wintypes.DWORD,
                                   wintypes.DWORD]
user32.UnhookWinEvent.restype = wintypes.BOOL
user32.UnhookWinEvent.argtypes = [wintypes.HANDLE]
try:
    user32.GetDpiForWindow.restype = wintypes.UINT
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
except AttributeError:
    pass        # до Windows 10 1607 такой функции нет

DWMWA_CAPTION_BUTTON_BOUNDS = 5
DWMWA_EXTENDED_FRAME_BOUNDS = 9   # видимые границы окна, без невидимой рамки
DWMWA_CLOAKED = 14                # окно скрыто оболочкой, хоть и «существует»

EVENT_SYSTEM_FOREGROUND = 0x0003
EVENT_OBJECT_LOCATIONCHANGE = 0x800B
WINEVENT_OUTOFCONTEXT = 0x0000
WINEVENT_SKIPOWNPROCESS = 0x0002
OBJID_WINDOW = 0

GWL_STYLE = -16
GWL_EXSTYLE = -20
WS_CAPTION = 0x00C00000
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002

FOLLOW_MS = 120          # запасной круг слежения; движение ловим событиями
# Окно должно продержаться два круга подряд: программы вроде MiniBin мигают
# служебным окном на долю секунды, и значок успевал выскочить в пустоту.
STABLE_TICKS = 2
MIN_SIDE = 120           # окно меньше этого — не окно, а всплывающая мелочь
# Закрепив окно, Windows поднимает его на самый верх «верхнего» слоя — выше
# нашего значка. Возвращаемся наверх сами, несколько раз подряд: команда
# закрепления уходит в очередь чужого окна и исполняется не мгновенно.
RERAISE_MS = (0, 60, 150, 320)
ICON_RATIO = 0.5         # доля стороны под сам глиф
IDLE_ALPHA = 0.82        # в покое чуть приглушён, под курсором — в полную силу
PROBE_MS = 400           # как часто подглядываем цвет заголовка под значком
LIGHT_LEVEL = 0.55       # ярче этого — заголовок светлый, значок делаем тёмным
INK_DARK = "#1B1B1B"

# Запасная прикидка, когда окно не отдаёт границы своих кнопок: высота заголовка
# и ширина трёх кнопок в стандартной теме Windows 10/11.
FALLBACK_CAPTION_H = 32
FALLBACK_RESERVE = 141
GAP = 4                  # зазор до соседней кнопки, чтобы не липнуть к ней


class PinBadge(QWidget):
    """clicked(hwnd) — по значку щёлкнули для окна hwnd."""

    clicked = Signal(int)

    def __init__(self, pin_service, parent=None):
        super().__init__(parent)
        self.pin = pin_service
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)

        self._hwnd = 0           # окно, за которым идём
        self._pinned = False
        self._hover = False
        self._styled = False
        self._side = 0           # текущая сторона значка в физических пикселях
        self._candidate = 0      # окно-кандидат и сколько кругов оно держится
        self._steady = 0
        self._light_bg = False   # под значком светлый заголовок
        self._probe_at = 0.0     # когда последний раз смотрели цвет

        self._timer = QTimer(self)
        self._timer.setInterval(FOLLOW_MS)
        self._timer.timeout.connect(self._follow)

        # Ссылку на обёртку держим сами: Windows зовёт её из своего кода, и
        # собранный сборщиком мусора объект уронил бы процесс.
        self._hook_proc = _HOOK_PROC(self._on_win_event)
        self._hook = 0

    # --- запуск ------------------------------------------------------------ #

    def start(self):
        self._timer.start()
        self._install_hook()

    def stop(self):
        self._timer.stop()
        self._remove_hook()
        self._hwnd = 0
        self.hide()

    def _install_hook(self):
        """
        Ловим перемещение окна событием, а не опросом.

        Опрос раз в 120 мс при перетаскивании выглядел так, будто значок едет
        за окном на верёвочке. Windows умеет сообщать о смене положения сразу —
        подписываемся и переставляемся в тот же миг.
        """
        if self._hook:
            return
        self._hook = user32.SetWinEventHook(
            EVENT_SYSTEM_FOREGROUND, EVENT_OBJECT_LOCATIONCHANGE, None,
            self._hook_proc, 0, 0,
            WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS)

    def _remove_hook(self):
        if self._hook:
            user32.UnhookWinEvent(self._hook)
            self._hook = 0

    def _on_win_event(self, _hook, event, hwnd, id_object, _id_child,
                      _thread, _time):
        if id_object != OBJID_WINDOW:
            return                      # курсор, подсказки, поля ввода — мимо
        if event == EVENT_SYSTEM_FOREGROUND or hwnd == self._hwnd:
            self._follow()

    def target(self):
        return self._hwnd

    # --- слежение ---------------------------------------------------------- #

    def _follow(self):
        hwnd = user32.GetForegroundWindow()
        if not self._suitable(hwnd):
            self._candidate = self._steady = 0
            self._hwnd = 0
            if self.isVisible():
                self.hide()
            return

        # Мигнувшее окно не должно утаскивать значок за собой.
        if hwnd != self._candidate:
            self._candidate, self._steady = hwnd, 1
        else:
            self._steady += 1
        if self._steady < STABLE_TICKS and hwnd != self._hwnd:
            return

        rect = self._visible_rect(hwnd)
        if rect is None:
            return
        if self._fullscreen(rect):
            # Поверх игры или полноэкранного видео значок только мешает.
            self._hwnd = 0
            self.hide()
            return

        self._hwnd = hwnd
        pinned = self.pin._is_topmost(hwnd)
        if pinned != self._pinned:
            self._pinned = pinned
            self.update()
        self._place(rect)

    def _suitable(self, hwnd):
        if not hwnd:
            return False
        if self.pin._own_window(hwnd) or not self.pin._pinnable(hwnd):
            return False
        if not user32.GetWindowLongW(hwnd, GWL_STYLE) & WS_CAPTION:
            # Без заголовка — не окно программы, а меню, подсказка или
            # всплывашка. Контекстное меню вдобавок само по себе лежит поверх
            # всех, и значок показывал его закреплённым, хотя закрепления нет.
            return False
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if style & WS_EX_TOOLWINDOW:
            return False        # служебные окна закреплять незачем
        if self._cloaked(hwnd):
            return False        # окно есть, а на экране его нет
        rect = self._visible_rect(hwnd)
        if rect is None:
            return False
        ratio = self._window_ratio(hwnd, 1.0)
        least = MIN_SIDE * ratio
        return (rect.right - rect.left) >= least and (rect.bottom - rect.top) >= least

    @staticmethod
    def _cloaked(hwnd):
        value = ctypes.c_int(0)
        hr = dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), DWMWA_CLOAKED,
                                          ctypes.byref(value),
                                          ctypes.sizeof(value))
        return hr == 0 and value.value != 0

    @staticmethod
    def _visible_rect(hwnd):
        """
        Видимые границы окна.

        GetWindowRect отдаёт их вместе с невидимой рамкой изменения размера — на
        Windows 10 и 11 это лишние 7 px слева, справа и снизу, и значок из-за них
        уезжал вправо, под кнопки заголовка.
        """
        rect = wintypes.RECT()
        hr = dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd),
                                          DWMWA_EXTENDED_FRAME_BOUNDS,
                                          ctypes.byref(rect),
                                          ctypes.sizeof(rect))
        if hr == 0 and rect.right > rect.left and rect.bottom > rect.top:
            return rect
        plain = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(plain)):
            return plain
        return None

    @staticmethod
    def _fullscreen(rect):
        for screen in QGuiApplication.screens():
            geo = screen.geometry()
            ratio = screen.devicePixelRatio()
            if (abs(rect.left - geo.x() * ratio) < 2
                    and abs(rect.top - geo.y() * ratio) < 2
                    and abs((rect.right - rect.left) - geo.width() * ratio) < 2
                    and abs((rect.bottom - rect.top) - geo.height() * ratio) < 2):
                return True
        return False

    @staticmethod
    def _window_ratio(hwnd, fallback):
        """
        Масштаб экрана, на котором висит окно.

        Спрашиваем у Windows по самому окну: на мониторах с разным масштабом это
        точнее, чем догадываться по координатам.
        """
        try:
            dpi = user32.GetDpiForWindow(wintypes.HWND(hwnd))
            if dpi:
                return dpi / 96.0
        except Exception:
            pass
        return fallback

    def _ratio_at(self, x, y):
        for screen in QGuiApplication.screens():
            geo = screen.geometry()
            ratio = screen.devicePixelRatio()
            if (geo.x() * ratio <= x < (geo.x() + geo.width()) * ratio
                    and geo.y() * ratio <= y < (geo.y() + geo.height()) * ratio):
                return ratio
        primary = QGuiApplication.primaryScreen()
        return primary.devicePixelRatio() if primary else 1.0

    @staticmethod
    def _caption_buttons(hwnd):
        """
        Границы кнопок заголовка в координатах окна. None — окно не отвечает.

        Так делает и сама Windows, когда показывает подсказки к этим кнопкам:
        отдельного способа узнать, где заканчивается «крестик», нет.
        """
        rect = wintypes.RECT()
        hr = dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd),
                                          DWMWA_CAPTION_BUTTON_BOUNDS,
                                          ctypes.byref(rect),
                                          ctypes.sizeof(rect))
        if hr != 0:
            return None
        if rect.right <= rect.left or rect.bottom <= rect.top:
            return None
        return rect

    def _place(self, rect):
        """rect — видимые границы окна; кнопки заголовка DWM меряет от его угла."""
        ratio = self._window_ratio(self._hwnd,
                                   self._ratio_at(rect.right - 1, rect.top))
        buttons = self._caption_buttons(self._hwnd)
        if buttons is not None:
            # Встаём следующей кнопкой в том же ряду и той же высоты.
            side = buttons.bottom - buttons.top
            window = wintypes.RECT()
            user32.GetWindowRect(self._hwnd, ctypes.byref(window))
            x = window.left + buttons.left - side - int(round(GAP * ratio))
            y = window.top + buttons.top
        else:
            side = int(round(FALLBACK_CAPTION_H * ratio))
            x = int(rect.right - round((FALLBACK_RESERVE + GAP) * ratio) - side)
            y = rect.top
        side = max(16, int(side))
        x, y = self._clamp_into(x, y, side, rect)
        if not self.isVisible():
            self.show()
            self._apply_ex_style()
        if side != self._side:
            self._side = side
            self.update()
        user32.SetWindowPos(int(self.winId()), HWND_TOPMOST, int(x), int(y),
                            side, side, SWP_NOACTIVATE)
        self._probe_background(int(x), int(y), side)

    def _probe_background(self, x, y, side):
        """
        Подсматриваем цвет заголовка слева от значка.

        Белая кнопка на светлом заголовке пропадает, а какой он у чужого окна —
        заранее не известно: тему заголовка приложение выбирает само. Снимок
        одного пикселя стоит десятые доли миллисекунды, берём его изредка.
        """
        now = time.monotonic()
        if now - self._probe_at < PROBE_MS / 1000.0:
            return
        self._probe_at = now
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        # Левее значка: под собой мы бы сняли собственную прозрачную поверхность.
        shot = screen.grabWindow(0, x - max(4, side // 4), y + side // 2, 1, 1)
        image = shot.toImage() if not shot.isNull() else None
        if image is None or image.isNull():
            return
        color = image.pixelColor(0, 0)
        level = (0.299 * color.redF() + 0.587 * color.greenF()
                 + 0.114 * color.blueF())
        light = level > LIGHT_LEVEL
        if light != self._light_bg:
            self._light_bg = light
            self.update()

    @staticmethod
    def _clamp_into(x, y, side, rect):
        """
        Загоняем значок внутрь видимых границ окна.

        У развёрнутого окна рамка уходит за край экрана, и посадка по кнопкам
        заголовка выносила значок выше самого окна — снаружи это выглядело как
        «значок вылез за границы».
        """
        bottom = max(rect.top, rect.bottom - side)
        right = max(rect.left, rect.right - side)
        return (max(rect.left, min(int(x), right)),
                max(rect.top, min(int(y), bottom)))

    def _apply_ex_style(self):
        """Значок не забирает фокус и не мелькает в Alt+Tab."""
        if self._styled:
            return
        try:
            hwnd = int(self.winId())
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                                  style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
            self._styled = True
        except Exception:
            pass

    # --- события ----------------------------------------------------------- #

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self._hwnd:
            return
        if not self.rect().contains(event.position().toPoint()):
            return
        self.clicked.emit(self._hwnd)
        # Состояние перечитываем сразу, не дожидаясь следующего круга слежения.
        self._pinned = self.pin._is_topmost(self._hwnd)
        self.update()
        for delay in RERAISE_MS:
            QTimer.singleShot(delay, self._reraise)

    def refresh(self):
        """Состояние окна поменяли снаружи — перечитать и всплыть обратно."""
        for delay in RERAISE_MS:
            QTimer.singleShot(delay, self._reraise)

    def _reraise(self):
        """
        Поднять значок обратно над только что закреплённым окном.

        Без этого он пропадал на глазах: закрепление ставит окно выше всех, а
        значок всплывал обратно только на следующем круге слежения. При снятии
        закрепления окно уезжает вниз, и мелькания не было — отсюда и разница.
        """
        if not self._hwnd or not self.isVisible():
            return
        user32.SetWindowPos(int(self.winId()), HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        pinned = self.pin._is_topmost(self._hwnd)
        if pinned != self._pinned:
            self._pinned = pinned
            self.update()

    # --- отрисовка --------------------------------------------------------- #

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        # Без подложки: в чужом заголовке любая наша плашка выглядит заплаткой.
        # Чтобы белый значок не пропал на светлом заголовке, под него кладётся
        # тёмный контур — тот же глиф, сдвинутый на пиксель во все стороны.
        glyph = max(8, int(round(min(self.width(), self.height()) * ICON_RATIO)))
        left = (self.width() - glyph) / 2.0
        top = (self.height() - glyph) / 2.0
        source = QRectF(0, 0, glyph, glyph)

        ink = QColor(INK_DARK) if self._light_bg else theme.color("text_primary")
        halo = QColor(Qt.white) if self._light_bg else QColor(0, 0, 0)
        shade = icons.pixmap("snippets", glyph, halo)
        p.setOpacity(0.45)
        step = max(1.0, glyph / 14.0)
        for dx, dy in ((-step, 0), (step, 0), (0, -step), (0, step)):
            p.drawPixmap(QRectF(left + dx, top + dy, glyph, glyph), shade, source)

        p.setOpacity(1.0 if self._hover else IDLE_ALPHA)
        pixmap = icons.pixmap("snippets", glyph, ink)
        # Центруем по дробным координатам: при нечётной разнице целочисленное
        # деление сдвигало глиф на полпикселя вверх и влево.
        p.drawPixmap(QRectF(left, top, glyph, glyph), pixmap, source)

        if not self._pinned:
            return
        # Перечёркнутый значок = окно закреплено.
        box = QRectF(left, top, glyph, glyph).adjusted(glyph * 0.04, glyph * 0.04,
                                                       -glyph * 0.04, -glyph * 0.04)
        width = max(1.4, glyph * 0.11)
        # Полоса тоже с тёмной подложкой — по той же причине, что и сам значок.
        shade_pen = QPen(halo)
        shade_pen.setWidthF(width + step * 1.6)
        shade_pen.setCapStyle(Qt.RoundCap)
        p.setOpacity(0.45)
        p.setPen(shade_pen)
        p.drawLine(box.bottomLeft(), box.topRight())

        pen = QPen(ink)
        pen.setWidthF(width)
        pen.setCapStyle(Qt.RoundCap)
        p.setOpacity(1.0 if self._hover else IDLE_ALPHA)
        p.setPen(pen)
        p.drawLine(box.bottomLeft(), box.topRight())
