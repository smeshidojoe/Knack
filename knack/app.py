"""Точка сборки: настройки, службы, панель, трей, хоткей."""

import ctypes
import signal
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from .core import autostart, config, fonts, icons, logbook
from .core.constants import APP_NAME, VERSION
from .core.hotkey import HotkeyManager
from .services.media import MediaService
from .tray import Tray
from .ui import theme
from .ui.overlay import Overlay

ERROR_ALREADY_EXISTS = 183


def _single_instance():
    """False — если Knack уже запущен."""
    try:
        handle = ctypes.windll.kernel32.CreateMutexW(None, False, "Knack.Instance")
        if not handle:
            return True
        return ctypes.windll.kernel32.GetLastError() != ERROR_ALREADY_EXISTS
    except Exception:
        return True


class KnackApp:
    def __init__(self, argv):
        self._quitting = False
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

        self.qt = QApplication(argv)
        self.qt.setApplicationName(APP_NAME)
        self.qt.setApplicationVersion(VERSION)
        self.qt.setQuitOnLastWindowClosed(False)

        self.settings = config.load()
        fonts.load()
        theme.apply(self.settings.get("theme"))

        self.media = MediaService()
        self.media.start()

        self.overlay = Overlay(self.settings, self.media)

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
        logbook.log("%s %s запущен" % (APP_NAME, VERSION))

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

    def quit(self):
        if self._quitting:
            return
        self._quitting = True
        config.save(self.settings)
        self.hotkeys.unregister_all()
        self.media.stop()
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
    if not _single_instance():
        logbook.log("Knack уже запущен")
        return 0
    try:
        return KnackApp(argv).run()
    except KeyboardInterrupt:
        logbook.log("остановлен по Ctrl+C")
        return 0
