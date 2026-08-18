"""
Вкладка «Сниппеты»: то, что приходится набирать постоянно.

Сверху строка поиска: набираешь «Почта» — в списке остаётся только почта. Клик
по строке кладёт значение в буфер. Плюс справа переводит строку поиска в режим
добавления: слева имя, справа значение, Enter сохраняет, Esc отменяет.
"""

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ...core import fonts, i18n, icons
from ...core.scale import s, sf
from .. import theme
from ..widgets.buttons import IconButton
from ..widgets.field import line_edit, restyle
from ..widgets.listview import ListView
from ..widgets.text import Text
from .base import Page

BAR_X, BAR_Y, BAR_W, BAR_H, BAR_R = 54, 31, 465, 22, 7
SEARCH_ICON_X, SEARCH_ICON_PX = 9, 9
INPUT_X, INPUT_R = 22, 30          # поле ввода внутри строки: отступы слева и справа
PLUS_CX, PLUS_PX = 504.5, 9

ROW_Y, ROW_H, ROW_STEP, ROW_R = 58, 22, 24, 7
ROW_ICON_X, ROW_ICON_PX = 6, 12
ROW_NAME_X, ROW_TEXT_PX = 25, 10
NAME_GAP = 6
LIST_BOTTOM = 180

EMPTY_Y, EMPTY_PX = 126, 9
ARROW_X, ARROW_Y, ARROW_W, ARROW_H = 280.5, 101.5, 11.5, 17


