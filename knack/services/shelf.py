"""
Полка: скриншоты из буфера и файлы, брошенные на панель.

Картинки лежат в %APPDATA%\\Knack\\clipboard своими файлами, а не ссылками:
иначе полка ломалась бы вслед за исходником.

Медиафайлы (музыка, видео) не копируются: на полке лежит путь к оригиналу, и по
клику в буфер уходит именно он — так файл вставляется в чат через Ctrl+V.

Брошенная картинка КОПИРУЕТСЯ побайтово, без разбора и пережатия: фотография с
телефона это два десятка мегапикселей, и её декодирование с последующей упаковкой
в PNG занимало на потоке интерфейса несколько секунд — панель всё это время
висела. Уменьшенное превью для карточки готовится отдельным потоком и появляется
само.
"""

import os
import shutil
import threading
import time
import uuid

from PySide6.QtCore import (QFileSystemWatcher, QMimeData, QObject, Qt, QTimer,
                            QUrl, Signal)
from PySide6.QtGui import QImage

from ..core import jsonfile, logbook
from ..core.constants import SHELF_DIR, SHELF_INDEX

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
MEDIA_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus",
             ".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}

KIND_IMAGE = "image"
KIND_MEDIA = "media"

THUMB_MAX = 256          # длинная сторона превью карточки
RESCAN_MS = 200          # пауза перед перепроверкой: ФС шлёт события пачками


