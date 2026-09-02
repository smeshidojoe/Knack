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
        self._silent = False
        self._installing = False

    def supported(self):
        """В режиме разработки подменять нечего — обновляемся только собранными."""
        return updater.is_frozen()

    def latest_version(self):
        return self._latest.get("version", "")

    # --- проверка ------------------------------------------------------------ #

    def silent(self):
        """Последняя проверка была фоновой: о «всё свежее» сообщать не надо."""
        return self._silent

    def check(self, then_install=False, silent=False):
        if self._busy:
            return
        self._busy = True
        self._silent = silent
        if not silent:
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
        # Досюда доходим, только если установка не началась: путь загрузки
        # выходит раньше. Значит, замок снимаем в любом случае.
        self._installing = False
        self._busy = False

    # --- установка ------------------------------------------------------------ #

    def installing(self):
        """Установка уже идёт: второй раз запускать нечего."""
        return self._installing

    def install(self):
        """Качает найденное обновление и перезапускается в него."""
        # Установку могли позвать и с плашки, и кнопкой в настройках, и из трея.
        # Второй запуск скачал бы тот же архив поверх качающегося.
        if self._installing:
            return
        if self._busy or self._latest.get("status") != "available":
            self._installing = True
            self.check(then_install=True)
            return
        self._installing = True
        self._busy = True
        threading.Thread(target=self._download_worker, args=(self._latest,),
                         name="knack-update", daemon=True).start()

    def cancel_install(self):
        """Установка не состоялась — снимаем замок, чтобы можно было повторить."""
        self._installing = False

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
            self._installing = False
            return
        self._busy = False
        self.state.emit("ready", version)

    # --- применение ----------------------------------------------------------- #

    @staticmethod
    def start_helper():
        """
        Запускает помощника, который подменит exe. True — пошло.

        Разделено с выходом нарочно: вызывающий сначала спрашивает, удалось ли
        запустить помощника, и только потом разбирает программу. Иначе при
        неудаче мы оставались бы с остановленными службами и запертой панелью.
        """
        return bool(updater.restart_to_update())

    @staticmethod
    def exit_now():
        """
        Обрывает процесс, освобождая свой exe.

        Обычный выход тут не годится: пока процесс жив, его файл заблокирован, и
        помощник будет ждать впустую.
        """
        os._exit(0)
