"""
Вкладка «Полка»: скриншоты из буфера и брошенные на панель файлы.

Сетка карточек 72x69 в шесть колонок, прокрутка колесом. Картинка показывается
как есть, у медиафайла карточка со значком: копируется не файл, а путь к нему —
так его можно вставить в чат обычным Ctrl+V.

Клик по карточке кладёт содержимое в буфер, крестик в углу убирает карточку.
Карточку можно утащить мышью наружу — в папку, в чат, в любое окно, принимающее
файлы: наружу уходит тот же набор данных, что и в буфер.
"""

import os

from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import (QDrag, QFontMetrics, QPainter, QPainterPath, QPen,
                           QPixmap)
from PySide6.QtWidgets import QApplication, QWidget

from ...core import fonts, i18n, icons
from ...core.constants import BODY_R
from ...core.scale import s, sf
from ...services.shelf import KIND_IMAGE, KIND_MEDIA
from .. import theme
from ..widgets.flash import Flash
from ..widgets.text import Text
from .base import Page

GRID_X, GRID_Y = 56, 27
CARD_W, CARD_H, CARD_R = 72, 69, 9
STEP_X, STEP_Y = 79, 77
COLUMNS = 6
GRID_BOTTOM = 180

THUMB_X, THUMB_Y, THUMB_W, THUMB_H, THUMB_R = 5, 6, 62, 34, 5
CAP_X, CAP_Y, CAP_W, CAP_H, CAP_PX = 7, 45, 58.6, 20, 7
CLOSE_BOX, CLOSE_PAD = 12, 3
DRAG_PREVIEW = 56          # размер картинки под курсором при переносе


