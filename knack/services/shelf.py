"""
Полка: скриншоты из буфера и файлы, брошенные на панель.

Картинки лежат в %APPDATA%\\Knack\\clipboard своими файлами, а не ссылками:
иначе полка ломалась бы вслед за исходником.

Медиафайлы (музыка, видео) не копируются: на полке лежит путь к оригиналу, и по
клику в буфер уходит именно он — так файл вставляется в чат через Ctrl+V.

Для видео и музыки превью снимает ffmpeg: у видео берётся кадр, у аудиофайла —
вшитая обложка. Сам ffmpeg в сборку не кладём, он качается по требованию в
%APPDATA%/Knack/tools (см. core/tools.py).

Брошенная картинка КОПИРУЕТСЯ побайтово, без разбора и пережатия: фотография с
телефона это два десятка мегапикселей, и её декодирование с последующей упаковкой
в PNG занимало на потоке интерфейса несколько секунд — панель всё это время
висела. Уменьшенное превью для карточки готовится отдельным потоком и появляется
само.
"""

import hashlib
import os
import shutil
import threading
import time
import uuid

from PySide6.QtCore import (QFileSystemWatcher, QMimeData, QObject, Qt, QTimer,
                            QUrl, Signal)
from PySide6.QtGui import QImage

from ..core import jsonfile, logbook, tools
from ..core.constants import SHELF_DIR, SHELF_INDEX

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}
AUDIO_EXT = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".opus"}
MEDIA_EXT = VIDEO_EXT | AUDIO_EXT

KIND_IMAGE = "image"
KIND_MEDIA = "media"

THUMB_MAX = 256          # длинная сторона превью карточки
RESCAN_MS = 200          # пауза перед перепроверкой: ФС шлёт события пачками


