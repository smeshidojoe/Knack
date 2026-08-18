"""
Меню в стиле панели.

Нативное QMenu на Windows рисуется системой: свой фон, свои отступы, своя рамка
и чужой шрифт — рядом с чёрной панелью оно выглядит как кусок другой программы.
Поэтому меню рисуем сами, теми же цветами и тем же SF Pro.

Виджет — Qt.Popup: Qt сам закрывает его по клику мимо и по Esc.
"""

from PySide6.QtCore import QPoint, QRectF, Qt, Signal
from PySide6.QtGui import QFontMetrics, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from ..core import fonts
from ..core.scale import s, sf
from . import theme

ITEM_H     = 30     # высота строки, px макета
ITEM_PAD_X = 12
GAP_H      = 7      # высота разделителя
RADIUS     = 10
BORDER     = 1
FONT_PX    = 11
CHECK_W    = 14     # колонка под галочку
MIN_W      = 150


class Menu(QWidget):
    """items: список (key, label) либо None для разделителя."""

    triggered = Signal(str)

    def __init__(self, items, checks=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

        self.items = list(items)
        self.checks = dict(checks or {})     # key -> bool, рисуем галочку
        self._hover = -1
        self._font = fonts.font(s(FONT_PX), "Medium")

        self._rows = []                      # (y, h, index) в пикселях экрана
        self._measure()

    # --- геометрия ------------------------------------------------------- #

    def _measure(self):
        fm = QFontMetrics(self._font)
        pad = s(ITEM_PAD_X)
        check = s(CHECK_W) if self.checks else 0
        width = s(MIN_W)
        for item in self.items:
            if item is None:
                continue
            width = max(width, pad * 2 + check + fm.horizontalAdvance(item[1]))

        y = s(6)
        self._rows = []
        for index, item in enumerate(self.items):
            h = s(GAP_H) if item is None else s(ITEM_H)
            self._rows.append((y, h, index))
            y += h
        self.setFixedSize(width, y + s(6))

    def popup_at(self, pos):
        """Показывает меню у точки, не вылезая за край экрана."""
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(max(pos.x(), geo.left()), geo.right() - self.width())
        y = pos.y()
        if y + self.height() > geo.bottom():
            y = pos.y() - self.height()          # у нижнего края раскрываем вверх
        y = min(max(y, geo.top()), geo.bottom() - self.height())
        self.move(QPoint(int(x), int(y)))
        self.show()
        self.raise_()

    def _index_at(self, point):
        for y, h, index in self._rows:
            if self.items[index] is not None and y <= point.y() < y + h:
                return index
        return -1

    # --- события --------------------------------------------------------- #

    def mouseMoveEvent(self, event):
        index = self._index_at(event.position().toPoint())
        if index != self._hover:
            self._hover = index
            self.update()

    def leaveEvent(self, event):
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        index = self._index_at(event.position().toPoint())
        if index >= 0:
            key = self.items[index][0]
            self.close()
            self.triggered.emit(key)

    # --- отрисовка ------------------------------------------------------- #

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)

        r = sf(RADIUS)
        border = sf(BORDER)
        body = QRectF(border / 2, border / 2,
                      self.width() - border, self.height() - border)
        path = QPainterPath()
        path.addRoundedRect(body, r, r)
        p.fillPath(path, theme.color("menu_bg"))
        p.setPen(theme.color("menu_border"))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        p.setFont(self._font)
        pad = s(ITEM_PAD_X)
        check = s(CHECK_W) if self.checks else 0
        inset = s(4)

        for y, h, index in self._rows:
            item = self.items[index]
            if item is None:
                p.setPen(theme.color("menu_border"))
                mid = y + h / 2
                p.drawLine(int(pad), int(mid), int(self.width() - pad), int(mid))
                continue

            key, label = item
            if index == self._hover:
                p.setPen(Qt.NoPen)
                p.setBrush(theme.color("hover"))
                rr = sf(7)
                p.drawRoundedRect(QRectF(inset, y, self.width() - inset * 2, h), rr, rr)

            if self.checks.get(key):
                p.setPen(theme.color("text_primary"))
                p.drawText(QRectF(pad, y, check, h), int(Qt.AlignLeft | Qt.AlignVCenter),
                           "✓")

            p.setPen(theme.color("text_primary" if index == self._hover
                                 else "text_secondary"))
            p.drawText(QRectF(pad + check, y, self.width() - pad * 2 - check, h),
                       int(Qt.AlignLeft | Qt.AlignVCenter), label)
