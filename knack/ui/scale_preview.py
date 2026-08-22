"""
Призрак будущего размера панели.

Пока тянут ползунок размера, саму панель не трогаем: она перестраивалась бы под
курсором, ползунок уезжал бы из-под пальца, а шаг ощущался неровным. Вместо
этого поверх экрана показывается полупрозрачный контур — таким окно станет,
когда ползунок отпустят.

Окно прозрачно для мыши (`WindowTransparentForInput`): курсор его не замечает и
продолжает тянуть ползунок.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ..core.constants import PANEL_RADIUS
from . import theme

FILL_ALPHA = 0.30
EDGE_ALPHA = 0.75
EDGE_WIDTH = 2


class ScalePreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus
            | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self._radius = float(PANEL_RADIUS)

    def show_at(self, rect, radius):
        """radius — уже в пикселях экрана: масштаб тут свой, будущий."""
        self._radius = max(1.0, float(radius))
        self.setGeometry(rect)
        if not self.isVisible():
            self.show()
        self.raise_()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        border = float(EDGE_WIDTH)
        radius = self._radius
        body = QRectF(border / 2, border / 2,
                      self.width() - border, self.height() - border)
        path = QPainterPath()
        path.addRoundedRect(body, radius, radius)

        fill = QColor(theme.current().bg)
        fill.setAlphaF(FILL_ALPHA)
        p.fillPath(path, fill)

        edge = QColor(theme.current().text_bright)
        edge.setAlphaF(EDGE_ALPHA)
        pen = QPen(edge)
        pen.setWidthF(border)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
