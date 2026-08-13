"""Текстовая метка: цвет берётся из темы, длинная строка обрезается многоточием."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ...core import fonts
from .. import theme


class Text(QWidget):
    def __init__(self, parent=None, text="", role="text_primary",
                 align=Qt.AlignLeft, elide=Qt.ElideRight):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._text = text
        self._role = role
        self._align = align
        self._elide = elide

    # --- данные ---------------------------------------------------------- #

    def text(self):
        return self._text

    def set_text(self, value):
        value = value or ""
        if value != self._text:
            self._text = value
            self.update()

    def set_role(self, role):
        if role != self._role:
            self._role = role
            self.update()

    def set_font_px(self, px, style="Regular", letter_spacing=0.0):
        self.setFont(fonts.font(px, style, letter_spacing))
        self.update()

    def text_width(self):
        return QFontMetrics(self.font()).horizontalAdvance(self._text)

    # --- отрисовка ------------------------------------------------------- #

    def paintEvent(self, _event):
        if not self._text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self.font())
        p.setPen(theme.color(self._role))
        fm = QFontMetrics(self.font())
        s = self._text
        if self._elide is not None and fm.horizontalAdvance(s) > self.width():
            s = fm.elidedText(s, self._elide, self.width())
        p.drawText(self.rect(), int(self._align | Qt.AlignVCenter), s)
