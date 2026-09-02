"""
Сама панель: выезжает из свободного края экрана, прячется, когда курсор ушёл.

Окно — Qt.Tool без рамки, поверх всех, с WS_EX_NOACTIVATE: панель не должна
забирать фокус у активной программы, иначе каждое открытие сбивало бы набор
текста. Из-за этого на события мыши окна полагаться нельзя (курсор часто вне
окна), и положение курсора опрашивается таймером — тот же приём, что в Cyclop.

Выезд считается своими часами (ui/anim.py), а не QPropertyAnimation: последняя
жёстко привязана к 60 к/с, и на 180-герцовом мониторе движение выглядит рвано.
"""

import ctypes
import time

from PySide6.QtCore import QEasingCurve, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from ..core import i18n, icons, scale
from ..core.mouse import left_down
from ..core.constants import PANEL_H, PANEL_RADIUS, PANEL_W
from ..core.scale import s, sf
from ..core.taskbar import panel_edge
from . import anim, theme
from .anim import Tween
from .scale_preview import ScalePreview
from .update_overlay import UpdateOverlay
from .pages.clipboard import ClipboardPage
from .pages.media import MediaPage
from .pages.notes import NotesPage
from .pages.shelf import ShelfPage
from .pages.snippets import SnippetsPage
from .pages.settings import SettingsPage
from .pages.todo import TodoPage
from .pages.translate import TranslatePage
from .tabbar import TabBar
from .widgets.text import Text

WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
GWL_EXSTYLE = -20
SHOW_MS = 0.24
HIDE_MS = 0.18
TRIGGER_H = 3        # высота зоны у края экрана, px макета
LEAVE_MARGIN = 10    # запас вокруг панели, px макета

LABEL_X, LABEL_Y, LABEL_H, LABEL_W = 15, 9, 11, 140


