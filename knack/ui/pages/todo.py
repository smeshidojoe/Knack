"""
Вкладка TODO.

Строка списка — галочка и текст. Клик по галочке отмечает задачу, клик по
тексту открывает его на правку прямо в строке, крестик справа удаляет. Сверху
кнопка «Новая задача»: заводит пустую строку и сразу ставит в неё курсор.

Поле правки одно на весь список и переезжает к нужной строке: держать по
QLineEdit на каждую задачу дороже, а видно всё равно только одно.
"""

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ...core import fonts, i18n, icons
from ...core.scale import s, sf
from .. import theme
from ..widgets.field import line_edit, restyle
from ..widgets.listview import ListView
from ..widgets.text import Text
from .base import Page

NEW_X, NEW_Y, NEW_W, NEW_H, NEW_R = 54, 31, 465, 22, 7
NEW_PLUS_X, NEW_PLUS_PX, NEW_GAP, NEW_TEXT_PX = 9, 7, 8, 10

ROW_Y, ROW_H, ROW_STEP, ROW_R = 58, 22, 24, 7
LIST_BOTTOM = 180

BOX_X, BOX_PX, BOX_R = 8, 12, 3     # галочка: отступ слева, сторона, радиус
TEXT_X, TEXT_PX = 27, 10
TEXT_RIGHT, TEXT_RIGHT_HOVER = 8, 22

EMPTY_PX = 9
COUNT_R, COUNT_Y, COUNT_H, COUNT_PX = 558, 9, 11, 9    # счётчик в правом углу

# QLineEdit держит собственный отступ текста в 2 px и не отдаёт его ни стилю, ни
# setTextMargins. Поле правки стоит на месте нарисованной строки, и без поправки
# текст при клике заметно прыгал вправо. Отступ в физических пикселях, поэтому
# масштабом не умножается.
EDIT_NUDGE = 2