class ShelfStore(QObject):
    changed = Signal()
    ffmpeg_state = Signal(str)           # downloading | ready | error
    ffmpeg_progress = Signal(float)      # доля 0..1 во время загрузки
    _thumb_ready = Signal(str, str)      # (имя файла карточки, имя превью)

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else {}
        self._ffmpeg_lock = threading.Lock()
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
        # На старте подметаем с оглядкой: пустой список карточек означает либо
        # честно пустую полку, либо потерянный shelf.json — а файлы в папке в
        # этом случае ещё живые. Не различить, поэтому не трогаем.
        if self.items or not self._shelf_files():
            self._sweep_orphans()
        else:
            logbook.log("полка: индекс пуст, а файлы на месте — уборку пропускаю")
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
            if not self.preview_path(item):
                self._queue_thumb(item)

    def _thumb_key(self, item):
        """Имя, от которого пляшет файл превью: у медиа своего файла в папке нет."""
        name = item.get("file")
        if name:
            return os.path.splitext(name)[0]
        source = item.get("source") or ""
        # Именно md5, а не hash(): встроенный хеш строк случаен между запусками,
        # и превью пересоздавалось бы на каждом старте, оставляя мусор.
        return "media_%s" % hashlib.md5(source.encode("utf-8")).hexdigest()[:12]

    def _queue_thumb(self, item):
        source = self.path_of(item)
        name = self._thumb_key(item)
        if not name or not source:
            return
        if item.get("kind") == KIND_MEDIA:
            if not self.settings.get("shelf_video_thumbs", True):
                return
            worker = threading.Thread(target=self._media_thumb_worker,
                                      args=(name, source),
                                      name="knack-thumb", daemon=True)
            self._workers = [w for w in self._workers if w.is_alive()]
            self._workers.append(worker)
            worker.start()
            return
        worker = threading.Thread(target=self._thumb_worker, args=(name, source),
                                  name="knack-thumb", daemon=True)
        self._workers = [w for w in self._workers if w.is_alive()]
        self._workers.append(worker)
        worker.start()

    def _thumb_worker(self, name, source):
        """Превью картинки: QImage вне потока интерфейса безопасен."""
        try:
            if self._closing:
                return
            image = QImage(source)
            if image.isNull() or self._closing:
                return
            if max(image.width(), image.height()) > THUMB_MAX:
                image = image.scaled(THUMB_MAX, THUMB_MAX, Qt.KeepAspectRatio,
                                     Qt.SmoothTransformation)
            thumb = "%s_thumb.png" % name
            if image.save(os.path.join(SHELF_DIR, thumb), "PNG") and not self._closing:
                self._thumb_ready.emit(name, thumb)
        except Exception:
            logbook.exc("shelf thumb")

    def _media_thumb_worker(self, name, source):
        """Кадр из видео или вшитая обложка из аудио — силами ffmpeg."""
        try:
            if self._closing or not self._ensure_ffmpeg():
                return
            thumb = os.path.join(SHELF_DIR, "%s_thumb.png" % name)
            audio = os.path.splitext(source)[1].lower() not in VIDEO_EXT
            args = ["-y"]
            if not audio:
                # Первые кадры часто чёрные — отступаем на пару секунд. Если
                # ролик короче, ffmpeg вернёт ошибку, и мы возьмём самое начало.
                args += ["-ss", "2"]
            args += ["-i", source, "-frames:v", "1",
                     "-vf", "scale=%d:-1:force_original_aspect_ratio=decrease"
                     % THUMB_MAX, thumb]
            ok = tools.run(args)
            if not ok and not audio:
                ok = tools.run(["-y", "-i", source, "-frames:v", "1",
                                "-vf", "scale=%d:-1" % THUMB_MAX, thumb])
            if ok and os.path.isfile(thumb) and not self._closing:
                self._thumb_ready.emit(name, os.path.basename(thumb))
        except Exception:
            logbook.exc("shelf media thumb")

    def fetch_ffmpeg(self, force=False):
        """Ставит или переставляет ffmpeg по кнопке в настройках."""
        threading.Thread(target=self._fetch_ffmpeg_worker, args=(force,),
                         name="knack-ffmpeg", daemon=True).start()

    def _fetch_ffmpeg_worker(self, force):
        if force:
            try:
                os.remove(tools.FFMPEG_EXE)
            except OSError:
                pass
        self.ffmpeg_state.emit("downloading")
        try:
            if not tools.have_ffmpeg():
                tools.download_ffmpeg(on_progress=self.ffmpeg_progress.emit)
        except Exception:
            logbook.exc("ffmpeg fetch")
            self.ffmpeg_state.emit("error")
            return
        self.ffmpeg_state.emit("ready")
        # Свежий ffmpeg — можно достроить превью тем карточкам, что остались без.
        for item in list(self.items):
            if item.get("kind") == KIND_MEDIA and not self.preview_path(item):
                self._queue_thumb(item)

    def _ensure_ffmpeg(self):
        """Ставит ffmpeg, если его ещё нет. Качает не больше одного раза разом."""
        if tools.have_ffmpeg():
            return True
        if not self.settings.get("shelf_video_thumbs", True):
            return False
        with self._ffmpeg_lock:
            if tools.have_ffmpeg():
                return True
            try:
                logbook.log("полка: качаю ffmpeg для превью видео")
                self.ffmpeg_state.emit("downloading")
                tools.download_ffmpeg(on_progress=self.ffmpeg_progress.emit)
                self.ffmpeg_state.emit("ready")
                logbook.log("полка: ffmpeg готов")
            except Exception:
                logbook.exc("ffmpeg download")
                return False
        return tools.have_ffmpeg()

    def _on_thumb_ready(self, name, thumb):
        for item in self.items:
            if self._thumb_key(item) == name:
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

    def has_file(self, path):
        """
        Этот файл уже на полке?

        Карточку можно утащить наружу и, передумав, вернуть в окно — тогда к нам
        приезжает наш же файл, и без проверки появлялась вторая такая же
        карточка. У картинок сравниваем папку (наружу уходит наша копия), у
        медиа — путь к оригиналу.
        """
        path = os.path.normcase(os.path.abspath(path))
        if os.path.dirname(path) == os.path.normcase(os.path.abspath(SHELF_DIR)):
            return True
        for item in self.items:
            source = item.get("source") or ""
            if source and os.path.normcase(os.path.abspath(source)) == path:
                return True
        return False

    def add_file(self, path):
        """Файл, брошенный на панель."""
        path = os.path.abspath(path)
        if not os.path.isfile(path) or self.has_file(path):
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
        item = self._append({"source": path, "kind": KIND_MEDIA,
                             "added": time.time(),
                             "title": os.path.basename(path)})
        self._queue_thumb(item)
        return item

    # --- удаление --------------------------------------------------------- #

    def _erase_files(self, item):
        # У медиа удаляем только превью: сам файл принадлежит пользователю.
        if item.get("kind") == KIND_IMAGE:
            try:
                os.remove(self.path_of(item))
            except OSError:
                pass
        self._remove_thumb(item)

    def _shelf_files(self):
        try:
            return os.listdir(SHELF_DIR)
        except OSError:
            return []

    def _sweep_orphans(self):
        """
        Выметает из папки полки файлы, на которые не смотрит ни одна карточка.

        Удалить файл сразу получается не всегда: пока поток дорисовывает превью,
        Windows держит исходник открытым и os.remove тихо отказывает. А превью,
        дописанное уже после удаления карточки, оседает в папке навсегда — по
        имени его больше никто не ищет. Оба следа убираются здесь.
        """
        if not os.path.isdir(SHELF_DIR):
            return
        keep = set()
        for item in self.items:
            for name in (item.get("file"), item.get("thumb")):
                if name:
                    keep.add(name)
            # Превью, которое поток ещё дописывает, в карточке пока не записано,
            # но имя у него предсказуемое — иначе мы бы его сами и стёрли.
            keep.add("%s_thumb.png" % self._thumb_key(item))
        for name in self._shelf_files():
            if name in keep:
                continue
            try:
                os.remove(os.path.join(SHELF_DIR, name))
            except OSError:
                pass

    def remove(self, index):
        if not 0 <= index < len(self.items):
            return
        self._erase_files(self.items.pop(index))
        self._save()
        self._sweep_orphans()
        self._sync_watch()
        self.changed.emit()

    def clear(self):
        for item in list(self.items):
            self._erase_files(item)
        self.items = []
        self._save()
        self._sweep_orphans()
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
