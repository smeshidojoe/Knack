"""
Вкладка «Заметки».

Слева кнопка «Новая заметка» и список, справа поле текста. Заголовок строки —
первая непустая строка заметки; отдельного поля названия нет. Крестик появляется
при наведении на строку.

Пустые заметки убираются при уходе с вкладки: иначе список зарастает нажатиями
на «Новую заметку».
"""

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ...core import fonts, i18n, icons
from ...core.scale import s, sf
from .. import theme
from ..widgets.field import restyle, text_edit
from ..widgets.listview import ListView
from ..widgets.text import Text
from .base import Page

NEW_X, NEW_Y, NEW_W, NEW_H, NEW_R = 55, 31, 156, 22, 7
NEW_PLUS_PX, NEW_GAP, NEW_TEXT_PX = 7, 8, 10

ROW_Y, ROW_H, ROW_STEP, ROW_R = 56, 24, 27, 7
ROW_TEXT_X, ROW_TEXT_PX = 7, 10
LIST_BOTTOM = 179

EDIT_X, EDIT_Y, EDIT_W, EDIT_H, EDIT_R = 221, 31, 297, 146, 9
EDIT_PAD_X, EDIT_PAD_Y, EDIT_PX = 9, 10, 11

COUNT_R, COUNT_Y, COUNT_H, COUNT_PX = 558, 9, 11, 9    # счётчик в правом углу

SAVE_DELAY_MS = 400


class _NewButton(QWidget):
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

        label = i18n.t("notes.new")
        p.setFont(self._font)
        metrics = QFontMetrics(self._font)
        text_w = metrics.horizontalAdvance(label)
        glyph = s(NEW_PLUS_PX)
        total = glyph + s(NEW_GAP) + text_w
        x = (self.width() - total) / 2

        role = "text_bright" if self._hover else "text_button"
        pm = icons.pixmap("plus", glyph, theme.color(role))
        p.drawPixmap(int(x), (self.height() - glyph) // 2, pm)
        p.setPen(theme.color(role))
        p.drawText(QRectF(x + glyph + s(NEW_GAP), 0, text_w, self.height()),
                   int(Qt.AlignLeft | Qt.AlignVCenter), label)


class _NoteList(ListView):
    def __init__(self, store, parent=None):
        super().__init__(parent, row_height=ROW_H, row_spacing=ROW_STEP - ROW_H,
                         has_close=True, close_inset=6)
        self.store = store
        self.selected = -1
        self._font = fonts.font(s(ROW_TEXT_PX), "Medium")

    def restyle(self):
        self._font = fonts.font(s(ROW_TEXT_PX), "Medium")
        self.row_height = ROW_H
        self.row_spacing = ROW_STEP - ROW_H

    def count(self):
        return len(self.store.items)

    def paint_row(self, painter, index, rect, hover):
        item = self.store.items[index]
        active = index == self.selected
        r = sf(ROW_R)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.color("surface_hover" if (hover or active)
                                     else "surface_alt"))
        painter.drawRoundedRect(QRectF(rect), r, r)

        title = self.store.title_of(item) or i18n.t("notes.untitled")
        painter.setFont(self._font)
        painter.setPen(theme.color("text_bright"))
        left = rect.left() + s(ROW_TEXT_X)
        right = rect.right() - (s(22) if hover else s(8))
        box = QRectF(left, rect.top(), max(0, right - left), rect.height())
        metrics = QFontMetrics(self._font)
        painter.drawText(box, int(Qt.AlignLeft | Qt.AlignVCenter),
                         metrics.elidedText(title, Qt.ElideRight, int(box.width())))

        if hover:
            self.paint_close(painter, self.close_rect(rect), self._hover_close)


class _Editor(QWidget):
    """Фон поля редактирования; сам ввод — QPlainTextEdit поверх."""

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface"))
        r = sf(EDIT_R)
        p.drawRoundedRect(QRectF(self.rect()), r, r)