class _NewButton(QWidget):
    """Полоса «Новая задача» во всю ширину списка."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._hover = False
        self._font = fonts.font(s(NEW_TEXT_PX), "Medium")

    def restyle(self):
        self._font = fonts.font(s(NEW_TEXT_PX), "Medium")

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface_hover" if self._hover else "surface"))
        r = sf(NEW_R)
        p.drawRoundedRect(QRectF(self.rect()), r, r)

        role = "text_bright" if self._hover else "text_button"
        glyph = s(NEW_PLUS_PX)
        x = s(NEW_PLUS_X)
        pm = icons.pixmap("plus", glyph, theme.color(role))
        p.drawPixmap(x, (self.height() - glyph) // 2, pm)

        p.setFont(self._font)
        p.setPen(theme.color(role))
        left = x + glyph + s(NEW_GAP)
        p.drawText(QRectF(left, 0, self.width() - left, self.height()),
                   int(Qt.AlignLeft | Qt.AlignVCenter), i18n.t("todo.new"))


class _Rows(ListView):
    """Список задач. Галочка ловит клик отдельно от строки."""

    toggled = Signal(int)

    def __init__(self, store, parent=None):
        super().__init__(parent, row_height=ROW_H, row_spacing=ROW_STEP - ROW_H,
                         has_close=True, close_inset=8)
        self.store = store
        self.editing = -1        # строка, которую правят: её текст не рисуем
        self._font = fonts.font(s(TEXT_PX), "Medium")
        self._hover_box = False

    def restyle(self):
        self._font = fonts.font(s(TEXT_PX), "Medium")
        self.row_height = ROW_H
        self.row_spacing = ROW_STEP - ROW_H

    def count(self):
        return len(self.store.items)

    def box_rect(self, row):
        side = s(BOX_PX)
        return QRectF(row.left() + s(BOX_X), row.center().y() - side / 2 + 1,
                      side, side)

    def text_rect(self, row, hover):
        left = row.left() + s(TEXT_X)
        right = row.right() - s(TEXT_RIGHT_HOVER if hover else TEXT_RIGHT)
        return QRectF(left, row.top(), max(0, right - left), row.height())

    # --- события ---------------------------------------------------------- #

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        index = self.hover_index()
        box = (index >= 0
               and self.box_rect(self.row_rect(index)).contains(event.position()))
        if box != self._hover_box:
            self._hover_box = box
            self.update()

    def leaveEvent(self, event):
        self._hover_box = False
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        # Галочка перехватывает клик до общей обработки: иначе строка ушла бы
        # в правку, а отметить задачу было бы нечем.
        if event.button() == Qt.LeftButton:
            point = event.position().toPoint()
            index = self._index_at(point)
            if index >= 0 and self.box_rect(self.row_rect(index)).contains(
                    event.position()):
                self.toggled.emit(index)
                return
        super().mouseReleaseEvent(event)

    # --- отрисовка -------------------------------------------------------- #

    def paint_row(self, painter, index, rect, hover):
        item = self.store.items[index]
        done = bool(item.get("done"))

        r = sf(ROW_R)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.color("surface_hover" if hover else "surface_alt"))
        painter.drawRoundedRect(QRectF(rect), r, r)

        self._paint_box(painter, self.box_rect(rect), done,
                        hover and self._hover_box)

        if index != self.editing:
            painter.setFont(self._font)
            painter.setPen(theme.color("text_secondary" if done else "text_bright"))
            box = self.text_rect(rect, hover)
            font = self._font
            if done:
                # Зачёркиванием отличаем сделанное на беглый взгляд: одного
                # приглушённого цвета в списке из десяти строк мало.
                font = fonts.font(s(TEXT_PX), "Medium")
                font.setStrikeOut(True)
                painter.setFont(font)
            metrics = QFontMetrics(font)
            painter.drawText(box, int(Qt.AlignLeft | Qt.AlignVCenter),
                             metrics.elidedText(item.get("text") or "",
                                                Qt.ElideRight, int(box.width())))

        if hover:
            self.paint_close(painter, self.close_rect(rect), self._hover_close)

    def _paint_box(self, painter, rect, done, hover):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        radius = sf(BOX_R)
        if done:
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.color("text_bright"))
            painter.drawRoundedRect(rect, radius, radius)
            pen = QPen(theme.color("bg"))
            pen.setWidthF(max(1.0, sf(1.4)))
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            # Галочка нарисована по трём точкам внутри квадрата, а не иконкой:
            # так она остаётся резкой на любом масштабе панели.
            x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
            painter.drawPolyline([
                QPointF(x + w * 0.26, y + h * 0.52),
                QPointF(x + w * 0.44, y + h * 0.70),
                QPointF(x + w * 0.74, y + h * 0.32),
            ])
        else:
            pen = QPen(theme.color("text_bright" if hover else "text_button"))
            pen.setWidthF(max(1.0, sf(1.2)))
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            inset = pen.widthF() / 2
            painter.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset),
                                    radius, radius)
        painter.restore()


class _Empty(QWidget):
    """Подпись «Задач нет» посреди пустого списка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._font = fonts.font(s(EMPTY_PX), "Medium")

    def restyle(self):
        self._font = fonts.font(s(EMPTY_PX), "Medium")

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self._font)
        p.setPen(theme.color("text_muted"))
        p.drawText(self.rect(), int(Qt.AlignHCenter | Qt.AlignTop),
                   i18n.t("todo.empty"))


