"""
Полоса прогресса с перемоткой.

Виджет выше самой полосы: полосу 4 px не поймать мышью, поэтому кликабельная
область занимает всю строку, а полоса рисуется по центру.

Под курсором появляется метка-превью — куда встанет ползунок, если кликнуть.
Цвет у неё свой, чтобы не спорить с самим прогрессом.

Пока пользователь тянет, значения извне игнорируются: иначе бегунок дёргался бы
назад на каждом опросе позиции.
"""

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from ...core.scale import sf
from .. import theme

BAR_H       = 4     # высота полосы, px макета
KNOB_R      = 4     # радиус бегунка при наведении
PREVIEW_W   = 2     # ширина метки превью
PREVIEW_H   = 9     # высота метки превью


class SeekBar(QWidget):
    seek = Signal(float)            # секунда, куда перемотать
    scrubbing = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)     # превью нужно и без нажатой кнопки
        self.setAttribute(Qt.WA_Hover, True)
        self._position = 0.0
        self._duration = 0.0
        self._hover = False
        self._hover_x = 0.0
        self._drag = False
        self._drag_frac = 0.0

    # --- данные ---------------------------------------------------------- #

    def set_values(self, position, duration):
        if self._drag:
            return
        changed = (abs(position - self._position) > 0.02
                   or abs(duration - self._duration) > 0.02)
        self._position = max(0.0, float(position))
        self._duration = max(0.0, float(duration))
        if changed:
            self.update()

    def fraction(self):
        if self._drag:
            return self._drag_frac
        if self._duration <= 0:
            return 0.0
        return min(1.0, self._position / self._duration)

    def is_scrubbing(self):
        return self._drag

    def preview_seconds(self):
        """Секунда под курсором или None, если курсор вне полосы."""
        if not self._hover or self._duration <= 0:
            return None
        return self._frac_at(self._hover_x) * self._duration

    # --- события --------------------------------------------------------- #

    def _frac_at(self, x):
        if self.width() <= 0:
            return 0.0
        return max(0.0, min(1.0, x / self.width()))

    def enterEvent(self, event):
        self._hover = True
        self._hover_x = event.position().x()
        self.setCursor(Qt.PointingHandCursor if self.isEnabled() else Qt.ArrowCursor)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._duration <= 0:
            return
        self._drag = True
        self._drag_frac = self._frac_at(event.position().x())
        self.scrubbing.emit(True)
        self.update()

    def mouseMoveEvent(self, event):
        self._hover = True
        self._hover_x = event.position().x()
        if self._drag:
            self._drag_frac = self._frac_at(self._hover_x)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton or not self._drag:
            return
        self._drag = False
        frac = self._frac_at(event.position().x())
        self._position = frac * self._duration
        self.scrubbing.emit(False)
        self.seek.emit(self._position)
        self.update()

    # --- отрисовка ------------------------------------------------------- #

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)

        h = sf(BAR_H)
        y = (self.height() - h) / 2
        r = h / 2
        p.setBrush(theme.color("track"))
        p.drawRoundedRect(QRectF(0, y, self.width(), h), r, r)

        if self._hover and self.isEnabled() and self._duration > 0 and not self._drag:
            pw, ph = sf(PREVIEW_W), sf(PREVIEW_H)
            x = min(max(self._hover_x - pw / 2, 0), self.width() - pw)
            p.setBrush(theme.color("track_preview"))
            p.drawRoundedRect(QRectF(x, (self.height() - ph) / 2, pw, ph),
                              pw / 2, pw / 2)

        frac = self.fraction()
        if frac > 0:
            w = max(h, self.width() * frac)     # не тоньше собственной скруглённости
            p.setBrush(theme.color("track_fill"))
            p.drawRoundedRect(QRectF(0, y, w, h), r, r)

        if (self._hover or self._drag) and self.isEnabled() and self._duration > 0:
            knob = sf(KNOB_R)
            cx = min(max(self.width() * frac, knob), self.width() - knob)
            p.setBrush(theme.color("track_fill"))
            p.drawEllipse(QRectF(cx - knob, self.height() / 2 - knob,
                                 knob * 2, knob * 2))
