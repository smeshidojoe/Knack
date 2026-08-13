"""
Сама панель: выезжает из свободного края экрана, прячется, когда курсор ушёл.

Окно — Qt.Tool без рамки, поверх всех, с WS_EX_NOACTIVATE: панель не должна
забирать фокус у активной программы, иначе каждое открытие сбивало бы набор
текста. Из-за этого на события мыши окна полагаться нельзя (курсор часто вне
окна), и положение курсора опрашивается таймером — тот же приём, что в Cyclop.
"""

import ctypes
import time

from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRect, Qt,
                            QTimer, Signal)
from PySide6.QtGui import QCursor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from ..core import icons
from ..core import scale
from ..core.constants import PANEL_H, PANEL_RADIUS, PANEL_W, RAIL_W
from ..core.scale import s, sf
from ..core.taskbar import panel_edge
from . import theme
from .pages.media import MediaPage
from .pages.stubs import (ClipboardPage, SettingsPage, ShelfPage, SnippetsPage,
                          TranslatePage)
from .tabbar import TabBar
from .widgets.text import Text

WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
GWL_EXSTYLE = -20
VK_LBUTTON = 0x01

SHOW_MS = 220
HIDE_MS = 170
TRIGGER_H = 3        # высота зоны у края экрана, px макета
LEAVE_MARGIN = 10    # запас вокруг панели, px макета

LABEL_X, LABEL_Y, LABEL_H, LABEL_W = 15, 9, 11, 140


def _mouse_down():
    """Нажата ли левая кнопка — глобально, независимо от фокуса."""
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
    except Exception:
        return False