class _Rows(ListView):
    def __init__(self, page, store):
        super().__init__(page, row_height=ROW_H, row_spacing=ROW_STEP - ROW_H,
                         has_close=True, close_inset=8)
        self.page = page
        self.store = store
        self.matches = []
        self._name_font = fonts.font(s(ROW_TEXT_PX), "Bold")
        self._value_font = fonts.font(s(ROW_TEXT_PX), "Regular")

    def restyle(self):
        self._name_font = fonts.font(s(ROW_TEXT_PX), "Bold")
        self._value_font = fonts.font(s(ROW_TEXT_PX), "Regular")
        self.row_height = ROW_H
        self.row_spacing = ROW_STEP - ROW_H

    def set_matches(self, matches):
        self.matches = matches
        self.refresh()
        self.update()

    def count(self):
        return len(self.matches)

    def source_index(self, index):
        if 0 <= index < len(self.matches):
            return self.matches[index][0]
        return -1

    def paint_row(self, painter, index, rect, hover):
        item = self.matches[index][1]
        r = sf(ROW_R)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.color("surface_hover" if hover else "surface"))
        painter.drawRoundedRect(QRectF(rect), r, r)

        size = s(ROW_ICON_PX)
        pm = icons.pixmap(item.get("icon") or "tag", size,
                          theme.color("text_secondary"))
        painter.drawPixmap(rect.left() + s(ROW_ICON_X),
                           rect.center().y() - size // 2, pm)

        name = str(item.get("name", ""))
        value = str(item.get("value", ""))
        left = rect.left() + s(ROW_NAME_X)
        right = rect.right() - (s(24) if hover else s(10))

        painter.setFont(self._name_font)
        name_w = QFontMetrics(self._name_font).horizontalAdvance(name)
        painter.setPen(theme.color("text_bright"))
        painter.drawText(QRectF(left, rect.top(), name_w, rect.height()),
                         int(Qt.AlignLeft | Qt.AlignVCenter), name)

        value_x = left + name_w + s(NAME_GAP)
        box = QRectF(value_x, rect.top(), max(0, right - value_x), rect.height())
        painter.setFont(self._value_font)
        painter.setPen(theme.color("text_secondary"))
        metrics = QFontMetrics(self._value_font)
        painter.drawText(box, int(Qt.AlignLeft | Qt.AlignVCenter),
                         metrics.elidedText(value, Qt.ElideRight, int(box.width())))

        if hover:
            self.paint_close(painter, self.close_rect(rect), self._hover_close)
        self.paint_flash(painter, index, QRectF(rect), r)


class _Bar(QWidget):
    """Фон строки поиска: скруглённый прямоугольник под полями ввода."""

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface"))
        r = sf(BAR_R)
        p.drawRoundedRect(QRectF(self.rect()), r, r)
        size = s(SEARCH_ICON_PX)
        pm = icons.pixmap("search", size, theme.color("text_button"))
        p.drawPixmap(s(SEARCH_ICON_X), (self.height() - size) // 2, pm)


class _Empty(QWidget):
    """Подсказка пустого списка со стрелкой к плюсу."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.text = i18n.t("snippets.empty")
        self._font = fonts.font(s(EMPTY_PX), "Medium")

    def restyle(self):
        self._font = fonts.font(s(EMPTY_PX), "Medium")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self._font)
        p.setPen(theme.color("text_muted"))
        p.drawText(self.rect(), int(Qt.AlignHCenter | Qt.AlignVCenter), self.text)

        # Стрелка от подсказки вверх, к плюсу в строке поиска.
        pen = QPen(theme.color("text_muted"))
        pen.setWidthF(max(1.0, sf(1.2)))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        x = self.width() / 2 + sf(ARROW_X - 287)
        top = self.height() / 2 - s(ARROW_H) - s(6)
        bottom = self.height() / 2 - s(9)
        tip_x = x + sf(ARROW_W)
        path = QPainterPath()
        path.moveTo(x, bottom)
        path.cubicTo(x - sf(3), bottom - sf(8), tip_x - sf(2), bottom - sf(4),
                     tip_x, top)
        p.drawPath(path)
        # Наконечник: две короткие черты от кончика вниз, поперёк касательной.
        p.drawLine(tip_x, top, tip_x - sf(5), top + sf(3))
        p.drawLine(tip_x, top, tip_x + sf(1), top + sf(6))


class SnippetsPage(Page):
    key = "snippets"
    wants_keyboard = True

    def __init__(self, store, clipboard, parent=None):
        super().__init__(parent)
        self.store = store
        self.clipboard = clipboard
        self._adding = False

        self.bar = _Bar(self)
        self.search = line_edit(self, ROW_TEXT_PX, "Medium", i18n.t("snippets.search"))
        self.search.textChanged.connect(self._apply_filter)
        self.value = line_edit(self, ROW_TEXT_PX, "Medium", i18n.t("snippets.value"))
        self.value.hide()
        self.search.returnPressed.connect(self._commit_add)
        self.value.returnPressed.connect(self._commit_add)

        self.plus = IconButton(self, icon_name="plus", icon_px=PLUS_PX,
                               hover_shape=None, role="text_button",
                               role_hover="text_bright")
        self.plus.clicked.connect(self._toggle_add)

        self.rows = _Rows(self, store)
        self.rows.activated.connect(self._copy)
        self.rows.close_requested.connect(self._remove)

        self.empty = _Empty(self)

        store.changed.connect(self._apply_filter)
        self._apply_filter()

    # --- геометрия -------------------------------------------------------- #

    def relayout(self):
        self.bar.setGeometry(s(BAR_X), s(BAR_Y), s(BAR_W), s(BAR_H))
        self.rows.restyle()
        self.rows.setGeometry(s(BAR_X), s(ROW_Y), s(BAR_W),
                              s(LIST_BOTTOM) - s(ROW_Y))
        self.empty.restyle()
        self.empty.setGeometry(s(BAR_X), s(ROW_Y), s(BAR_W),
                               s(LIST_BOTTOM) - s(ROW_Y))

        restyle(self.search, ROW_TEXT_PX)
        restyle(self.value, ROW_TEXT_PX)
        self._layout_fields()

        box = s(PLUS_PX * 2)
        self.plus.setGeometry(s(PLUS_CX) - box // 2,
                              s(BAR_Y) + (s(BAR_H) - box) // 2, box, box)
        self.plus.raise_()
        self.rows.refresh()

    def _layout_fields(self):
        left = s(BAR_X) + s(INPUT_X)
        right = s(BAR_X) + s(BAR_W) - s(INPUT_R)
        top, height = s(BAR_Y), s(BAR_H)
        if self._adding:
            half = (right - left) // 3
            self.search.setGeometry(left, top, half, height)
            self.value.setGeometry(left + half + s(8), top,
                                   right - left - half - s(8), height)
        else:
            self.search.setGeometry(left, top, right - left, height)

    # --- поведение --------------------------------------------------------- #

    def _apply_filter(self):
        query = "" if self._adding else self.search.text()
        matches = self.store.search(query)
        self.rows.set_matches(matches)
        show_empty = not self.store.items and not self._adding
        self.empty.setVisible(show_empty)
        self.rows.setVisible(not show_empty)

    def _toggle_add(self):
        self._adding = not self._adding
        self.value.setVisible(self._adding)
        self.search.setPlaceholderText(
            i18n.t("snippets.name") if self._adding else i18n.t("snippets.search"))
        self.search.clear()
        self.value.clear()
        self._layout_fields()
        self._apply_filter()
        if self._adding:
            self.search.setFocus()

    def _commit_add(self):
        if not self._adding:
            return
        name = self.search.text().strip()
        value = self.value.text().strip()
        if name and value:
            self.store.add(name, value)
            self._toggle_add()

    def _copy(self, index):
        source = self.rows.source_index(index)
        if 0 <= source < len(self.store.items):
            self.clipboard.copy_text(self.store.items[source].get("value"))
            self.rows.flash(index)

    def _remove(self, index):
        source = self.rows.source_index(index)
        if source >= 0:
            self.store.remove(source)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self._adding:
            self._toggle_add()

    # --- жизненный цикл ---------------------------------------------------- #

    def retranslate(self):
        self.empty.text = i18n.t("snippets.empty")
        self.search.setPlaceholderText(
            i18n.t("snippets.name") if self._adding else i18n.t("snippets.search"))
        self.value.setPlaceholderText(i18n.t("snippets.value"))
        self.update()

    def on_hide(self):
        if self._adding:
            self._toggle_add()
        self.search.clear()
