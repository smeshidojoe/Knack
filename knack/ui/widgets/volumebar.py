"""
Регулятор громкости: значок динамика и короткая полоса.

Стоит справа от кнопок перемотки — единственное свободное место в этой строке,
где он не спорит ни с обложкой, ни с названием трека.

Полоса тонкая, поэтому мышь ловит весь виджет, а не саму полосу: клик ставит
уровень, протяжка ведёт его за курсором, колесо двигает по 5%. Клик по значку
выключает и включает звук.
"""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPen
from PySide6.QtWidgets import QWidget

from ...core.scale import s, sf
from .. import theme

ICON_W, ICON_H = 11, 11     # бокс значка, px макета
GAP = 6                     # от значка до полосы
BAR_H = 3
KNOB_R = 3.5
WHEEL_STEP = 0.05


class VolumeBar(QWidget):
    moved = Signal(float)       # уровень 0..1, пока тянут или крутят колесо
    mute_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self._level = 0.0
        self._muted = False
        self._hover = False
        self._drag = False

    # --- данные ----------------------------------------------------------- #

    def set_values(self, level, muted):
        if self._drag:
            return          # пока тянут, чужие значения не мешают
        level = max(0.0, min(1.0, float(level)))
        if abs(level - self._level) < 0.001 and muted == self._muted:
            return
        self._level, self._muted = level, muted
        self.update()

    def level(self):
        return self._level

    # --- геометрия -------------------------------------------------------- #

    def _icon_rect(self):
        w, h = s(ICON_W), s(ICON_H)
        return QRectF(0, (self.height() - h) / 2.0, w, h)

    def _bar_rect(self):
        left = s(ICON_W) + s(GAP)
        h = sf(BAR_H)
        return QRectF(left, (self.height() - h) / 2.0,
                      max(1.0, self.width() - left), h)

    def _level_at(self, x):
        bar = self._bar_rect()
        if bar.width() <= 0:
            return 0.0
        return max(0.0, min(1.0, (x - bar.left()) / bar.width()))

    # --- события ---------------------------------------------------------- #

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._icon_rect().contains(event.position()):
            self.mute_clicked.emit()
            return
        self._drag = True
        self._apply(event.position().x())

    def mouseMoveEvent(self, event):
        if self._drag:
            self._apply(event.position().x())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag:
            self._drag = False
            self._apply(event.position().x())

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120.0
        if not steps:
            return
        self._set(self._level + steps * WHEEL_STEP)

    def _apply(self, x):
        self._set(self._level_at(x))

    def _set(self, value):
        value = max(0.0, min(1.0, value))
        if abs(value - self._level) < 0.001:
            return
        self._level = value
        self._muted = False
        self.update()
        self.moved.emit(value)

    # --- отрисовка -------------------------------------------------------- #

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        bright = self._hover or self._drag
        self._paint_icon(p, self._icon_rect(), bright)

        bar = self._bar_rect()
        radius = bar.height() / 2.0
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("track"))
        p.drawRoundedRect(bar, radius, radius)

        filled = 0.0 if self._muted else self._level
        if filled > 0:
            done = QRectF(bar)
            done.setWidth(max(bar.height(), bar.width() * filled))
            p.setBrush(theme.color("track_fill"))
            p.drawRoundedRect(done, radius, radius)

        if bright:
            knob = sf(KNOB_R)
            cx = bar.left() + bar.width() * filled
            cx = max(bar.left() + knob, min(bar.right() - knob, cx))
            p.setBrush(theme.color("track_fill"))
            p.drawEllipse(QPointF(cx, bar.center().y()), knob, knob)

    def _paint_icon(self, p, rect, bright):
        """
        Динамик рисуем сами: отдельного значка в макете нет, а рисованный
        остаётся резким на любом масштабе панели.
        """
        p.save()
        color = theme.color("text_primary" if bright else "text_secondary")
        w, h = rect.width(), rect.height()
        x, y = rect.left(), rect.top()

        p.setPen(Qt.NoPen)
        p.setBrush(color)
        body = QRectF(x + w * 0.04, y + h * 0.34, w * 0.20, h * 0.32)
        p.drawRect(body)
        p.drawPolygon([
            QPointF(x + w * 0.24, y + h * 0.34),
            QPointF(x + w * 0.50, y + h * 0.12),
            QPointF(x + w * 0.50, y + h * 0.88),
            QPointF(x + w * 0.24, y + h * 0.66),
        ])

        pen = QPen(color)
        pen.setWidthF(max(1.0, sf(1.1)))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if self._muted:
            # Крестик вместо волн: перечёркнутый динамик читается сразу.
            p.drawLine(QPointF(x + w * 0.68, y + h * 0.36),
                       QPointF(x + w * 0.98, y + h * 0.64))
            p.drawLine(QPointF(x + w * 0.98, y + h * 0.36),
                       QPointF(x + w * 0.68, y + h * 0.64))
        else:
            # Вторая волна появляется на громкости выше половины — заодно
            # видно уровень, не глядя на полосу.
            waves = [(0.58, 0.28)] if self._level <= 0.5 else [(0.58, 0.28),
                                                               (0.78, 0.44)]
            for left, span in waves:
                box = QRectF(x + w * left - w * span, y + h * (0.5 - span),
                             w * span * 2, h * span * 2)
                p.drawArc(box, -55 * 16, 110 * 16)
        p.restore()
