"""
Слежение за буфером обмена.

Опроса по таймеру нет: Windows сама сообщает о копировании
(WM_CLIPBOARDUPDATE), и Qt отдаёт это сигналом QClipboard.dataChanged. Опрос
пропускал бы быстрые подряд идущие копирования и жёг батарею впустую.

Текст уходит в историю, картинки — на полку.

На одну копию система нередко присылает НЕСКОЛЬКО событий: программа-источник
выкладывает форматы по очереди, и каждый выпуск будит слушателей заново. Из-за
этого один скриншот ложился на полку двумя одинаковыми карточками. Поэтому
события сначала копятся в короткой паузе, а картинка вдобавок сверяется по
содержимому с предыдущей.
"""

import hashlib
import time

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QGuiApplication

from ..core import jsonfile, logbook
from ..core.constants import CLIPBOARD_PATH

# Пауза, за которую схлопываются повторные события одной копии.
SETTLE_MS = 150

# Картинка иногда доезжает в буфер позже своих метаданных (так ведёт себя
# «Универсальный буфер» и часть программ захвата). Ждём её несколькими короткими
# попытками, иначе скриншот молча теряется.
IMAGE_RETRY_MS = 180
IMAGE_RETRIES = 5

# Сколько секунд считать одинаковую картинку повтором того же события.
SAME_IMAGE_SEC = 3.0
# Сколько секунд после нашей же записи в буфер не реагировать на события.
OWN_COPY_SEC = 1.5

MAX_TEXT = 20000     # длиннее в историю не кладём: это уже не «скопированное»


def _is_file_list(mime):
    """
    В буфере лежат файлы, а не текст.

    Ctrl+X или Ctrl+C по файлу в Проводнике кладёт список файлов, и Qt отдаёт
    его ещё и текстом — строкой `file:///C:/...`. В историю СКОПИРОВАННОГО
    ТЕКСТА такому не место.

    Ссылку из браузера это не задевает: у неё адрес http(s), а не локальный
    файл, и она по-прежнему попадает в историю.
    """
    urls = mime.urls()
    if not urls or not all(url.isLocalFile() for url in urls):
        return False
    text = (mime.text() or "").strip()
    if not text:
        return True
    known = set()
    for url in urls:
        known.add(url.toString())
        known.add(url.toLocalFile())
    lines = {line.strip() for line in text.splitlines() if line.strip()}
    return lines.issubset(known)


def _image_hash(image):
    """Отпечаток содержимого картинки; буфер отдаём хешу без копии."""
    try:
        return hashlib.md5(image.constBits()).hexdigest()
    except Exception:
        return ""


class ClipboardService(QObject):
    history_changed = Signal()

    def __init__(self, settings, shelf, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.shelf = shelf
        self.history = [x for x in jsonfile.load(CLIPBOARD_PATH, [])
                        if isinstance(x, dict) and x.get("text")]

        self._own_at = 0.0          # когда мы сами писали в буфер
        self._own_texts = set()     # и что именно там оказалось
        self._last_hash = ""        # отпечаток последней принятой картинки
        self._last_hash_at = 0.0

        self._settle = QTimer(self)
        self._settle.setSingleShot(True)
        self._settle.setInterval(SETTLE_MS)
        self._settle.timeout.connect(self._process)

        self._retries = 0
        self._retry = QTimer(self)
        self._retry.setInterval(IMAGE_RETRY_MS)
        self._retry.timeout.connect(self._try_image)

    def start(self):
        QGuiApplication.clipboard().dataChanged.connect(self._on_change)

    # --- запись в буфер --------------------------------------------------- #

    def _mark_own(self, *texts):
        """
        Запоминаем, что и когда положили в буфер сами.

        Одного окна по времени мало: событие о нашей же записи иногда приходит
        позже, и путь к файлу всплывал в истории как «скопированный текст».
        Поэтому сверяемся ещё и по содержимому.
        """
        self._own_at = time.monotonic()
        self._own_texts = {x for x in texts if x}

    def copy_text(self, text):
        """Кладёт текст в буфер, не поднимая его же обратно в историю."""
        if not text:
            return
        self._mark_own(text)
        QGuiApplication.clipboard().setText(text)

    def copy_mime(self, mime):
        # Ссылки на файлы Windows отдаёт текстом как file:///... — такую строку
        # в историю класть незачем, поэтому помечаем оба написания.
        variants = [mime.text() or ""]
        for url in mime.urls():
            variants.append(url.toString())
            if url.isLocalFile():
                variants.append(url.toLocalFile())
        self._mark_own(*variants)
        QGuiApplication.clipboard().setMimeData(mime)

    def suppress(self):
        """Не реагировать на ближайшие изменения буфера.

        Нужна смене раскладки: она сама жмёт Ctrl+C в чужом окне, и ни
        выхваченный текст, ни его замена в историю попадать не должны.
        """
        self._own_at = time.monotonic()

    def _is_own(self):
        return (time.monotonic() - self._own_at) < OWN_COPY_SEC

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
        # Не читаем буфер сразу: источник может ещё выкладывать форматы, а
        # повторные события одной копии должны схлопнуться в одно.
        self._settle.start()

    def _process(self):
        if self._is_own():
            return
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

        if _is_file_list(mime):
            return

        if mime.hasText():
            text = mime.text()
            if text in self._own_texts or text.strip() in self._own_texts:
                return
            self.add_text(text)

    def _try_image(self):
        if self._is_own():
            self._retry.stop()
            return
        image = QGuiApplication.clipboard().image()
        if image is None or image.isNull():
            self._retries -= 1
            if self._retries > 0:
                self._retry.start()
            else:
                self._retry.stop()
            return

        self._retry.stop()
        digest = _image_hash(image)
        now = time.monotonic()
        if (digest and digest == self._last_hash
                and now - self._last_hash_at < SAME_IMAGE_SEC):
            # Та же картинка сразу следом — это второе событие одной копии.
            self._last_hash_at = now
            return
        self._last_hash, self._last_hash_at = digest, now
        self.shelf.add_image(image)
