"""Значок в трее: показать панель, автозапуск, выход."""

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .core import autostart, icons
from .core.constants import APP_NAME, VERSION


class Tray(QObject):
    show_requested = Signal()
    quit_requested = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

        self.icon = QSystemTrayIcon(self._icon(), parent)
        self.icon.setToolTip("%s %s" % (APP_NAME, VERSION))

        menu = QMenu()
        act_show = QAction("Показать панель", menu)
        act_show.triggered.connect(self.show_requested.emit)
        menu.addAction(act_show)

        menu.addSeparator()

        self.act_autostart = QAction("Запускать с Windows", menu)
        self.act_autostart.setCheckable(True)
        self.act_autostart.setChecked(bool(settings.get("autostart")))
        self.act_autostart.toggled.connect(self._toggle_autostart)
        menu.addAction(self.act_autostart)

        menu.addSeparator()

        act_quit = QAction("Выход", menu)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self._menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._activated)

    def _icon(self):
        return QIcon(icons.pixmap("music", 32, "#FFFFFF"))

    def show(self):
        self.icon.show()

    def hide(self):
        self.icon.hide()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_requested.emit()

    def _toggle_autostart(self, on):
        self.settings["autostart"] = bool(on)
        autostart.set_enabled(on)