class NotesPage(Page):
    key = "notes"
    wants_keyboard = True

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._current = ""

        self.new_button = _NewButton(self)
        self.new_button.clicked.connect(self._create)

        self.list = _NoteList(store, self)
        self.list.activated.connect(self._select)
        self.list.close_requested.connect(self._remove)

        self.count = Text(self, role="text_muted", align=Qt.AlignRight)

        self.frame = _Editor(self)
        self.editor = text_edit(self, EDIT_PX, "Medium",
                                i18n.t("notes.placeholder"))
        self.editor.textChanged.connect(self._schedule_save)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(SAVE_DELAY_MS)
        self._save_timer.timeout.connect(self._save)

        store.changed.connect(self._on_changed)
        self._select_first()
        self._update_count()

    # --- геометрия -------------------------------------------------------- #

    def relayout(self):
        self.new_button.restyle()
        self.new_button.setGeometry(s(NEW_X), s(NEW_Y), s(NEW_W), s(NEW_H))

        self.list.restyle()
        self.list.setGeometry(s(NEW_X), s(ROW_Y), s(NEW_W),
                              s(LIST_BOTTOM) - s(ROW_Y))

        self.frame.setGeometry(s(EDIT_X), s(EDIT_Y), s(EDIT_W), s(EDIT_H))
        restyle(self.editor, EDIT_PX)
        self.editor.setGeometry(s(EDIT_X) + s(EDIT_PAD_X), s(EDIT_Y) + s(EDIT_PAD_Y),
                                s(EDIT_W) - s(EDIT_PAD_X) * 2,
                                s(EDIT_H) - s(EDIT_PAD_Y) * 2)
        self.editor.raise_()

        self.count.set_font_px(s(COUNT_PX), "Bold")
        self.count.setGeometry(s(COUNT_R) - s(60), s(COUNT_Y), s(60), s(COUNT_H))
        self.list.refresh()

    # --- поведение --------------------------------------------------------- #

    def _on_changed(self):
        self.list.update()
        self._update_count()

    def _update_count(self):
        """Сколько заметок — цифрой в правом верхнем углу, как в cyclop."""
        count = len(self.store.items)
        self.count.set_text(str(count) if count else "")

    def _select_first(self):
        if self.store.items:
            self._select(0)
        else:
            self._current = ""
            self.list.selected = -1
            self._set_editor_text("")
            self.editor.setEnabled(False)

    def _set_editor_text(self, text):
        blocked = self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(blocked)

    def _create(self):
        # Пустые заметки чистим только при уходе с вкладки: иначе повторное
        # нажатие «Новой заметки» стирало бы предыдущую пустую вместо того,
        # чтобы добавить ещё одну строку.
        item = self.store.create()
        self._current = item["id"]
        self.list.selected = self.store.index_of(self._current)
        self.editor.setEnabled(True)
        self._set_editor_text("")
        self.list.scroll_to(max(0, self.list.selected))
        self.list.update()
        self.editor.setFocus()

    def _select(self, index):
        if not 0 <= index < len(self.store.items):
            return
        self._save()
        item = self.store.items[index]
        self._current = item.get("id", "")
        self.list.selected = index
        self.editor.setEnabled(True)
        self._set_editor_text(item.get("text") or "")
        self.list.update()

    def _remove(self, index):
        if not 0 <= index < len(self.store.items):
            return
        note_id = self.store.items[index].get("id")
        self.store.remove(note_id)
        if note_id == self._current:
            self._select_first()
        else:
            self.list.selected = self.store.index_of(self._current)
        self.list.refresh()

    def _schedule_save(self):
        self._save_timer.start()
        # Заголовок в списке — первая строка текста, поэтому список обновляем
        # сразу, не дожидаясь записи на диск.
        self.list.update()

    def _save(self):
        self._save_timer.stop()
        if self._current:
            self.store.set_text(self._current, self.editor.toPlainText())

    # --- жизненный цикл ---------------------------------------------------- #

    def retranslate(self):
        self.editor.setPlaceholderText(i18n.t("notes.placeholder"))
        self.new_button.update()
        self.list.update()

    def on_show(self):
        self.list.selected = self.store.index_of(self._current)
        self.list.update()

    def on_hide(self):
        self._save()
        self.store.prune_empty(keep_id=self._current)
        self.list.selected = self.store.index_of(self._current)
        self.list.refresh()
