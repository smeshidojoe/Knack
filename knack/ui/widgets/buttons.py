"""
Кнопка-иконка с подсветкой при наведении.

Две формы подсветки из макета: круг под кнопками плеера (37 px) и пилюля под
вкладками (28x23, радиус 7). Цвет иконки берётся ролью темы и зависит от
состояния, поэтому одна и та же кнопка работает и вкладкой, и кнопкой плеера.
"""

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from ...core import icons
from ...core.scale import s, sf
from .. import theme


class IconButton(QWidget):
    clicked = Signal()

    def __init__(self, parent=None, icon_name="", icon_px=12,
                 hover_shape="circle", hover_size=(37, 37), hover_radius=0,
                 role="text_primary", role_hover=None, role_active=None,
                 role_disabled="text_muted"):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        self.icon_name = icon_name
        self.icon_px = icon_px
        self.hover_shape = hover_shape          # 'circle' | 'pill' | None
        self.hover_size = hover_size            # в координатах макета
        self.hover_radius = hover_radius
        self.role = role
        self.role_hover = role_hover or role
        self.role_active = role_active or role
        self.role_disabled = role_disabled

        self._hover = False
        self._down = False
        self._active = False

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

    # --- события --------------------------------------------------------- #

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self._down = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._down = True
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._down:
            self._down = False
            self.update()
            if self.rect().contains(event.position().toPoint()) and self.isEnabled():
                self.clicked.emit()

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

        if self._hover and self.isEnabled() and self.hover_shape:
            w, h = s(self.hover_size[0]), s(self.hover_size[1])
            x = (self.width() - w) / 2
            y = (self.height() - h) / 2
            rect = QRectF(x, y, w, h)
            p.setPen(Qt.NoPen)
            p.setBrush(theme.color("hover"))
            if self.hover_shape == "circle":
                p.drawEllipse(rect)
            else:
                r = sf(self.hover_radius or 7)
                p.drawRoundedRect(rect, r, r)

        if not self.icon_name:
            return
        size = s(self.icon_px)
        pm = icons.pixmap(self.icon_name, size, theme.color(self._icon_role()))
        # Нажатие — лёгкое «утапливание» на 1 px, без анимации.
        dy = 1 if self._down and self.isEnabled() else 0
        x = (self.width() - size) // 2
        y = (self.height() - size) // 2 + dy
        p.drawPixmap(x, y, pm)