class _Grid(QWidget):
    def __init__(self, page, store):
        super().__init__(page)
        self.page = page
        self.store = store
        self.setMouseTracking(True)
        self._offset = 0
        self._hover = -1
        self._hover_close = False
        self._thumbs = {}
        self._press_at = None       # где нажали, чтобы отличить клик от переноса
        self._press_index = -1
        self._dragging = False
        self._after_drag = False    # перенос закончился, клик засчитывать нельзя
        self._flash = Flash(self.update)
        self._font = fonts.font(s(CAP_PX), "Medium")

    # --- геометрия -------------------------------------------------------- #

    def restyle(self):
        self._font = fonts.font(s(CAP_PX), "Medium")
        self._thumbs.clear()

    def rows(self):
        n = len(self.store.items)
        return (n + COLUMNS - 1) // COLUMNS if n else 0

    def content_height(self):
        rows = self.rows()
        return rows * s(STEP_Y) - (s(STEP_Y) - s(CARD_H)) if rows else 0

    def max_offset(self):
        return max(0, self.content_height() - self.height())

    def card_rect(self, index):
        row, column = divmod(index, COLUMNS)
        return QRect(column * s(STEP_X), row * s(STEP_Y) - self._offset,
                     s(CARD_W), s(CARD_H))

    def close_rect(self, card):
        box = s(CLOSE_BOX)
        return QRect(card.right() - box - s(CLOSE_PAD), card.top() + s(CLOSE_PAD),
                     box, box)

    def _index_at(self, point):
        for index in range(len(self.store.items)):
            if self.card_rect(index).contains(point):
                return index
        return -1

    # --- события ---------------------------------------------------------- #

    def wheelEvent(self, event):
        if self.max_offset() <= 0:
            return
        self._offset -= event.angleDelta().y() * s(STEP_Y) // 240
        self._offset = max(0, min(self._offset, self.max_offset()))
        self.update()

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        point = event.position().toPoint()
        self._press_at = point
        self._press_index = self._index_at(point)
        self._after_drag = False

    def mouseMoveEvent(self, event):
        point = event.position().toPoint()
        if (self._press_at is not None and self._press_index >= 0
                and not self._dragging
                and (point - self._press_at).manhattanLength()
                >= QApplication.startDragDistance()):
            self._start_drag(self._press_index)
            return
        index = self._index_at(point)
        close = bool(index >= 0
                     and self.close_rect(self.card_rect(index)).contains(point))
        if index != self._hover or close != self._hover_close:
            self._hover, self._hover_close = index, close
            self.setCursor(Qt.PointingHandCursor if index >= 0 else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, event):
        self._hover, self._hover_close = -1, False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        # Qt обычно не доводит отпускание до виджета-источника после переноса,
        # но если довело — клик засчитывать нельзя, карточку уже утащили.
        was_drag = self._dragging or self._after_drag
        self._dragging = self._after_drag = False
        self._press_at, self._press_index = None, -1
        if was_drag:
            return
        point = event.position().toPoint()
        index = self._index_at(point)
        if index < 0:
            return
        if self.close_rect(self.card_rect(index)).contains(point):
            self.store.remove(index)
            self._thumbs.clear()
        else:
            self.page.copy_item(index)

    def _start_drag(self, index):
        """Перенос карточки наружу: в папку, в чат, в любое окно с файлами."""
        if not 0 <= index < len(self.store.items):
            return
        item = self.store.items[index]
        self._dragging = True
        self._hover, self._hover_close = -1, False
        self.update()

        drag = QDrag(self)
        drag.setMimeData(self.store.mime_for(item))
        preview = self._drag_pixmap(item)
        if not preview.isNull():
            drag.setPixmap(preview)
            drag.setHotSpot(QPoint(preview.width() // 2, preview.height() // 2))
        drag.exec(Qt.CopyAction)
        self._dragging = False
        self._after_drag = True
        self._press_at, self._press_index = None, -1

    def _drag_pixmap(self, item):
        """Картинка под курсором во время переноса."""
        side = s(DRAG_PREVIEW)
        source = self._thumb(item, side, side)
        if not source.isNull():
            return source
        return icons.pixmap("media", side, theme.color("text_secondary"))

    def refresh(self):
        self._offset = max(0, min(self._offset, self.max_offset()))
        self.update()

    def flash(self, index):
        self._flash.start(index)

    # --- отрисовка -------------------------------------------------------- #

    def _thumb(self, item, width, height):
        path = self.store.preview_path(item)
        key = (path, width, height)
        pm = self._thumbs.get(key)
        if pm is None:
            source = QPixmap(path) if path else QPixmap()
            if source.isNull():
                pm = QPixmap()
            else:
                pm = source.scaled(width, height, Qt.KeepAspectRatioByExpanding,
                                   Qt.SmoothTransformation)
            self._thumbs[key] = pm
        return pm

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.setFont(self._font)
        metrics = QFontMetrics(self._font)

        for index, item in enumerate(self.store.items):
            card = self.card_rect(index)
            if card.bottom() < 0 or card.top() > self.height():
                continue

            radius = sf(CARD_R)
            p.setPen(Qt.NoPen)
            p.setBrush(theme.color("card"))
            p.drawRoundedRect(QRectF(card), radius, radius)

            thumb = QRect(card.left() + s(THUMB_X), card.top() + s(THUMB_Y),
                          s(THUMB_W), s(THUMB_H))
            pm = self._thumb(item, thumb.width(), thumb.height())
            if pm.isNull():
                # У медиа превью не бывает вовсе, у картинки его может ещё
                # готовить фоновый поток — тогда карточка просто пустая.
                if item.get("kind") == KIND_MEDIA:
                    glyph = icons.pixmap("media", s(18),
                                         theme.color("text_secondary"))
                    p.drawPixmap(thumb.center().x() - glyph.width() // 2,
                                 thumb.center().y() - glyph.height() // 2, glyph)
            else:
                path = QPainterPath()
                r = sf(THUMB_R)
                path.addRoundedRect(QRectF(thumb), r, r)
                p.save()
                p.setClipPath(path)
                p.drawPixmap(thumb.center().x() - pm.width() // 2,
                             thumb.center().y() - pm.height() // 2, pm)
                p.restore()

            title, when = self.store.caption(item)
            if item.get("kind") == KIND_IMAGE:
                title = i18n.t("shelf.shot")
            box = QRectF(card.left() + s(CAP_X), card.top() + s(CAP_Y),
                         s(CAP_W), s(CAP_H))
            p.setPen(theme.color("text_secondary"))
            line = metrics.elidedText(title or "", Qt.ElideMiddle, int(box.width()))
            p.drawText(QRectF(box.x(), box.y(), box.width(), box.height() / 2),
                       int(Qt.AlignLeft | Qt.AlignVCenter), line)
            p.drawText(QRectF(box.x(), box.y() + box.height() / 2,
                              box.width(), box.height() / 2),
                       int(Qt.AlignLeft | Qt.AlignVCenter), when)

            flash = self._flash.color(index, theme.current().flash)
            if flash is not None:
                p.setPen(Qt.NoPen)
                p.setBrush(flash)
                p.drawRoundedRect(QRectF(card), radius, radius)

            if index == self._hover:
                self._paint_close(p, self.close_rect(card))

    def _paint_close(self, painter, rect):
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.color("bg"))
        painter.drawEllipse(QRectF(rect))
        pen = QPen(theme.color("text_bright" if self._hover_close
                               else "text_secondary"))
        pen.setWidthF(max(1.0, sf(1.2)))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        pad = rect.width() * 0.3
        box = QRectF(rect).adjusted(pad, pad, -pad, -pad)
        painter.drawLine(box.topLeft(), box.bottomRight())
        painter.drawLine(box.topRight(), box.bottomLeft())


class ShelfPage(Page):
    key = "shelf"

    def __init__(self, store, clipboard, parent=None):
        super().__init__(parent)
        self.store = store
        self.clipboard = clipboard
        self.setAcceptDrops(True)

        self.grid = _Grid(self, store)
        self.empty = Text(self, text=i18n.t("shelf.empty"), role="text_muted",
                          align=Qt.AlignHCenter)

        store.changed.connect(self._refresh)
        self._refresh()

    def relayout(self):
        self.grid.restyle()
        self.grid.setGeometry(s(GRID_X), s(GRID_Y),
                              COLUMNS * s(STEP_X) - (s(STEP_X) - s(CARD_W)),
                              s(GRID_BOTTOM) - s(GRID_Y))
        self.empty.set_font_px(s(9), "Medium")
        self.empty.setGeometry(s(GRID_X), s(GRID_Y), s(BODY_R) - s(GRID_X),
                               s(GRID_BOTTOM) - s(GRID_Y))
        self.grid.refresh()

    def _refresh(self):
        has = bool(self.store.items)
        self.grid.setVisible(has)
        self.empty.setVisible(not has)
        self.grid.refresh()

    def copy_item(self, index):
        if 0 <= index < len(self.store.items):
            self.clipboard.copy_mime(self.store.mime_for(self.store.items[index]))
            self.grid.flash(index)

    def retranslate(self):
        self.empty.set_text(i18n.t("shelf.empty"))
        self.grid.update()

    # --- перетаскивание --------------------------------------------------- #

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() or event.mimeData().hasImage():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        self.take_drop(event.mimeData())
        event.acceptProposedAction()

    def take_drop(self, mime):
        """
        Принимает брошенное: файлы по ссылкам либо картинку из буфера.

        Если ссылки на файлы есть, картинку из того же события не берём: своя же
        карточка, вернувшаяся в окно, несёт и то и другое, и она добавилась бы
        второй раз уже как изображение.
        """
        if mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    self.store.add_file(url.toLocalFile())
            return True
        if mime.hasImage():
            image = mime.imageData()
            if image is not None:
                self.store.add_image(image)
            return True
        return False
