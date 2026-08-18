"""
Полка: скриншоты из буфера и файлы, брошенные на панель.

Картинки сохраняются в %APPDATA%\\Knack\\clipboard и переживают перезапуск —
именно файлами, а не ссылками, иначе полка ломалась бы вслед за исходником.

Медиафайлы (музыка, видео) не копируются: на полке лежит путь к оригиналу, и по
клику в буфер уходит именно он — так файл вставляется в чат через Ctrl+V.
"""

import os
import time
import uuid

from PySide6.QtCore import QMimeData, QObject, QUrl, Signal
from PySide6.QtGui import QImage

from ..core import jsonfile
from ..core.constants import SHELF_DIR, SHELF_INDEX

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
MEDIA_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus",
             ".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}

KIND_IMAGE = "image"
KIND_MEDIA = "media"


class ShelfStore(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = jsonfile.load(SHELF_INDEX, [])
        self._drop_missing()

    # --- данные ---------------------------------------------------------- #

    def _drop_missing(self):
        """Файл могли удалить мимо программы — такие записи выкидываем."""
        alive = []
        for item in self.items:
            if not isinstance(item, dict):
                continue
            path = self.path_of(item)
            if path and os.path.isfile(path):
                alive.append(item)
        if len(alive) != len(self.items):
            self.items = alive
            self._save()

    def _save(self):
        jsonfile.save(SHELF_INDEX, self.items)

    def path_of(self, item):
        """Полный путь к содержимому карточки."""
        if item.get("kind") == KIND_MEDIA:
            return item.get("source") or ""
        name = item.get("file") or ""
        return os.path.join(SHELF_DIR, name) if name else ""

    def preview_path(self, item):
        """Что показывать на карточке: сам файл для картинок, превью для медиа."""
        if item.get("kind") == KIND_IMAGE:
            return self.path_of(item)
        preview = item.get("preview") or ""
        return os.path.join(SHELF_DIR, preview) if preview else ""

    # --- добавление ------------------------------------------------------- #

    def add_image(self, image):
        """image: QImage из буфера обмена."""
        if image is None or image.isNull():
            return None
        os.makedirs(SHELF_DIR, exist_ok=True)
        name = "%s.png" % uuid.uuid4().hex[:12]
        path = os.path.join(SHELF_DIR, name)
        if not image.save(path, "PNG"):
            return None
        item = {"file": name, "kind": KIND_IMAGE, "added": time.time()}
        self.items.insert(0, item)
        self._save()
        self.changed.emit()
        return item

    def add_file(self, path):
        """Файл, брошенный на панель."""
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            return None
        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXT:
            image = QImage(path)
            return self.add_image(image)
        if ext not in MEDIA_EXT:
            return None
        # Превью кадра из видео тут не берём: для этого нужен ffmpeg, а он ещё
        # не подключён. Карточка рисуется значком по типу файла.
        item = {"source": path, "kind": KIND_MEDIA, "added": time.time(),
                "title": os.path.basename(path)}
        self.items.insert(0, item)
        self._save()
        self.changed.emit()
        return item

    # --- удаление --------------------------------------------------------- #

    def remove(self, index):
        if not 0 <= index < len(self.items):
            return
        item = self.items.pop(index)
        if item.get("kind") == KIND_IMAGE:
            try:
                os.remove(self.path_of(item))
            except OSError:
                pass
        self._save()
        self.changed.emit()

    def clear(self):
        for item in list(self.items):
            if item.get("kind") == KIND_IMAGE:
                try:
                    os.remove(self.path_of(item))
                except OSError:
                    pass
        self.items = []
        self._save()
        self.changed.emit()

    # --- копирование ------------------------------------------------------ #

    def mime_for(self, item):
        """
        Что кладём в буфер по клику.

        Для картинки — саму картинку и заодно ссылку на файл: одни программы
        ждут пиксели, другие путь. Для медиа — только путь, как и задумано.
        """
        mime = QMimeData()
        path = self.path_of(item)
        if not path:
            return mime
        if item.get("kind") == KIND_IMAGE:
            image = QImage(path)
            if not image.isNull():
                mime.setImageData(image)
        else:
            mime.setText(path)
        mime.setUrls([QUrl.fromLocalFile(path)])
        return mime

    def caption(self, item):
        """Две строки подписи под карточкой: что это и когда добавлено."""
        stamp = time.localtime(item.get("added") or time.time())
        when = time.strftime("%d.%m.%Y %H:%M", stamp)
        if item.get("kind") == KIND_MEDIA:
            return item.get("title") or "", when
        return None, when      # первая строка подставляется на стороне вкладки