class ShelfStore(QObject):
    changed = Signal()
    _thumb_ready = Signal(str, str)      # (имя файла карточки, имя превью)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = [x for x in jsonfile.load(SHELF_INDEX, []) if isinstance(x, dict)]
        self._thumb_ready.connect(self._on_thumb_ready)
        self._closing = False
        self._workers = []

        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self._schedule_rescan)
        self._watcher.fileChanged.connect(self._schedule_rescan)
        self._rescan = QTimer(self)
        self._rescan.setSingleShot(True)
        self._rescan.setInterval(RESCAN_MS)
        self._rescan.timeout.connect(self._recheck)

        self._drop_missing(quiet=True)
        self._sync_watch()
        self._queue_missing_thumbs()

    # --- данные ---------------------------------------------------------- #

    def _save(self):
        jsonfile.save(SHELF_INDEX, self.items)

    def path_of(self, item):
        """Полный путь к содержимому карточки."""
        if item.get("kind") == KIND_MEDIA:
            return item.get("source") or ""
        name = item.get("file") or ""
        return os.path.join(SHELF_DIR, name) if name else ""

    def preview_path(self, item):
        """
        Что показывать на карточке.

        Только готовое превью: рисовать полноразмерный исходник значило бы
        разбирать двадцатимегапиксельный файл на каждую перерисовку сетки.
        Пока превью не готово, карточка стоит пустой.
        """
        name = item.get("thumb") or ""
        if not name:
            return ""
        path = os.path.join(SHELF_DIR, name)
        return path if os.path.isfile(path) else ""

    def _alive(self, item):
        path = self.path_of(item)
        if not path:
            return False
        if os.path.isfile(path):
            return True
        if item.get("kind") == KIND_MEDIA:
            # Диск мог быть временно отключён — карточку тогда не трогаем,
            # выкидываем только когда папка на месте, а файла в ней нет.
            return not os.path.isdir(os.path.dirname(path) or ".")
        return False

    def _drop_missing(self, quiet=False):
        """Файл удалили мимо программы — карточка уходит следом."""
        alive = [item for item in self.items if self._alive(item)]
        if len(alive) == len(self.items):
            return False
        for item in self.items:
            if item not in alive:
                self._remove_thumb(item)
        self.items = alive
        self._save()
        if not quiet:
            self.changed.emit()
        return True

    # --- слежение за файлами ------------------------------------------------ #

    def _sync_watch(self):
        """Под наблюдением папка полки и каждый исходник медиа со своей папкой."""
        paths = []
        if os.path.isdir(SHELF_DIR):
            paths.append(SHELF_DIR)
        for item in self.items:
            if item.get("kind") != KIND_MEDIA:
                continue
            source = item.get("source") or ""
            if os.path.isfile(source):
                paths.append(source)
                folder = os.path.dirname(source)
                if os.path.isdir(folder):
                    paths.append(folder)

        current = set(self._watcher.directories()) | set(self._watcher.files())
        wanted = set(paths)
        if current - wanted:
            self._watcher.removePaths(list(current - wanted))
        if wanted - current:
            self._watcher.addPaths(list(wanted - current))

    def _schedule_rescan(self, _path=""):
        self._rescan.start()

    def _recheck(self):
        if not self._drop_missing():
            # Ничего не пропало — значит что-то появилось (например, наш же
            # поток дописал превью); сетке всё равно стоит перерисоваться.
            self.changed.emit()
        self._sync_watch()

    # --- превью -------------------------------------------------------------- #

    def _queue_missing_thumbs(self):
        for item in self.items:
            if item.get("kind") == KIND_IMAGE and not self.preview_path(item):
                self._queue_thumb(item)

    def _queue_thumb(self, item):
        name = item.get("file") or ""
        source = self.path_of(item)
        if not name or not source:
            return
        worker = threading.Thread(target=self._thumb_worker, args=(name, source),
                                  name="knack-thumb", daemon=True)
        self._workers = [w for w in self._workers if w.is_alive()]
        self._workers.append(worker)
        worker.start()

    def _thumb_worker(self, name, source):
        """Готовит превью в фоне: QImage вне потока интерфейса безопасен."""
        try:
            if self._closing:
                return
            image = QImage(source)
            if image.isNull() or self._closing:
                return
            if max(image.width(), image.height()) > THUMB_MAX:
                image = image.scaled(THUMB_MAX, THUMB_MAX, Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation)
            thumb = "%s_thumb.png" % os.path.splitext(name)[0]
            if image.save(os.path.join(SHELF_DIR, thumb), "PNG") and not self._closing:
                self._thumb_ready.emit(name, thumb)
        except Exception:
            logbook.exc("shelf thumb")

    def _on_thumb_ready(self, name, thumb):
        for item in self.items:
            if item.get("file") == name:
                item["thumb"] = thumb
                self._save()
                self.changed.emit()
                return

    def _remove_thumb(self, item):
        thumb = item.get("thumb") or ""
        if not thumb:
            return
        try:
            os.remove(os.path.join(SHELF_DIR, thumb))
        except OSError:
            pass

    def shutdown(self):
        """Программа закрывается: дорисовывать превью уже некуда."""
        self._closing = True
        self._rescan.stop()
        for worker in self._workers:
            worker.join(timeout=0.5)
        self._workers = []

    # --- добавление ------------------------------------------------------- #

    def _append(self, item):
        self.items.insert(0, item)
        self._save()
        self._sync_watch()
        self.changed.emit()
        return item

    def add_image(self, image):
        """image: QImage из буфера обмена."""
        if image is None or image.isNull():
            return None
        os.makedirs(SHELF_DIR, exist_ok=True)
        name = "%s.png" % uuid.uuid4().hex[:12]
        if not image.save(os.path.join(SHELF_DIR, name), "PNG"):
            return None
        item = self._append({"file": name, "kind": KIND_IMAGE,
                             "added": time.time()})
        self._queue_thumb(item)
        return item

    def add_file(self, path):
        """Файл, брошенный на панель."""
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            return None
        ext = os.path.splitext(path)[1].lower()

        if ext in IMAGE_EXT:
            os.makedirs(SHELF_DIR, exist_ok=True)
            name = "%s%s" % (uuid.uuid4().hex[:12], ext)
            try:
                shutil.copy2(path, os.path.join(SHELF_DIR, name))
            except OSError:
                logbook.exc("shelf copy")
                return None
            item = self._append({"file": name, "kind": KIND_IMAGE,
                                 "added": time.time(),
                                 "title": os.path.basename(path)})
            self._queue_thumb(item)
            return item

        if ext not in MEDIA_EXT:
            return None
        # Превью кадра из видео тут не берём: для этого нужен ffmpeg, а он ещё
        # не подключён. Карточка рисуется значком по типу файла.
        return self._append({"source": path, "kind": KIND_MEDIA,
                             "added": time.time(),
                             "title": os.path.basename(path)})

    # --- удаление --------------------------------------------------------- #

    def _erase_files(self, item):
        if item.get("kind") != KIND_IMAGE:
            return
        try:
            os.remove(self.path_of(item))
        except OSError:
            pass
        self._remove_thumb(item)

    def remove(self, index):
        if not 0 <= index < len(self.items):
            return
        self._erase_files(self.items.pop(index))
        self._save()
        self._sync_watch()
        self.changed.emit()

    def clear(self):
        for item in list(self.items):
            self._erase_files(item)
        self.items = []
        self._save()
        self._sync_watch()
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