class Overlay(QWidget):
    opened = Signal()
    closed = Signal()

    def __init__(self, settings, media_service, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._open = False
        self._out_since = None
        self._edge = panel_edge()
        self._screen = None
        self._laid_out = False

        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.rail = TabBar(self)
        self.rail.selected.connect(self.set_tab)
        self.label = Text(self, role="text_muted")

        self.pages = {}
        for page in (MediaPage(media_service, self), ShelfPage(self),
                     ClipboardPage(self), SnippetsPage(self),
                     TranslatePage(self), SettingsPage(self)):
            self.pages[page.key] = page
            page.hide()

        self._current = None

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.finished.connect(self._on_anim_done)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

        self.apply_scale(force=True)
        self.set_tab(settings.get("last_tab", "media"), save=False)

    # --- вкладки --------------------------------------------------------- #

    def set_tab(self, key, save=True):
        page = self.pages.get(key)
        if page is None or key == self._current:
            return
        if self._current:
            old = self.pages[self._current]
            old.on_hide()
            old.hide()
        self._current = key
        self.rail.set_current(key)
        self.label.set_text(page.title)
        page.show()
        page.raise_()
        self.rail.raise_()
        self.label.raise_()
        if self._open:
            page.on_show()
        if save:
            self.settings["last_tab"] = key

    def current_page(self):
        return self.pages.get(self._current)

    # --- масштаб и раскладка --------------------------------------------- #

    def _target_screen(self):
        if self.settings.get("monitor") == "primary":
            return QGuiApplication.primaryScreen()
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def apply_scale(self, force=False):
        """Пересчитывает масштаб под целевой экран и, если он изменился,
        перекладывает всё. Иконки кешируются по размеру — кеш сбрасываем."""
        screen = self._target_screen()
        changed = scale.set_from_screen(screen, self.settings.get("scale_override", 0.0))
        self._screen = screen
        if changed or force or not self._laid_out:
            icons.clear_cache()
            self.relayout()
        return screen

    def relayout(self):
        self.setFixedSize(s(PANEL_W), s(PANEL_H))
        self.rail.setGeometry(0, 0, s(RAIL_W), s(PANEL_H))
        self.rail.relayout()

        self.label.set_font_px(s(9), "Bold")
        self.label.setGeometry(s(LABEL_X), s(LABEL_Y), s(LABEL_W), s(LABEL_H))

        for page in self.pages.values():
            page.setGeometry(0, 0, s(PANEL_W), s(PANEL_H))
            page.relayout()

        self.rail.raise_()
        self.label.raise_()
        self._laid_out = True

    # --- позиция на экране ----------------------------------------------- #

    def _positions(self, screen):
        """(закрытая, открытая) позиции окна для текущего края экрана."""
        geo = screen.geometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        gap = s(self.settings.get("edge_gap", 0))
        if self._edge == "bottom":
            return (QPoint(x, geo.bottom() + 1),
                    QPoint(x, geo.bottom() + 1 - self.height() - gap))
        return (QPoint(x, geo.y() - self.height()),
                QPoint(x, geo.y() + gap))

    def _trigger_rect(self, screen):
        geo = screen.geometry()
        x = geo.x() + (geo.width() - self.width()) // 2
        h = max(2, s(TRIGGER_H))
        if self._edge == "bottom":
            return QRect(x, geo.bottom() + 1 - h, self.width(), h)
        return QRect(x, geo.y(), self.width(), h)

    # --- показ и скрытие -------------------------------------------------- #

    def is_open(self):
        return self._open

    def open_panel(self):
        screen = self.apply_scale()
        self._edge = panel_edge()
        closed_pos, open_pos = self._positions(screen)

        was_open = self._open
        self._open = True
        self._out_since = None

        if not self.isVisible():
            self.move(closed_pos)
            self.show()
            self._apply_ex_style()
        self.raise_()

        page = self.current_page()
        if page and not was_open:
            page.on_show()

        self._anim.stop()
        self._anim.setDuration(SHOW_MS)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(open_pos)
        self._anim.start()

        self._sync_timer()
        if not was_open:
            self.opened.emit()

    def close_panel(self):
        if not self._open and not self.isVisible():
            return
        self._open = False
        self._out_since = None
        screen = self._screen or self._target_screen()
        closed_pos, _ = self._positions(screen)

        page = self.current_page()
        if page:
            page.on_hide()

        self._anim.stop()
        self._anim.setDuration(HIDE_MS)
        self._anim.setEasingCurve(QEasingCurve.InCubic)
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(closed_pos)
        self._anim.start()

        self._sync_timer()
        self.closed.emit()

    def toggle(self):
        if self._open:
            self.close_panel()
        else:
            self.open_panel()

    def _on_anim_done(self):
        if not self._open:
            self.hide()

    # --- слежение за курсором --------------------------------------------- #

    def _hover_enabled(self):
        return "hover" in self.settings.get("trigger", "hover+hotkey")

    def _sync_timer(self):
        need = self._open or self._hover_enabled()
        if need and not self._timer.isActive():
            self._timer.start(16 if self._open else 32)
        elif need:
            self._timer.setInterval(16 if self._open else 32)
        elif self._timer.isActive():
            self._timer.stop()

    def start_watching(self):
        self._sync_timer()

    def _tick(self):
        pos = QCursor.pos()
        if self._open:
            self._tick_open(pos)
        elif self._hover_enabled():
            screen = self._target_screen()
            if self._trigger_rect(screen).contains(pos):
                self.open_panel()

    def _tick_open(self, pos):
        mode = self.settings.get("hide_mode", "leave")
        if mode == "manual":
            return
        m = s(LEAVE_MARGIN)
        area = QRect(self.pos(), self.size()).adjusted(-m, -m, m, m)
        inside = area.contains(pos)

        if mode == "click_outside":
            if not inside and _mouse_down():
                self.close_panel()
            return

        # mode == "leave": уходим не сразу, чтобы панель не схлопывалась от
        # случайного выхода курсора на пиксель. Пока кнопка мыши нажата (тянут
        # ползунок перемотки), не закрываемся вовсе.
        if inside or _mouse_down():
            self._out_since = None
            return
        now = time.monotonic()
        if self._out_since is None:
            self._out_since = now
        elif (now - self._out_since) * 1000 >= self.settings.get("hide_delay_ms", 220):
            self.close_panel()

    # --- нативные флаги окна ---------------------------------------------- #

    def _apply_ex_style(self, focusable=False):
        """WS_EX_NOACTIVATE — окно не забирает фокус; WS_EX_TOOLWINDOW убирает
        панель из Alt+Tab."""
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_TOOLWINDOW
            if focusable:
                style &= ~WS_EX_NOACTIVATE
            else:
                style |= WS_EX_NOACTIVATE
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            pass

    def set_focusable(self, on):
        """Вкладке переводчика нужен ввод с клавиатуры — там фокус разрешаем."""
        self._apply_ex_style(focusable=bool(on))

    # --- отрисовка -------------------------------------------------------- #

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        r = sf(PANEL_RADIUS)
        path.addRoundedRect(0, 0, self.width(), self.height(), r, r)
        p.fillPath(path, theme.color("bg"))
