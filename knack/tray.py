"""Значок в трее: показать панель, автозапуск, выход."""

from PySide6.QtCore import Qt, QObject, QPoint, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QSystemTrayIcon

from .core import autostart, i18n, icons, systheme
from .core.constants import APP_NAME, APP_VERSION
from .ui.menu import Menu

# Размеры, которые Windows спрашивает у значка в трее при разных масштабах.
ICON_SIZES = (16, 20, 24, 32, 48)

# Доля клетки под сам глиф. Соседние значки в трее нарисованы с полями, и знак
# во всю клетку выглядел крупнее остальных.
GLYPH_RATIO = 0.76


class Tray(QObject):
    show_requested = Signal()
    quit_requested = Signal()
    update_requested = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._menu = None

        self.icon = QSystemTrayIcon(self._icon(), parent)
        self.icon.setToolTip("%s %s" % (APP_NAME, APP_VERSION))
        # Контекстное меню рисуем сами (см. ui/menu.py): нативное QMenu на
        # Windows игнорирует тему приложения целиком.
        self.icon.activated.connect(self._activated)

        # Тему системы можно переключить на ходу, и белый значок на светлой
        # панели задач пропадёт. Qt сообщает о смене — перекрашиваемся.
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(lambda _s: self.refresh_icon())

    def _icon(self):
        """Значок под текущую тему: белый на тёмной панели, тёмный на светлой."""
        ink = systheme.tray_ink()
        icon = QIcon()
        for size in ICON_SIZES:
            glyph = icons.pixmap("app", max(8, round(size * GLYPH_RATIO)), ink)
            ratio = glyph.devicePixelRatio()
            canvas = QPixmap(round(size * ratio), round(size * ratio))
            canvas.setDevicePixelRatio(ratio)
            canvas.fill(Qt.transparent)
            painter = QPainter(canvas)
            painter.drawPixmap(
                round((size - glyph.width() / ratio) / 2),
                round((size - glyph.height() / ratio) / 2), glyph)
            painter.end()
            icon.addPixmap(canvas)
        return icon

    def refresh_icon(self):
        self.icon.setIcon(self._icon())

    def notify(self, text):
        """Всплывающее уведомление системы — своего тоста у нас нет."""
        if text:
            self.icon.showMessage(APP_NAME, text, self.icon.icon(), 4000)

    def show(self):
        self.icon.show()

    def hide(self):
        self.icon.hide()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_requested.emit()
        elif reason == QSystemTrayIcon.Context:
            self._show_menu(QCursor.pos())

    def _show_menu(self, pos):
        items = [
            ("show", i18n.t("tray.show")),
            None,
            ("autostart", i18n.t("tray.autostart")),
            ("update", i18n.t("tray.update")),
            None,
            ("quit", i18n.t("tray.quit")),
        ]
        checks = {"autostart": bool(self.settings.get("autostart"))}
        self._menu = Menu(items, checks)
        self._menu.triggered.connect(self._on_menu)
        self._menu.popup_at(QPoint(pos.x(), pos.y()))

    def _on_menu(self, key):
        if key == "show":
            self.show_requested.emit()
        elif key == "autostart":
            value = not bool(self.settings.get("autostart"))
            self.settings["autostart"] = value
            autostart.set_enabled(value)
        elif key == "update":
            self.update_requested.emit()
        elif key == "quit":
            self.quit_requested.emit()
