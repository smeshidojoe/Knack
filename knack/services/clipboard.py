"""
Слежение за буфером обмена.

Опроса по таймеру нет: Windows сама сообщает о копировании
(WM_CLIPBOARDUPDATE), и Qt отдаёт это сигналом QClipboard.dataChanged. Опрос
пропускал бы быстрые подряд идущие копирования и жёг батарею впустую.

Текст уходит в историю, картинки — на полку.
"""

import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from ..core import jsonfile, logbook
from ..core.constants import CLIPBOARD_PATH

# Картинка иногда доезжает в буфер позже своих метаданных (так ведёт себя
# «Универсальный буфер» и часть программ захвата). Ждём её несколькими короткими
# попытками, иначе скриншот молча теряется.
IMAGE_RETRY_MS = 180
IMAGE_RETRIES = 5

MAX_TEXT = 20000     # длиннее в историю не кладём: это уже не «скопированное»


class ClipboardService(QObject):
    history_changed = Signal()

    def __init__(self, settings, shelf, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.shelf = shelf
        self.history = [x for x in jsonfile.load(CLIPBOARD_PATH, [])
                        if isinstance(x, dict) and x.get("text")]
        self._own_copy = ""     # что положили в буфер мы сами
        self._retries = 0
        self._retry = QTimer(self)
        self._retry.setInterval(IMAGE_RETRY_MS)
        self._retry.timeout.connect(self._try_image)

    def start(self):
        QGuiApplication.clipboard().dataChanged.connect(self._on_change)

    # --- запись в буфер --------------------------------------------------- #

    def copy_text(self, text):
        """Кладёт текст в буфер, не поднимая его же обратно в историю."""
        if not text:
            return
        self._own_copy = text
        QGuiApplication.clipboard().setText(text)

    def copy_mime(self, mime):
        self._own_copy = mime.text() or "\0mime"
        QGuiApplication.clipboard().setMimeData(mime)

    # --- история текста ---------------------------------------------------- #

    def limit(self):
        return int(self.settings.get("clipboard_limit", 100))

    def add_text(self, text):
        text = (text or "").strip()
        if not text or len(text) > MAX_TEXT:
            return
        # Повтор того же текста поднимаем наверх, а не плодим дубликаты.
        self.history = [x for x in self.history if x.get("text") != text]
        self.history.insert(0, {"text": text, "added": time.time()})
        del self.history[self.limit():]
        jsonfile.save(CLIPBOARD_PATH, self.history)
        self.history_changed.emit()

    def remove(self, index):
        if 0 <= index < len(self.history):
            self.history.pop(index)
            jsonfile.save(CLIPBOARD_PATH, self.history)
            self.history_changed.emit()

    def clear(self):
        self.history = []
        jsonfile.save(CLIPBOARD_PATH, self.history)
        self.history_changed.emit()

    # --- события буфера ---------------------------------------------------- #

    def _on_change(self):
        try:
            mime = QGuiApplication.clipboard().mimeData()
        except Exception:
            logbook.exc("clipboard read")
            return
        if mime is None:
            return

        if mime.hasImage():
            self._retries = IMAGE_RETRIES
            self._try_image()
            return

        if mime.hasText():
            text = mime.text()
            if text == self._own_copy:
                self._own_copy = ""
                return
            self.add_text(text)

    def _try_image(self):
        clipboard = QGuiApplication.clipboard()
        image = clipboard.image()
        if image is not None and not image.isNull():
            self._retry.stop()
            if self._own_copy:
                self._own_copy = ""
                return
            self.shelf.add_image(image)
            return
        self._retries -= 1
        if self._retries > 0:
            self._retry.start()
        else:
            self._retry.stop()
