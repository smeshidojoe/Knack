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
        self.tray.update_requested.connect(self._check_update)
        self.tray.show()

        self.services.updates.state.connect(self._on_update_state)
        self.services.shelf.ffmpeg_state.connect(self._on_ffmpeg_state)
        self.services.shelf.ffmpeg_progress.connect(self._on_ffmpeg_progress)
        self.services.updates.progress.connect(self._on_update_progress)

        autostart.set_enabled(self.settings.get("autostart", True))

        missing = icons.missing()
        if missing:
            logbook.log("иконки не найдены:", ", ".join(missing))

        self._install_signals()
        self.overlay.start_watching()
        # После сборки окон: прогрев и построение интерфейса тянут один и тот же
        # шрифтовой замок, и запущенный раньше поток задержал бы старт.
        fonts.warm_up()
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
        """Перерегистрирует все сочетания разом: их два, и оба зависят от
        настроек."""
        self.hotkeys.unregister_all()
        if "hotkey" in self.settings.get("trigger", ""):
            combo = self.settings.get("hotkey")
            if not self.hotkeys.register("toggle", combo):
                logbook.log("хоткей", combo, "занят другой программой")
        if self.settings.get("layout_switch_enabled", True):
            combo = self.settings.get("layout_hotkey")
            if not self.hotkeys.register("layout", combo):
                logbook.log("хоткей раскладки", combo, "занят другой программой")
        if self.settings.get("pin_enabled", True):
            combo = self.settings.get("pin_hotkey")
            if not self.hotkeys.register("pin", combo):
                logbook.log("хоткей закрепления", combo, "занят другой программой")

    def _on_hotkey(self, name):
        if name == "toggle":
            self.overlay.toggle()
        elif name == "layout":
            self.services.layout.trigger()
        elif name == "pin":
            state = self.services.pin.toggle()
            if state is not None:
                self.tray.notify(i18n.t("pin.on" if state else "pin.off"))

    def _on_capture(self, active):
        """Пока в настройках ловят сочетание, глобальный хоткей снимаем —
        иначе нажатие текущей комбинации закрыло бы панель вместо записи."""
        if active:
            self.hotkeys.unregister_all()
        else:
            self._register_hotkey()

    def _on_setting(self, key):
        """Настройки применяются сразу; на диск пишем тем же ходом."""
        if key == "ui_scale_preview":
            # Ползунок ещё в руке: показываем контур будущего окна и молчим —
            # ни перестройки, ни записи на диск.
            self.overlay.preview_scale(self.settings.get("ui_scale", 1.0))
            return
        if key == "ui_scale":
            self.overlay.hide_preview()
        elif key == "check_update":
            self._check_update()
            return
        elif key == "fetch_ffmpeg":
            from .core import tools
            self.services.shelf.fetch_ffmpeg(force=tools.have_ffmpeg())
            return
        elif key == "install_update":
            version = (self.services.updates.latest_version()
                       or getattr(self, "_update_version", ""))
            self.overlay.start_update(i18n.t("update.card") % version)
            self.services.updates.install()
            return
        if key == "language":
            i18n.set_language(self.settings.get("language"))
            self.overlay.retranslate()
        elif key in ("ui_scale", "edge_gap"):
            self.overlay.reapply()
        elif key == "animation_fps":
            anim.set_fps(self.settings.get("animation_fps", 0))
        elif key in ("hotkey", "trigger", "layout_hotkey",
                     "layout_switch_enabled", "pin_hotkey", "pin_enabled"):
            self._register_hotkey()
            self.overlay.start_watching()
        elif key == "monitor":
            self.overlay.reapply()
        config.save(self.settings)

    def _check_update(self):
        """Пункт меню в трее: проверить и, если есть, сразу поставить."""
        if not self.services.updates.supported():
            self.tray.notify(i18n.t("update.dev"))
            return
        self.tray.notify(i18n.t("update.checking"))
        self.services.updates.check(then_install=True)

    def _settings_page(self):
        return self.overlay.pages.get("settings")

    def _on_ffmpeg_state(self, key):
        page = self._settings_page()
        text = {"downloading": i18n.t("settings.working"),
                "ready": i18n.t("settings.done"),
                "error": i18n.t("settings.failed")}.get(key, "")
        if page is not None:
            page.set_ffmpeg_status(text, busy=(key == "downloading"))
        if key != "downloading":
            self.tray.notify(text)

    def _on_ffmpeg_progress(self, fraction):
        page = self._settings_page()
        if page is not None:
            page.set_ffmpeg_status(i18n.t("settings.percent")
                                   % round(fraction * 100), busy=True)

    def _on_update_progress(self, fraction):
        self.overlay.update_progress(fraction)

    def _on_update_state(self, key, version):
        page = self._settings_page()
        if page is not None:
            page.set_update_status({
                "checking": i18n.t("update.checking"),
                "downloading": i18n.t("settings.working"),
                "current": i18n.t("settings.done"),
                "error": i18n.t("settings.failed"),
            }.get(key, ""))
        if key == "available":
            self._update_version = version
            if page is not None:
                page.set_update_status("", ready=True)
            self.tray.notify(i18n.t("update.available") % version)
        elif key == "current":
            self.tray.notify(i18n.t("update.current"))
        elif key == "error":
            self.tray.notify(i18n.t("update.error"))
        elif key == "ready":
            self.overlay.update_progress(1.0, i18n.t("update.card.restart"))
            self.tray.notify(i18n.t("update.ready"))
            # Настройки сохраняем до подмены: дальше процесс обрывается.
            config.save(self.settings)
            self.hotkeys.unregister_all()
            self.services.stop()
            self.services.updates.apply_and_exit()

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
