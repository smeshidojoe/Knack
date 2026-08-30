"""
Вкладка «Буфер»: история скопированного текста.

Строки идут сверху вниз, свежая первая. Клик по строке возвращает текст в буфер,
крестик справа убирает одну запись, «Очистить» в правом нижнем углу — всю
историю. Длина ограничена настройкой clipboard_limit (по умолчанию 100), лишнее
вытесняется с конца.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFontMetrics, QPainter

from ...core import fonts, i18n, icons
from ...core.constants import BODY_R
from ...core.scale import s, sf
from .. import theme
from ..widgets.controls import TextButton
from ..widgets.listview import ListView
from ..widgets.text import Text
from .base import Page

ROW_X, ROW_Y, ROW_W, ROW_H = 54, 34, 450, 16
ROW_STEP   = 20
ROW_RADIUS = 3
LIST_BOTTOM = 166

ICON_X, ICON_PX = 2.9, 9      # значок строки внутри строки
TEXT_X   = 18                 # текст внутри строки
TEXT_PX  = 10

CLEAR_R, CLEAR_Y, CLEAR_H, CLEAR_PX = 558, 171, 11, 9


class _History(ListView):
    def __init__(self, service, parent=None):
        super().__init__(parent, row_height=ROW_H, row_spacing=ROW_STEP - ROW_H,
                         has_close=True, close_inset=4)
        self.service = service
        self._font = fonts.font(s(TEXT_PX), "Medium")

    def restyle(self):
        self._font = fonts.font(s(TEXT_PX), "Medium")
        self.row_height = ROW_H
        self.row_spacing = ROW_STEP - ROW_H

    def count(self):
        return len(self.service.history)

    def paint_row(self, painter, index, rect, hover):
        if hover:
            r = sf(ROW_RADIUS)
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.color("surface"))
            painter.drawRoundedRect(QRectF(rect), r, r)

        size = s(ICON_PX)
        pm = icons.pixmap("textlines", size, theme.color("text_muted"))
        painter.drawPixmap(rect.left() + s(ICON_X),
                           rect.center().y() - size // 2 + 1, pm)

        text = (self.service.history[index].get("text") or "").replace("\n", " ")
        painter.setFont(self._font)
        painter.setPen(theme.color("text_bright"))
        left = rect.left() + s(TEXT_X)
        right = rect.right() - (s(16) if hover else s(4))
        box = QRectF(left, rect.top(), max(0, right - left), rect.height())
        metrics = QFontMetrics(self._font)
        painter.drawText(box, int(Qt.AlignLeft | Qt.AlignVCenter),
                         metrics.elidedText(text, Qt.ElideRight, int(box.width())))

        if hover:
            self.paint_close(painter, self.close_rect(rect), self._hover_close)
        self.paint_flash(painter, index, QRectF(rect), sf(ROW_RADIUS))


class ClipboardPage(Page):
    key = "clipboard"

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service

        self.list = _History(service, self)
        self.list.activated.connect(self._copy)
        self.list.close_requested.connect(self.service.remove)

        self.empty = Text(self, text=i18n.t("clipboard.empty"),
                          role="text_muted", align=Qt.AlignHCenter)
        self.clear = TextButton(self, i18n.t("clipboard.clear"), flat=True)
        self.clear.clicked.connect(self.service.clear)

        service.history_changed.connect(self._refresh)
        self._refresh()

    # --- геометрия -------------------------------------------------------- #

    def relayout(self):
        self.list.restyle()
        self.list.setGeometry(s(ROW_X), s(ROW_Y), s(ROW_W),
                              s(LIST_BOTTOM) - s(ROW_Y))
        self.empty.set_font_px(s(9), "Medium")
        self.empty.setGeometry(s(ROW_X), s(ROW_Y), s(BODY_R) - s(ROW_X),
                               s(LIST_BOTTOM) - s(ROW_Y))
        self.clear.restyle()
        width = max(s(60), self.clear.width_hint())
        height = s(CLEAR_H) + s(8)
        self.clear.setGeometry(s(CLEAR_R) - width, s(CLEAR_Y) - s(4), width, height)
        self.list.refresh()

    # --- поведение --------------------------------------------------------- #

    def _refresh(self):
        has = bool(self.service.history)
        self.list.setVisible(has)
        self.empty.setVisible(not has)
        self.clear.set_shown(has)
        self.list.refresh()
        self.list.update()

    def _copy(self, index):
        if 0 <= index < len(self.service.history):
            self.service.copy_text(self.service.history[index].get("text"))
            self.list.flash(index)

    def retranslate(self):
        self.empty.set_text(i18n.t("clipboard.empty"))
        self.clear.set_label(i18n.t("clipboard.clear"))
