"""
Кнопка-иконка с подсветкой и масштабной анимацией.

Две формы подсветки из макета: круг под кнопками плеера (37 px) и пилюля под
вкладками (28x23, радиус 7).

Анимация: при наведении иконка и подсветка вместе плавно подрастают, при уводе
возвращаются к обычному размеру. Клик сначала поджимает кнопку, потом отпускает
обратно к «наведённому» размеру с лёгким перелётом. Каждая кнопка тянет своё
значение отдельным твином, поэтому переезд мыши с одной вкладки на другую даёт
две встречные анимации, а не рывок.

Иконка растеризуется один раз в размере под максимальный масштаб и рисуется в
уменьшенный прямоугольник — так при анимации не появляются ступеньки от
округления размера до целых пикселей.
"""

from PySide6.QtCore import QEasingCurve, QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from ...core import icons
from ...core.scale import s, sf
from .. import theme
from ..anim import Tween

HOVER_SCALE = 1.14
PRESS_SCALE = 0.90

HOVER_MS = 0.16
PRESS_MS = 0.09
BACK_MS  = 0.22


class IconButton(QWidget):
    clicked = Signal()

    def __init__(self, parent=None, icon_name="", icon_px=12,
                 hover_shape="circle", hover_size=(37, 37), hover_radius=0,
                 role="text_primary", role_hover=None, role_active=None,
                 role_disabled="text_muted", icon_offset=(0, 0), animate=True):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        self.icon_name = icon_name
        self.icon_px = icon_px
        self.icon_offset = icon_offset          # сдвиг глифа, px макета
        self.hover_shape = hover_shape          # 'circle' | 'pill' | None
        self.hover_size = hover_size            # в координатах макета
        self.hover_radius = hover_radius
        self.role = role
        self.role_hover = role_hover or role
        self.role_active = role_active or role
        self.role_disabled = role_disabled
        self.animate = animate

        self._hover = False
        self._down = False
        self._active = False
        self._scale = 1.0
        self._tween = Tween(self._on_scale, value=1.0, duration=HOVER_MS)

    # --- состояние ------------------------------------------------------- #

    def set_active(self, value):
        value = bool(value)
        if value != self._active:
            self._active = value
            self.update()

    def is_active(self):
        return self._active

    def set_icon(self, name):
        if name != self.icon_name:
            self.icon_name = name
            self.update()

    def _on_scale(self, value):
        self._scale = value
        self.update()

    def _go(self, value, duration, curve=QEasingCurve.OutCubic):
        if self.animate:
            self._tween.target(value, duration, curve)
        else:
            self._tween.set(value)

    def _rest_scale(self):
        return HOVER_SCALE if (self._hover and self.isEnabled()) else 1.0

    # --- события --------------------------------------------------------- #

    def enterEvent(self, event):
        self._hover = True
        self._go(self._rest_scale(), HOVER_MS)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._down = False
        self._go(1.0, HOVER_MS)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._down = True
            self._go(PRESS_SCALE, PRESS_MS)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self._down:
            return
        self._down = False
        inside = self.rect().contains(event.position().toPoint())
        self._hover = self._hover and inside
        self._go(self._rest_scale(), BACK_MS, QEasingCurve.OutBack)
        if inside and self.isEnabled():
            self.clicked.emit()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == event.Type.EnabledChange and not self.isEnabled():
            self._hover = self._down = False
            self._go(1.0, HOVER_MS)

    def hideEvent(self, event):
        super().hideEvent(event)
        # Скрытая кнопка не должна держать общий таймер анимаций.
        self._tween.set(1.0)
        self._hover = self._down = False

    # --- отрисовка ------------------------------------------------------- #

    def _icon_role(self):
        if not self.isEnabled():
            return self.role_disabled
        if self._active:
            return self.role_active
        if self._hover:
            return self.role_hover
        return self.role

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        cx, cy = self.width() / 2, self.height() / 2
        p.translate(cx, cy)
        p.scale(self._scale, self._scale)
        p.translate(-cx, -cy)

        if self._hover and self.isEnabled() and self.hover_shape:
            w, h = s(self.hover_size[0]), s(self.hover_size[1])
            rect = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
            p.setPen(Qt.NoPen)
            p.setBrush(theme.color("hover"))
            if self.hover_shape == "circle":
                p.drawEllipse(rect)
            else:
                r = sf(self.hover_radius or 7)
                p.drawRoundedRect(rect, r, r)

        if not self.icon_name:
            return
        side = sf(self.icon_px)
        pm = icons.pixmap(self.icon_name, s(self.icon_px * HOVER_SCALE),
                          theme.color(self._icon_role()))
        rect = QRectF((self.width() - side) / 2 + sf(self.icon_offset[0]),
                      (self.height() - side) / 2 + sf(self.icon_offset[1]),
                      side, side)
        p.drawPixmap(rect, pm, QRectF(pm.rect()))
