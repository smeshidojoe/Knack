"""
Вертикальный список строк с прокруткой.

Своя отрисовка вместо QListWidget с делегатом: строки в макете простые (фон,
иконка, два текста), а получить точные цвета, радиусы и подсветку от штатного
списка стоит больше кода, чем нарисовать их прямо.

Наследник задаёт count() и paint_row(). Прокрутка колесом, тонкая полоса справа
появляется только когда содержимое не влезло.
"""

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget

from ...core.scale import s, sf
from .. import theme
from .flash import Flash

SCROLL_W   = 2      # ширина полосы прокрутки, px макета
SCROLL_GAP = 4      # отступ полосы от содержимого
CLOSE_BOX  = 12     # крестик удаления в строке


class ListView(QWidget):
    activated = Signal(int)          # клик по строке
    close_requested = Signal(int)    # клик по крестику

    def __init__(self, parent=None, row_height=22, row_spacing=2,
                 has_close=False, close_inset=6):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self.row_height = row_height
        self.row_spacing = row_spacing
        self.has_close = has_close
        self.close_inset = close_inset

        self._offset = 0
        self._hover = -1
        self._hover_close = False
        self._flash = Flash(self.update)

    # --- к переопределению ------------------------------------------------ #

    def count(self):
        return 0

    def paint_row(self, painter, index, rect, hover):
        """rect — прямоугольник строки в координатах виджета."""

    # --- геометрия -------------------------------------------------------- #

    def step(self):
        return s(self.row_height) + s(self.row_spacing)

    def content_height(self):
        n = self.count()
        return n * self.step() - s(self.row_spacing) if n else 0

    def max_offset(self):
        return max(0, self.content_height() - self.height())

    def row_rect(self, index):
        width = self.width() - (s(SCROLL_W + SCROLL_GAP) if self.max_offset() else 0)
        return QRect(0, index * self.step() - self._offset, width, s(self.row_height))

    def close_rect(self, row):
        box = s(CLOSE_BOX)
        return QRect(row.right() - s(self.close_inset) - box,
                     row.center().y() - box // 2 + 1, box, box)

    def scroll_to(self, index):
        top = index * self.step()
        bottom = top + s(self.row_height)
        if top < self._offset:
            self._offset = top
        elif bottom > self._offset + self.height():
            self._offset = bottom - self.height()
        self._clamp()

    def _clamp(self):
        self._offset = max(0, min(self._offset, self.max_offset()))
        self.update()

    def refresh(self):
        self._clamp()

    # --- события ---------------------------------------------------------- #

    def wheelEvent(self, event):
        if self.max_offset() <= 0:
            return
        self._offset -= event.angleDelta().y() * self.step() // 120
        self._clamp()

    def _index_at(self, point):
        step = self.step()
        if step <= 0:
            return -1
        index = (point.y() + self._offset) // step
        if not 0 <= index < self.count():
            return -1
        if not self.row_rect(index).contains(point):
            return -1
        return index

    def mouseMoveEvent(self, event):
        point = event.position().toPoint()
        index = self._index_at(point)
        close = bool(self.has_close and index >= 0
                     and self.close_rect(self.row_rect(index)).contains(point))
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
        point = event.position().toPoint()
        index = self._index_at(point)
        if index < 0:
            return
        if self.has_close and self.close_rect(self.row_rect(index)).contains(point):
            self.close_requested.emit(index)
        else:
            self.activated.emit(index)

    def hover_index(self):
        return self._hover

    def flash(self, index):
        """Подсветить строку: содержимое ушло в буфер."""
        self._flash.start(index)

    def paint_flash(self, painter, index, shape, radius):
        color = self._flash.color(index, theme.current().flash)
        if color is None:
            return
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(shape, radius, radius)

    # --- отрисовка -------------------------------------------------------- #

    def paint_close(self, painter, rect, hover):
        """Крестик удаления в правой части строки."""
        painter.save()
        pen = QPen(theme.color("text_bright" if hover else "text_button"))
        pen.setWidthF(max(1.0, sf(1.2)))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        pad_x, pad_y = rect.width() * 0.28, rect.height() * 0.28
        box = QRectF(rect).adjusted(pad_x, pad_y, -pad_x, -pad_y)
        painter.drawLine(box.topLeft(), box.bottomRight())
        painter.drawLine(box.topRight(), box.bottomLeft())
        painter.restore()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        first = max(0, (self._offset // self.step()) if self.step() else 0)
        last = min(self.count(), first + self.height() // max(1, self.step()) + 2)
        for index in range(first, last):
            rect = self.row_rect(index)
            if rect.bottom() < 0 or rect.top() > self.height():
                continue
            self.paint_row(p, index, rect, index == self._hover)

        span = self.max_offset()
        if span <= 0:
            return
        track_w = sf(SCROLL_W)
        x = self.width() - track_w
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("scroll_track"))
        p.drawRoundedRect(QRectF(x, 0, track_w, self.height()),
                          track_w / 2, track_w / 2)
        visible = self.height() / max(1.0, float(self.content_height()))
        thumb_h = max(sf(12), self.height() * visible)
        top = (self.height() - thumb_h) * (self._offset / span)
        p.setBrush(theme.color("scroll_thumb"))
        p.drawRoundedRect(QRectF(x, top, track_w, thumb_h),
                          track_w / 2, track_w / 2)
