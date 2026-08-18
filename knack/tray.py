"""Значок в трее: показать панель, автозапуск, выход."""

import os

from PySide6.QtCore import QObject, QPoint, Signal
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from .core import autostart, i18n, icons
from .core.constants import APP_ICO, APP_NAME, APP_VERSION
from .ui.menu import Menu


class Tray(QObject):
    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._menu = None

        self.icon = QSystemTrayIcon(self._icon(), parent)
        self.icon.setToolTip("%s %s" % (APP_NAME, APP_VERSION))
        # Контекстное меню рисуем сами (см. ui/menu.py): нативное QMenu на
        # Windows игнорирует тему приложения целиком.
        self.icon.activated.connect(self._activated)

    def _icon(self):
        """В сборке берём готовый .ico (у него есть все размеры), в разработке
        рисуем из SVG."""
        if os.path.isfile(APP_ICO):
            return QIcon(APP_ICO)
        return QIcon(icons.pixmap("app", 32, "#FFFFFF"))

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
        elif key == "quit":
            self.quit_requested.emit()
