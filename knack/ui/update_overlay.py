"""
Карточка обновления поверх панели.

Пока идёт загрузка новой версии, панель нельзя ни закрыть, ни потыкать: сейчас
она подменит собственный exe и перезапустится, и незаконченное действие в другой
вкладке всё равно пропадёт. Поэтому содержимое затемняется, поверх выезжает
карточка с полосой прогресса, а клики до вкладок не доходят.

Сделано по образцу такого же окна в Snatchr.
"""

from PySide6.QtCore import QEasingCurve, QRectF, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from ..core import fonts
from ..core.constants import PANEL_RADIUS
from ..core.scale import s, sf
from . import theme
from .anim import Tween

DIM_ALPHA = 0.72

CARD_W, CARD_H, CARD_R = 260, 78, 12
TITLE_PX, PERCENT_PX = 11, 9
BAR_W, BAR_H, BAR_R = 212, 4, 2
TITLE_TOP, BAR_TOP = 18, 46
RISE = 22          # на сколько карточка выезжает снизу


class UpdateOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._title = ""
        self._fraction = 0.0
        self._appear = Tween(lambda _v: self.update(), value=0.0, duration=0.26)
        self.hide()

    # --- данные ----------------------------------------------------------- #

    def start(self, title):
        self._title = title or ""
        self._fraction = 0.0
        self.show()
        self.raise_()
        self._appear.set(0.0)
        self._appear.target(1.0, 0.26, QEasingCurve.OutCubic)

    def set_title(self, title):
        self._title = title or ""
        self.update()

    def set_progress(self, fraction):
        self._fraction = max(0.0, min(1.0, float(fraction or 0.0)))
        self.update()

    def finish(self):
        self._appear.set(0.0)
        self.hide()

    # --- события ---------------------------------------------------------- #

    def mousePressEvent(self, event):
        event.accept()          # клики до вкладок не доходят

    def mouseReleaseEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    # --- отрисовка -------------------------------------------------------- #

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        progress = self._appear.value

        # Затемнение по форме панели, чтобы не залезть на скруглённые углы.
        radius = sf(PANEL_RADIUS)
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(self.rect()), radius, radius)
        dim = QColor(theme.current().bg)
        dim.setAlphaF(DIM_ALPHA * progress)
        p.fillPath(shape, dim)

        card_w, card_h = s(CARD_W), s(CARD_H)
        left = (self.width() - card_w) / 2
        top = (self.height() - card_h) / 2 + s(RISE) * (1.0 - progress)

        card = QRectF(left, top, card_w, card_h)
        p.setOpacity(progress)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface_alt"))
        p.drawRoundedRect(card, sf(CARD_R), sf(CARD_R))

        p.setFont(fonts.font(s(TITLE_PX), "Medium"))
        p.setPen(theme.color("text_bright"))
        p.drawText(QRectF(left, top + s(TITLE_TOP), card_w, s(16)),
                   int(Qt.AlignHCenter | Qt.AlignVCenter), self._title)

        bar_w, bar_h = s(BAR_W), s(BAR_H)
        bar_x = left + (card_w - bar_w) / 2
        bar_y = top + s(BAR_TOP)
        radius_bar = sf(BAR_R)
        p.setBrush(theme.color("track"))
        p.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), radius_bar, radius_bar)
        if self._fraction > 0:
            filled = max(bar_h, bar_w * self._fraction)
            p.setBrush(theme.color("track_fill"))
            p.drawRoundedRect(QRectF(bar_x, bar_y, filled, bar_h),
                              radius_bar, radius_bar)

        percent = "%d%%" % round(self._fraction * 100)
        font = fonts.font(s(PERCENT_PX), "Semibold")
        p.setFont(font)
        p.setPen(theme.color("text_secondary"))
        width = QFontMetrics(font).horizontalAdvance(percent)
        p.drawText(QRectF(bar_x + bar_w - width, bar_y + bar_h + s(4),
                          width, s(12)),
                   int(Qt.AlignRight | Qt.AlignVCenter), percent)
        p.setOpacity(1.0)
