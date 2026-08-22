"""
Вкладка «Переводчик».

Две одинаковые панели: слева вводят, справа читают. Язык у каждой панели свой,
подпись сверху — кнопка со списком языков.

Перевод запускается не на каждое нажатие клавиши, а через паузу после неё:
и офлайн-модель, и запрос к DeepL стоят слишком дорого, чтобы дёргать их на
каждую букву. Ответ на устаревший текст отбрасывается по номеру запроса.
"""

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ...core import fonts, i18n
from ...core.scale import s, sf
from ...services.translate import LANGUAGES, language_name, pick_direction
from .. import theme
from ..widgets.buttons import IconButton
from ..widgets.field import restyle, text_edit
from ..widgets.listview import ListView
from .base import Page

PANE_Y, PANE_W, PANE_H, PANE_R = 31, 227, 148, 8
LEFT_X, RIGHT_X = 55, 293

LABEL_X, LABEL_Y, LABEL_H, LABEL_PX = 8, 6, 11, 9
TEXT_PAD_X, TEXT_TOP, TEXT_PAD_B, TEXT_PX = 8, 23, 8, 11

DROP_X, DROP_Y, DROP_W, DROP_H, DROP_R = 63, 3, 83, 92, 4
DROP_ITEM_X, DROP_ITEM_Y = 3, 2
DROP_ITEM_W, DROP_ITEM_H, DROP_ITEM_STEP, DROP_ITEM_R = 71, 13, 14, 2
DROP_TEXT_X, DROP_TEXT_PX = 5, 9

SWAP_CX, SWAP_CY, SWAP_BOX, SWAP_HOVER, SWAP_ICON = 287.5, 105, 24, 20, 11

TYPING_DELAY_MS = 500


class _Pane(QWidget):
    """Фон панели перевода."""

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface"))
        r = sf(PANE_R)
        p.drawRoundedRect(QRectF(self.rect()), r, r)


class _LangLabel(QWidget):
    """Подпись языка, она же кнопка открытия списка."""

    def __init__(self, page, side):
        super().__init__(page)
        self.page = page
        self.side = side
        self.code = "en"
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._hover = False
        self._font = fonts.font(s(LABEL_PX), "Semibold")

    def restyle(self):
        self._font = fonts.font(s(LABEL_PX), "Semibold")

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.page.open_languages(self.side)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self._font)
        p.setPen(theme.color("text_secondary" if self._hover else "text_muted"))
        p.drawText(self.rect(), int(Qt.AlignLeft | Qt.AlignVCenter),
                   language_name(self.code))

    def width_hint(self):
        return QFontMetrics(self._font).horizontalAdvance(language_name(self.code))


class _LangList(ListView):
    def __init__(self, parent=None):
        super().__init__(parent, row_height=DROP_ITEM_H,
                         row_spacing=DROP_ITEM_STEP - DROP_ITEM_H)
        self._font = fonts.font(s(DROP_TEXT_PX), "Semibold")

    def restyle(self):
        self._font = fonts.font(s(DROP_TEXT_PX), "Semibold")
        self.row_height = DROP_ITEM_H
        self.row_spacing = DROP_ITEM_STEP - DROP_ITEM_H

    def count(self):
        return len(LANGUAGES)

    def paint_row(self, painter, index, rect, hover):
        r = sf(DROP_ITEM_R)
        painter.setPen(Qt.NoPen)
        painter.setBrush(theme.color("surface_hover" if hover else "surface"))
        painter.drawRoundedRect(QRectF(rect), r, r)
        painter.setFont(self._font)
        painter.setPen(theme.color("text_bright"))
        painter.drawText(QRectF(rect.left() + s(DROP_TEXT_X), rect.top(),
                                rect.width() - s(DROP_TEXT_X), rect.height()),
                         int(Qt.AlignLeft | Qt.AlignVCenter), LANGUAGES[index][1])


class _Dropdown(QWidget):
    """Панель со списком языков поверх поля перевода."""

    def __init__(self, page):
        super().__init__(page)
        self.list = _LangList(self)
        self.hide()

    def restyle(self):
        self.list.restyle()
        self.list.setGeometry(s(DROP_ITEM_X), s(DROP_ITEM_Y),
                              s(DROP_ITEM_W) + s(6),
                              self.height() - s(DROP_ITEM_Y) * 2)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface_alt"))
        r = sf(DROP_R)
        p.drawRoundedRect(QRectF(self.rect()), r, r)