class Overlay(QWidget):
    opened = Signal()
    closed = Signal()
    setting_changed = Signal(str)     # что поменяли в настройках
    hotkey_capture = Signal(bool)     # идёт захват сочетания

    def __init__(self, settings, services, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.services = services
        self._open = False
        self._out_since = None
        self._in_since = None
        self._edge = panel_edge()
        self._screen = None
        self._open_screen = None      # экран, на котором панель открыли
        self._laid_out = False
        self._slide_x = 0

        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # Файл можно бросить на панель с любой вкладки: она сама переключится
        # на полку. Вкладка полки принимает такие события сама, до нас они
        # доходят только с остальных.
        self.setAcceptDrops(True)

        self.rail = TabBar(self)
        self.rail.selected.connect(self.set_tab)
        self.label = Text(self, role="text_muted")

        self.pages = {}
        for page in (MediaPage(services.media, services.volume, self),
                     ShelfPage(services.shelf, services.clipboard, self),
                     ClipboardPage(services.clipboard, self),
                     SnippetsPage(services.snippets, services.clipboard, self),
                     NotesPage(services.notes, self),
                     TodoPage(services.todo, self),
                     TranslatePage(services.translator, settings, self),
                     SettingsPage(settings, self)):
            self.pages[page.key] = page
            page.hide()

        settings_page = self.pages["settings"]
        settings_page.changed.connect(self.setting_changed.emit)
        settings_page.capturing.connect(self.hotkey_capture.emit)

        self._current = None
        self._slide = Tween(self._on_slide, on_done=self._on_slide_done)

        self._preview = None       # призрак будущего размера, создаётся по нужде
        self.updating = UpdateOverlay(self)

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
        self.label.set_text(i18n.t("tab." + key))
        page.show()
        page.raise_()
        self.rail.raise_all()
        self.label.raise_()
        self.set_focusable(page.wants_keyboard)
        if self._open:
            page.on_show()
        if save:
            self.settings["last_tab"] = key

    def current_page(self):
        return self.pages.get(self._current)

    def retranslate(self):
        """Язык сменили — обновить подписи."""
        page = self.current_page()
        if page:
            self.label.set_text(i18n.t("tab." + page.key))
        for p in self.pages.values():
            p.retranslate()
        self.updating.retranslate()

    # --- масштаб и раскладка --------------------------------------------- #

    def _target_screen(self):
        if self.settings.get("monitor") == "primary":
            return QGuiApplication.primaryScreen()
        return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()

    def apply_scale(self, screen=None, force=False):
        """Пересчитывает масштаб под экран и, если он изменился, перекладывает
        всё. Иконки кешируются по размеру — кеш сбрасываем."""
        screen = screen or self._target_screen()
        changed = scale.set_from_screen(screen,
                                        self.settings.get("scale_override", 0.0),
                                        self.settings.get("ui_scale", 1.0))
        self._screen = screen
        anim.set_fps(self.settings.get("animation_fps", 0), screen)
        if changed or force or not self._laid_out:
            icons.clear_cache()
            self.relayout()
        return screen

    def preview_scale(self, user_scale):
        """
        Показывает, каким станет окно при таком размере.

        Саму панель во время перетаскивания не трогаем: она уезжала бы из-под
        курсора и шаг ощущался неровным.
        """
        screen = self._open_screen or self._target_screen()
        factor = scale.compute(screen, self.settings.get("scale_override", 0.0),
                               user_scale)
        geo = screen.geometry()
        width = int(round(PANEL_W * factor))
        height = int(round(PANEL_H * factor))
        gap = int(round(self.settings.get("edge_gap", 0) * factor))
        x = geo.x() + (geo.width() - width) // 2
        if self._edge == "bottom":
            y = geo.bottom() + 1 - height - gap
        else:
            y = geo.y() + gap

        if self._preview is None:
            self._preview = ScalePreview()
        self._preview.show_at(QRect(x, y, width, height),
                              radius=PANEL_RADIUS * factor)

    def ask_update(self, title):
        """Карточка с вопросом про найденную версию."""
        self.updating.setGeometry(0, 0, self.width(), self.height())
        self.updating.ask(title)
        self.updating.raise_()

    def start_update(self, title):
        """Затемняет панель и показывает карточку загрузки."""
        self.updating.setGeometry(0, 0, self.width(), self.height())
        self.updating.start(title)
        self.updating.raise_()

    def update_progress(self, fraction, title=None):
        if title:
            self.updating.set_title(title)
        self.updating.set_progress(fraction)

    def finish_update(self):
        self.updating.finish()

    def hide_preview(self):
        if self._preview is not None:
            self._preview.hide()

    def reapply(self, recenter=True):
        """Перечитать масштаб и отступы после правки настроек."""
        screen = self._open_screen or self._target_screen()
        keep_x = self._slide_x
        self.apply_scale(screen, force=True)
        if self._open:
            _closed, open_y = self._positions(screen)
            if not recenter:
                self._slide_x = keep_x
            self._slide.set(float(open_y))
        self._sync_timer()

    def relayout(self):
        self.setFixedSize(s(PANEL_W), s(PANEL_H))
        self.rail.relayout()

        self.label.set_font_px(s(9), "Bold")
        self.label.setGeometry(s(LABEL_X), s(LABEL_Y), s(LABEL_W), s(LABEL_H))

        for page in self.pages.values():
            page.setGeometry(0, 0, s(PANEL_W), s(PANEL_H))
            page.relayout()

        self.updating.setGeometry(0, 0, s(PANEL_W), s(PANEL_H))
        self.rail.raise_all()
        self.label.raise_()
        self._laid_out = True

    # --- позиция на экране ----------------------------------------------- #

    def _positions(self, screen):
        """(закрытый, открытый) Y окна для текущего края экрана."""
        geo = screen.geometry()
        self._slide_x = geo.x() + (geo.width() - self.width()) // 2
        gap = s(self.settings.get("edge_gap", 0))
        if self._edge == "bottom":
            return geo.bottom() + 1, geo.bottom() + 1 - self.height() - gap
        return geo.y() - self.height(), geo.y() + gap

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
        # Экран выбираем ОДИН раз, на открытии: если после этого мышь уедет на
        # другой монитор, панель должна уехать обратно туда, где вылезла, а не
        # перепрыгнуть следом.
        screen = self.apply_scale(self._target_screen())
        self._open_screen = screen
        self._edge = panel_edge()
        closed_y, open_y = self._positions(screen)

        was_open = self._open
        self._open = True
        self._out_since = None
        self._in_since = None

        if not self.isVisible():
            self.move(self._slide_x, closed_y)
            self._slide.set(float(closed_y))
            self.show()
            self._apply_ex_style()
        self.raise_()

        page = self.current_page()
        if page:
            self.set_focusable(page.wants_keyboard)
            if not was_open:
                page.on_show()

        self._slide.target(float(open_y), SHOW_MS, QEasingCurve.OutCubic)
        self._sync_timer()
        if not was_open:
            self.opened.emit()

    def close_panel(self):
        # Пока ставится обновление, панель заперта: закрыть её хоткеем, из трея
        # или кликом мимо нельзя. Установка идёт своим ходом и заканчивается
        # подменой exe с перезапуском — прятать её на полпути нечего.
        if self.updating.blocking():
            return
        if not self._open and not self.isVisible():
            return
        self._open = False
        self._out_since = None
        self._in_since = None
        screen = self._open_screen or self._screen or self._target_screen()
        closed_y, _ = self._positions(screen)

        page = self.current_page()
        if page:
            page.on_hide()

        self._slide.target(float(closed_y), HIDE_MS, QEasingCurve.InCubic)
        self._sync_timer()
        self.closed.emit()

    def toggle(self):
        if self._open:
            self.close_panel()
        else:
            self.open_panel()

    def _on_slide(self, y):
        self.move(self._slide_x, int(round(y)))

    def _on_slide_done(self):
        if not self._open:
            self.hide()
            self._open_screen = None

    # --- слежение за курсором --------------------------------------------- #

    def _hover_enabled(self):
        return "hover" in self.settings.get("trigger", "hover+hotkey")

    def _sync_timer(self):
        need = self._open or self._hover_enabled()
        interval = 8 if self._open else 24
        if need:
            self._timer.setInterval(interval)
            if not self._timer.isActive():
                self._timer.start()
        elif self._timer.isActive():
            self._timer.stop()

    def start_watching(self):
        self._sync_timer()

    def _tick(self):
        pos = QCursor.pos()
        if self._open:
            self._tick_open(pos)
        elif self._hover_enabled():
            self._tick_trigger(pos)

    def _tick_trigger(self, pos):
        """
        Панель выезжает не от касания полосы, а от задержки в ней.

        Полоса лежит у самого края экрана, куда курсор попадает и по пути к
        углу, и промахом мимо кнопки: без выдержки панель выпрыгивала на каждое
        такое движение.
        """
        screen = self._target_screen()
        if not self._trigger_rect(screen).contains(pos):
            self._in_since = None
            return
        delay = self.settings.get("hover_delay_ms", 150)
        now = time.monotonic()
        if self._in_since is None:
            self._in_since = now
        if (now - self._in_since) * 1000 >= delay:
            self.open_panel()

    def _tick_open(self, pos):
        # Пока идёт установка, панель не прячем: она вот-вот подменит свой exe
        # и перезапустится, исчезать в этот момент нельзя. Вопрос про найденную
        # версию — не установка, его можно и переждать.
        if self.updating.blocking():
            return
        mode = self.settings.get("hide_mode", "leave")
        if mode == "manual":
            return
        m = s(LEAVE_MARGIN)
        area = QRect(self._slide_x, self.y(), self.width(), self.height())
        inside = area.adjusted(-m, -m, m, m).contains(pos)

        if mode == "click_outside":
            if not inside and left_down():
                self.close_panel()
            return

        # mode == "leave": уходим не сразу, чтобы панель не схлопывалась от
        # случайного выхода курсора на пиксель. Пока кнопка мыши нажата (тянут
        # ползунок перемотки), не закрываемся вовсе.
        # Пока в панели печатают, уводить её нельзя: мышь в это время может
        # лежать где угодно, а текст пропадёт вместе с окном.
        page = self.current_page()
        if inside or left_down() or (page and page.wants_keyboard
                                       and self.isActiveWindow()):
            self._out_since = None
            return
        now = time.monotonic()
        if self._out_since is None:
            self._out_since = now
        elif (now - self._out_since) * 1000 >= self.settings.get("hide_delay_ms", 220):
            self.close_panel()

    # --- приём брошенных файлов -------------------------------------------- #

    @staticmethod
    def _droppable(mime):
        return bool(mime and (mime.hasUrls() or mime.hasImage()))

    def dragEnterEvent(self, event):
        if not self._droppable(event.mimeData()):
            return
        # Показываем, куда именно оно ляжет, ещё до того как отпустили кнопку.
        self.set_tab("shelf")
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._droppable(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        page = self.pages.get("shelf")
        if page is not None and page.take_drop(event.mimeData()):
            event.acceptProposedAction()

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
        """Вкладкам с полями ввода фокус разрешаем, остальным — нет."""
        if not self.isVisible():
            return
        self._apply_ex_style(focusable=bool(on))
        if on:
            self.activateWindow()

    # --- отрисовка -------------------------------------------------------- #

    def _panel_path(self):
        """
        Скругления только у свободных углов.

        Панель прижата к краю экрана, и скруглять углы, которые в этот край
        упираются, незачем: получается щель с обоями между панелью и границей.
        Если задан отступ от края, панель ни во что не упирается — скругляем всё.
        """
        w, h = self.width(), self.height()
        r = sf(PANEL_RADIUS)
        path = QPainterPath()
        path.addRoundedRect(0, 0, w, h, r, r)
        if self.settings.get("edge_gap", 0):
            return path
        flat = QPainterPath()
        if self._edge == "top":
            flat.addRect(0, 0, w, r)
        else:
            flat.addRect(0, h - r, w, r)
        return path.united(flat)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillPath(self._panel_path(), theme.color("bg"))
