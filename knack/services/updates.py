"""
Проверка и установка обновлений — обёртка над core/updater.

Сеть и распаковка идут в отдельном потоке: сходить к GitHub и скачать десяток
мегабайт на потоке интерфейса значит подвесить панель.
"""

import os
import threading

from PySide6.QtCore import QObject, Signal

from ..core import logbook, updater


class UpdateService(QObject):
    """
    `state(ключ, версия)` — что происходит: checking, current, available,
    downloading, ready, error. Вкладка настроек и трей показывают это словами.
    """

    state = Signal(str, str)
    progress = Signal(float)        # доля скачанного 0..1

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._busy = False
        self._latest = {}

    def supported(self):
        """В режиме разработки подменять нечего — обновляемся только собранными."""
        return updater.is_frozen()

    def latest_version(self):
        return self._latest.get("version", "")

    # --- проверка ------------------------------------------------------------ #

    def check(self, then_install=False):
        if self._busy:
            return
        self._busy = True
        self.state.emit("checking", "")
        threading.Thread(target=self._check_worker, args=(then_install,),
                         name="knack-update", daemon=True).start()

    def _check_worker(self, then_install):
        try:
            result = updater.check()
        except Exception as error:
            logbook.exc("update check")
            result = {"status": "error", "error": str(error)}

        self._latest = result
        status = result.get("status")
        if status == "available":
            self.state.emit("available", result.get("version", ""))
            if then_install and result.get("url"):
                self._download_worker(result)
                return
        elif status == "current":
            self.state.emit("current", result.get("version", ""))
        else:
            logbook.log("обновление: не удалось проверить —", result.get("error"))
            self.state.emit("error", "")
        self._busy = False

    # --- установка ------------------------------------------------------------ #

    def install(self):
        """Качает найденное обновление и перезапускается в него."""
        if self._busy or self._latest.get("status") != "available":
            self.check(then_install=True)
            return
        self._busy = True
        threading.Thread(target=self._download_worker, args=(self._latest,),
                         name="knack-update", daemon=True).start()

    def _download_worker(self, result):
        version = result.get("version", "")
        try:
            self.state.emit("downloading", version)
            self.progress.emit(0.0)
            updater.download(result.get("url"), on_progress=self.progress.emit)
        except Exception:
            logbook.exc("update download")
            self.state.emit("error", version)
            self._busy = False
            return
        self._busy = False
        self.state.emit("ready", version)

    # --- применение ----------------------------------------------------------- #

    @staticmethod
    def apply_and_exit():
        """
        Запускает подмену exe и немедленно выходит.

        Обычный выход тут не годится: пока процесс жив, его exe заблокирован, и
        помощник будет ждать впустую. Настройки сохраняет вызывающий.
        """
        if not updater.restart_to_update():
            return False
        os._exit(0)
