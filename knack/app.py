"""Точка сборки: настройки, службы, панель, трей, хоткей."""

import ctypes
import os
import signal
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .core import autostart, config, fonts, i18n, icons, logbook, updater
from .core.constants import APP_ICO, APP_ID, APP_NAME, APP_VERSION
from .core.hotkey import HotkeyManager
from .services.hub import Services
from .tray import Tray
from .ui import anim, theme
from .ui.overlay import Overlay
from .ui.pin_badge import PinBadge
from .ui.toast import Toast

UPDATE_REVEAL_MS = 420                  # пока панель выезжает и колонка едет
TOAST_MS = 4000                         # сколько висит короткое сообщение
UPDATE_FIRST_MS = 8000                  # первая тихая проверка после старта
UPDATE_WATCH_MS = 2 * 60 * 60 * 1000    # и дальше раз в два часа


class KnackApp:
    def __init__(self, argv):
        self._quitting = False
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

        self.qt = QApplication(argv)
        self._set_identity()
        self.qt.setQuitOnLastWindowClosed(False)

        had_config = os.path.isfile(config.CONFIG_PATH)
        self.settings = config.load()
        if not had_config:
            # Первый запуск: галочку автозапуска мог поставить (или снять)
            # установщик. Реестр тут — источник истины, иначе синхронизация ниже
            # затёрла бы выбор, сделанный в мастере.
            self.settings["autostart"] = autostart.is_enabled()
        fonts.load()
        i18n.set_language(self.settings.get("language"))
        theme.apply(self.settings.get("theme"))

        self.services = Services(self.settings)
        self.services.start()

        self.overlay = Overlay(self.settings, self.services)
        self.overlay.setting_changed.connect(self._on_setting)
        self.overlay.hotkey_capture.connect(self._on_capture)
        self.overlay.updating.accepted.connect(self._install_update)
        self.overlay.updating.dismissed.connect(self._dismiss_update)
        self.overlay.opened.connect(self._show_pending_update)

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

        # Настройка — источник истины: путь к exe переписываем на каждом старте,
        # иначе после переустановки в другую папку автозапуск указывал бы в
        # пустоту, а выключенный — оставался бы висеть от прошлой установки.
        autostart.set_enabled(self.settings.get("autostart", True))

        missing = icons.missing()
        if missing:
            logbook.log("иконки не найдены:", ", ".join(missing))

        self.toast = Toast()
        self.toast.clicked.connect(self._on_toast_click)
        self.toast.dismissed.connect(self._dismiss_update)

        self.pin_badge = PinBadge(self.services.pin)
        self.pin_badge.clicked.connect(self._on_badge_click)
        self._sync_pin_badge()

        self._pending_update = ""    # найденная фоном версия, о которой спросим
        self._start_update_watch()

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
            # Молча: состояние видно по значку в углу окна, а всплывающее
            # уведомление на каждое нажатие только мешает.
            self.services.pin.toggle()

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
            self._sync_pin_badge()
            self.overlay.start_watching()
        elif key == "pin_badge":
            self._sync_pin_badge()
        elif key == "monitor":
            self.overlay.reapply()
        config.save(self.settings)

    def _sync_pin_badge(self):
        """Значок ходит за активным окном, только когда закрепление включено."""
        on = (self.settings.get("pin_enabled", True)
              and self.settings.get("pin_badge", True))
        if on:
            self.pin_badge.start()
        else:
            self.pin_badge.stop()

    def _on_badge_click(self, hwnd):
        self.services.pin.toggle_window(hwnd)

    # --- обновления ------------------------------------------------------- #

    def _start_update_watch(self):
        """Тихая проверка: первая через 8 секунд после старта, дальше раз в два
        часа. Один запрос к GitHub в фоновом потоке — нагрузки никакой."""
        if not self.services.updates.supported():
            return
        self._update_timer = QTimer(self.qt)
        self._update_timer.setInterval(UPDATE_WATCH_MS)
        self._update_timer.timeout.connect(self._check_update_bg)
        self._update_timer.start()
        QTimer.singleShot(UPDATE_FIRST_MS, self._check_update_bg)

    def _check_update_bg(self):
        if self.settings.get("check_updates", True):
            self.services.updates.check(silent=True)

    def _show_pending_update(self):
        """Спрашиваем, когда панель на виду: карточка живёт внутри неё."""
        if not self._pending_update or self.overlay.updating.isVisible():
            return
        self.overlay.ask_update(i18n.t("update.found") % self._pending_update)

    def _on_toast_click(self):
        """
        Щёлкнули по плашке: панель выезжает, открываются настройки, колонка
        доезжает до строки обновления — и поверх неё встаёт карточка установки.
        """
        if not self._pending_update or self.services.updates.installing():
            return
        self.overlay.open_panel()
        self.overlay.set_tab("settings")
        page = self._settings_page()
        if page is not None:
            page.reveal_update_row()
        # Даём панели выехать и колонке доехать, и только потом накрываем всё
        # карточкой: иначе она появилась бы раньше самой панели.
        QTimer.singleShot(UPDATE_REVEAL_MS, self._install_update)

    def _show_update_card(self, version):
        """Открывает панель с карточкой установки, если её ещё нет."""
        if self.overlay.updating.blocking():
            return
        if not self.overlay.is_open():
            self.overlay.open_panel()
        self.overlay.start_update(i18n.t("update.card") % version)

    def _install_update(self):
        if self.services.updates.installing():
            return
        version = self._pending_update or self.services.updates.latest_version()
        self._pending_update = ""
        self.toast.close_message()
        self._show_update_card(version)
        self.services.updates.install()

    def _dismiss_update(self):
        """«Позже»: об этой версии больше не напоминаем."""
        self.toast.close_message()
        if self._pending_update:
            self.settings["update_dismissed_version"] = self._pending_update
            config.save(self.settings)
        self._pending_update = ""

    def _check_update(self):
        """Пункт меню в трее: проверить и, если есть, сразу поставить."""
        if not self.services.updates.supported():
            self.toast.show_message(i18n.t("update.dev"), "", TOAST_MS)
            return
        self.toast.show_message(i18n.t("update.checking"), "", TOAST_MS)
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
        if key == "downloading":
            # Загрузку могли начать из трея, минуя кнопку в настройках. Панель
            # тогда открываем сами: пока идёт установка, она заперта и показывает
            # прогресс — иначе обновление шло бы вслепую.
            self._show_update_card(version)

        silent = self.services.updates.silent()
        if key == "available":
            self._update_version = version
            if page is not None:
                page.set_update_status("", ready=True)
            if not silent:
                self.toast.show_message(i18n.t("update.available") % version,
                                        "", TOAST_MS)
                return
            if version == self.settings.get("update_dismissed_version"):
                return          # об этой версии уже спрашивали, ответили «позже»
            self._pending_update = version
            # Плашка своя, а не системная: системные уведомления глушит
            # «Фокусировка внимания», и сообщение о новой версии не доходит.
            self.toast.show_message(i18n.t("update.found") % version,
                                    i18n.t("update.toast.hint"))
            if self.overlay.is_open():
                self._show_pending_update()
        elif key == "current":
            if not silent:
                self.toast.show_message(i18n.t("update.current"), "", TOAST_MS)
        elif key == "error":
            if not silent:
                self.toast.show_message(i18n.t("update.error"), "", TOAST_MS)
        elif key == "ready":
            self.overlay.update_progress(1.0, i18n.t("update.card.restart"))
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
        self.toast.close_message()
        self.pin_badge.stop()
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