class TranslatePage(Page):
    key = "translate"
    wants_keyboard = True

    def __init__(self, translator, settings, parent=None):
        super().__init__(parent)
        self.translator = translator
        self.settings = settings
        self._request = 0
        self._side = "left"
        self._result_text = ""        # последний удавшийся перевод, не статус

        self.left_pane = _Pane(self)
        self.right_pane = _Pane(self)

        self.left_label = _LangLabel(self, "left")
        self.right_label = _LangLabel(self, "right")
        self.left_label.code = settings.get("translate_from", "en")
        self.right_label.code = settings.get("translate_to", "ru")

        self.source = text_edit(self, TEXT_PX, "Medium",
                                i18n.t("translate.placeholder"))
        self.source.textChanged.connect(self._schedule)
        self.result = text_edit(self, TEXT_PX, "Medium", "", read_only=True)

        self.swap = IconButton(self, icon_name="swap", icon_px=SWAP_ICON,
                               hover_shape="circle",
                               hover_size=(SWAP_HOVER, SWAP_HOVER),
                               role="text_button", role_hover="text_bright")
        self.swap.clicked.connect(self.swap_languages)

        self.dropdown = _Dropdown(self)
        self.dropdown.list.activated.connect(self._pick_language)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(TYPING_DELAY_MS)
        self._timer.timeout.connect(self._translate)

        translator.done.connect(self._on_done)
        translator.failed.connect(self._on_failed)
        translator.status.connect(self._on_status)

    # --- геометрия -------------------------------------------------------- #

    def relayout(self):
        self.left_pane.setGeometry(s(LEFT_X), s(PANE_Y), s(PANE_W), s(PANE_H))
        self.right_pane.setGeometry(s(RIGHT_X), s(PANE_Y), s(PANE_W), s(PANE_H))

        for label, pane_x in ((self.left_label, LEFT_X), (self.right_label, RIGHT_X)):
            label.restyle()
            label.setGeometry(s(pane_x) + s(LABEL_X), s(PANE_Y) + s(LABEL_Y),
                              max(s(40), label.width_hint() + s(4)), s(LABEL_H))

        for field, pane_x in ((self.source, LEFT_X), (self.result, RIGHT_X)):
            restyle(field, TEXT_PX)
            field.setGeometry(s(pane_x) + s(TEXT_PAD_X), s(PANE_Y) + s(TEXT_TOP),
                              s(PANE_W) - s(TEXT_PAD_X) * 2,
                              s(PANE_H) - s(TEXT_TOP) - s(TEXT_PAD_B))

        box = s(SWAP_BOX)
        self.swap.setGeometry(s(SWAP_CX) - box // 2, s(SWAP_CY) - box // 2, box, box)
        self.swap.raise_()

        self._place_dropdown()
        self.dropdown.raise_()

    def _place_dropdown(self):
        pane_x = LEFT_X if self._side == "left" else RIGHT_X
        self.dropdown.setGeometry(s(pane_x) + s(DROP_X), s(PANE_Y) + s(DROP_Y),
                                  s(DROP_W), s(DROP_H))
        self.dropdown.restyle()

    # --- языки ------------------------------------------------------------- #

    def open_languages(self, side):
        if self.dropdown.isVisible() and self._side == side:
            self.dropdown.hide()
            return
        self._side = side
        self._place_dropdown()
        self.dropdown.show()
        self.dropdown.raise_()

    def swap_languages(self):
        """Меняет панели местами вместе с уже переведённым текстом."""
        self.left_label.code, self.right_label.code = (self.right_label.code,
                                                       self.left_label.code)
        self._store_languages()
        if self._result_text:
            self.source.blockSignals(True)
            self.source.setPlainText(self._result_text)
            self.source.blockSignals(False)
        self._result_text = ""
        self.result.setPlainText("")
        self.dropdown.hide()
        self.relayout()
        self._translate()

    def _store_languages(self):
        self.settings["translate_from"] = self.left_label.code
        self.settings["translate_to"] = self.right_label.code

    def _pick_language(self, index):
        if not 0 <= index < len(LANGUAGES):
            return
        code = LANGUAGES[index][0]
        label = self.left_label if self._side == "left" else self.right_label
        other = self.right_label if self._side == "left" else self.left_label
        if code == other.code:
            # Два одинаковых языка смысла не имеют — меняем панели местами.
            other.code = label.code
        label.code = code
        self._store_languages()
        self.dropdown.hide()
        self.relayout()
        self._translate()

    def mouseReleaseEvent(self, event):
        if self.dropdown.isVisible():
            self.dropdown.hide()

    # --- перевод ----------------------------------------------------------- #

    def _schedule(self):
        self._timer.start()

    def _autodirect(self, text):
        """Кириллица в поле с латиницей разворачивает направление сама."""
        if not self.settings.get("translate_autodetect", True):
            return
        source, target = pick_direction(text, self.left_label.code,
                                        self.right_label.code)
        if source == self.left_label.code:
            return
        self.left_label.code, self.right_label.code = source, target
        self._store_languages()
        self.relayout()

    def _translate(self):
        text = self.source.toPlainText().strip()
        if not text:
            self._result_text = ""
            self.result.setPlainText("")
            return
        self._autodirect(text)
        if not self.translator.available():
            self.result.setPlainText(i18n.t("translate.offline"))
            return
        self.result.setPlainText(i18n.t("translate.working"))
        self._request = self.translator.translate(
            text, self.left_label.code, self.right_label.code)

    def _on_done(self, request, text):
        if request == self._request:
            self._result_text = text
            self.result.setPlainText(text)

    def _on_status(self, request, key):
        if request == self._request:
            self._result_text = ""
            self.result.setPlainText(i18n.t(key))

    def _on_failed(self, request, reason):
        if request != self._request:
            return
        key = "translate.no_pack" if "no-pack" in str(reason) else "translate.offline"
        self._result_text = ""
        self.result.setPlainText(i18n.t(key))

    # --- жизненный цикл ---------------------------------------------------- #

    def retranslate(self):
        self.source.setPlaceholderText(i18n.t("translate.placeholder"))
        self.left_label.update()
        self.right_label.update()

    def on_show(self):
        self.translator.warm_up()
        self.source.setFocus()

    def on_hide(self):
        self._timer.stop()
        self.dropdown.hide()
