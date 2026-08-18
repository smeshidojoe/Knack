"""Точка сборки: настройки, службы, панель, трей, хоткей."""

import ctypes
import os
import signal
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .core import autostart, config, fonts, i18n, icons, logbook
from .core.constants import APP_ICO, APP_ID, APP_NAME, APP_VERSION
from .core.hotkey import HotkeyManager
from .services.hub import Services
from .tray import Tray
from .ui import anim, theme
from .ui.overlay import Overlay


class KnackApp:
    def __init__(self, argv):
        self._quitting = False
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

        self.qt = QApplication(argv)
        self._set_identity()
        self.qt.setQuitOnLastWindowClosed(False)

        self.settings = config.load()
        fonts.load()
        i18n.set_language(self.settings.get("language"))
        theme.apply(self.settings.get("theme"))

        self.services = Services(self.settings)
        self.services.start()

        self.overlay = Overlay(self.settings, self.services)
        self.overlay.setting_changed.connect(self._on_setting)
        self.overlay.hotkey_capture.connect(self._on_capture)

        self.hotkeys = HotkeyManager(self.qt)
        self.hotkeys.install(self.qt)
        self.hotkeys.triggered.connect(self._on_hotkey)
        self._register_hotkey()

        self.tray = Tray(self.settings, self.qt)
        self.tray.show_requested.connect(self.overlay.open_panel)
        self.tray.quit_requested.connect(self.quit)
        self.tray.show()

        autostart.set_enabled(self.settings.get("autostart", True))

        missing = icons.missing()
        if missing:
            logbook.log("иконки не найдены:", ", ".join(missing))

        self._install_signals()
        self.overlay.start_watching()
        logbook.log("%s %s запущен" % (APP_NAME, APP_VERSION))

    def _set_identity(self):
        """Имя и значок приложения для системы: уведомления и панель задач
        группируются под Knack, а не под «Python»."""
        self.qt.setApplicationName(APP_NAME)
        self.qt.setApplicationDisplayName(APP_NAME)
        self.qt.setOrganizationName(APP_NAME)
        self.qt.setApplicationVersion(APP_VERSION)
        if os.path.isfile(APP_ICO):
            self.qt.setWindowIcon(QIcon(APP_ICO))
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass

    def _install_signals(self):
        """Ctrl+C в консоли должен закрывать программу, а не игнорироваться.

        Пока Qt крутит цикл событий в C++, интерпретатор не возвращает
        управление Python и зарегистрированный обработчик сигнала не
        выполняется. Холостой таймер даёт эту передышку раз в 200 мс.
        """
        def stop(_signum, _frame):
            logbook.log("получен сигнал остановки")
            self.quit()

        for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            sig = getattr(signal, name, None)
            if sig is None:
                continue
            try:
                signal.signal(sig, stop)
            except (ValueError, OSError):
                pass

        self._signal_timer = QTimer(self.qt)
        self._signal_timer.timeout.connect(lambda: None)
        self._signal_timer.start(200)

    def _register_hotkey(self):
        if "hotkey" not in self.settings.get("trigger", ""):
            return
        combo = self.settings.get("hotkey")
        if not self.hotkeys.register("toggle", combo):
            logbook.log("хоткей", combo, "занят другой программой")

    def _on_hotkey(self, name):
        if name == "toggle":
            self.overlay.toggle()

    def _on_capture(self, active):
        """Пока в настройках ловят сочетание, глобальный хоткей снимаем —
        иначе нажатие текущей комбинации закрыло бы панель вместо записи."""
        if active:
            self.hotkeys.unregister("toggle")
        else:
            self._register_hotkey()

    def _on_setting(self, key):
        """Настройки применяются сразу; на диск пишем тем же ходом."""
        if key == "language":
            i18n.set_language(self.settings.get("language"))
            self.overlay.retranslate()
            self.tray.icon.setToolTip("%s %s" % (APP_NAME, APP_VERSION))
        elif key in ("ui_scale", "edge_gap"):
            self.overlay.reapply()
        elif key == "animation_fps":
            anim.set_fps(self.settings.get("animation_fps", 0))
        elif key in ("hotkey", "trigger"):
            self.hotkeys.unregister("toggle")
            self._register_hotkey()
            self.overlay.start_watching()
        elif key == "monitor":
            self.overlay.reapply()
        config.save(self.settings)

    def set_language(self, code):
        if i18n.set_language(code):
            self.settings["language"] = i18n.language()
            self.overlay.retranslate()

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        config.save(self.settings)
        self.hotkeys.unregister_all()
        self.services.stop()
        self.tray.hide()
        self.qt.quit()

    def run(self):
        try:
            code = self.qt.exec()
        except KeyboardInterrupt:
            # Сигнал мог прийти между вызовами обработчика — доводим выход сами.
            code = 0
        self.quit()
        return code


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    try:
        return KnackApp(argv).run()
    except KeyboardInterrupt:
        logbook.log("остановлен по Ctrl+C")
        return 0