class TodoPage(Page):
    key = "todo"
    wants_keyboard = True

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._editing_id = ""

        self.new_button = _NewButton(self)
        self.new_button.clicked.connect(self._create)

        self.rows = _Rows(store, self)
        self.rows.activated.connect(self._edit)
        self.rows.toggled.connect(self._toggle)
        self.rows.close_requested.connect(self._remove)

        self.empty = _Empty(self)
        self.count = Text(self, role="text_muted", align=Qt.AlignRight)

        self.editor = line_edit(self, TEXT_PX, "Medium",
                                i18n.t("todo.placeholder"))
        self.editor.hide()
        self.editor.returnPressed.connect(self._commit)
        self.editor.editingFinished.connect(self._commit)

        store.changed.connect(self._refresh)
        self._refresh()

    # --- геометрия -------------------------------------------------------- #

    def relayout(self):
        self.new_button.restyle()
        self.new_button.setGeometry(s(NEW_X), s(NEW_Y), s(NEW_W), s(NEW_H))

        height = s(LIST_BOTTOM) - s(ROW_Y)
        self.rows.restyle()
        self.rows.setGeometry(s(NEW_X), s(ROW_Y), s(NEW_W), height)
        self.empty.restyle()
        self.empty.setGeometry(s(NEW_X), s(ROW_Y) + height // 3, s(NEW_W),
                               s(EMPTY_PX) * 3)

        restyle(self.editor, TEXT_PX)
        self.count.set_font_px(s(COUNT_PX), "Bold")
        self.count.setGeometry(s(COUNT_R) - s(60), s(COUNT_Y), s(60), s(COUNT_H))
        self.rows.refresh()
        self._place_editor()

    def _place_editor(self):
        """Поле правки встаёт ровно на текст своей строки."""
        index = self.rows.editing
        if index < 0:
            return
        row = self.rows.row_rect(index)
        box = self.rows.text_rect(row, hover=True).toRect()
        if box.bottom() < 0 or box.top() > self.rows.height():
            self._stop_edit()
            return
        box.translate(self.rows.x(), self.rows.y())
        box.adjust(-EDIT_NUDGE, 0, 0, 0)
        self.editor.setGeometry(box)
        self.editor.raise_()

    # --- поведение --------------------------------------------------------- #

    def _refresh(self):
        has_items = bool(self.store.items)
        self.empty.setVisible(not has_items)
        self.rows.setVisible(has_items)
        # Сколько задач — цифрой в правом верхнем углу, как в cyclop.
        self.count.set_text(str(len(self.store.items)) if has_items else "")
        self.rows.refresh()

    def _create(self):
        # Набранное в открытой строке сохраняем до вставки новой: create()
        # кладёт задачу в начало списка, номера съезжают, и правка ушла бы
        # в никуда вместе со старым номером.
        self._commit()
        item = self.store.create()
        self.rows.refresh()
        self._start_edit(self.store.index_of(item["id"]))

    def _edit(self, index):
        self._start_edit(index)

    def _start_edit(self, index):
        if not 0 <= index < len(self.store.items):
            return
        # Дальше работаем по id, а не по номеру строки: сохранение предыдущей
        # правки меняет список, и номер, взятый из клика, к этому моменту может
        # указывать уже мимо — раньше на этом вылетал IndexError.
        task_id = self.store.items[index].get("id", "")
        if not task_id or task_id == self._editing_id:
            return
        self._commit()
        index = self.store.index_of(task_id)
        if index < 0:
            return
        item = self.store.items[index]
        self._editing_id = task_id
        self.rows.editing = index
        self.rows.scroll_to(index)
        self.editor.setText(item.get("text") or "")
        self._place_editor()
        self.editor.show()
        self.editor.setFocus()
        self.editor.selectAll()
        self.rows.update()

    def _commit(self):
        if not self._editing_id:
            return
        # Сохраняем и закрываем поле до записи: set_text шлёт changed, и
        # обработчик перерисовки не должен застать нас на полпути.
        task_id, text = self._editing_id, self.editor.text()
        self._stop_edit()
        self.store.set_text(task_id, text)
        self._refresh()

    def _stop_edit(self):
        self._editing_id = ""
        self.rows.editing = -1
        self.editor.hide()
        self.rows.update()

    def _toggle(self, index):
        if index == self.rows.editing:
            self._commit()
        self.store.toggle(index)
        self.rows.update()

    def _remove(self, index):
        if index == self.rows.editing:
            self._stop_edit()
        elif self.rows.editing > index:
            self.rows.editing -= 1
            self._place_editor()
        self.store.remove(index)
        self._refresh()

    def keyPressEvent(self, event):
        if event.key() != Qt.Key_Escape or not self._editing_id:
            return
        task_id = self._editing_id
        self._stop_edit()
        index = self.store.index_of(task_id)
        # Escape отменяет набор. Строку, которую только что завели и не успели
        # назвать, отменять не от чего — она уходит вместе с набором.
        if index >= 0 and not (self.store.items[index].get("text") or "").strip():
            self.store.remove(index)
        self._refresh()

    # --- жизненный цикл ---------------------------------------------------- #

    def retranslate(self):
        self.editor.setPlaceholderText(i18n.t("todo.placeholder"))
        self.new_button.update()
        self.rows.update()
        self.empty.update()

    def on_hide(self):
        # Пустые строки убираем только здесь: пока вкладка открыта, их может
        # быть сколько угодно — «Новую задачу» жмут и по нескольку раз подряд.
        self._commit()
        self.store.prune_empty()
        self._refresh()
