"""Обложка трека: скруглённый квадрат, пока обложки нет — заливка-заглушка."""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QWidget

from ...core.scale import sf
from .. import theme


class Artwork(QWidget):
    def __init__(self, parent=None, radius=12):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._radius = radius
        self._pixmap = QPixmap()

    def set_image(self, data):
        """data: bytes с картинкой или None."""
        pm = QPixmap()
        if data:
            pm.loadFromData(data)
        self._pixmap = pm
        self.update()

    def has_image(self):
        return not self._pixmap.isNull()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        rect = QRectF(self.rect())
        r = sf(self._radius)
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)
        p.setClipPath(path)

        if self._pixmap.isNull():
            p.fillPath(path, theme.color("placeholder"))
            return

        # Обложки приходят квадратными не всегда — вписываем по короткой стороне.
        src = self._pixmap
        k = max(rect.width() / src.width(), rect.height() / src.height())
        w, h = src.width() * k, src.height() * k
        p.drawPixmap(QRectF((rect.width() - w) / 2, (rect.height() - h) / 2, w, h),
                     src, QRectF(src.rect()))
