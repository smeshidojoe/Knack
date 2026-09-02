"""
Карточка обновления поверх панели.

Пока идёт загрузка новой версии, панель нельзя ни закрыть, ни потыкать: сейчас
она подменит собственный exe и перезапустится, и незаконченное действие в другой
вкладке всё равно пропадёт. Поэтому содержимое затемняется, поверх выезжает
карточка с полосой прогресса, а клики до вкладок не доходят.

Та же карточка спрашивает про найденное обновление: заголовок и две кнопки.
В этом виде панель не блокируется — вопрос можно и переждать.

Сделано по образцу такого же окна в Snatchr.
"""

from PySide6.QtCore import QEasingCurve, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

from ..core import fonts, i18n
from ..core.constants import PANEL_RADIUS
from ..core.scale import s, sf
from . import theme
from .anim import Tween
from .widgets.controls import TextButton

DIM_ALPHA = 0.72

CARD_W, CARD_H, CARD_R = 260, 78, 12
TITLE_PX, PERCENT_PX = 11, 9
BAR_W, BAR_H, BAR_R = 212, 4, 2
TITLE_TOP, BAR_TOP = 18, 46
RISE = 22          # на сколько карточка выезжает снизу

BTN_TOP, BTN_H, BTN_GAP = 44, 22, 8      # кнопки в режиме вопроса


class UpdateOverlay(QWidget):
    """accepted — согласились ставить, dismissed — «позже»."""

    accepted = Signal()
    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self._title = ""
        self._fraction = 0.0
        self._asking = False
        self._appear = Tween(lambda _v: self.update(), value=0.0, duration=0.26,
                             on_done=self._on_appeared)

        self.yes = TextButton(self, i18n.t("update.now"))
        self.yes.clicked.connect(self._on_yes)
        self.later = TextButton(self, i18n.t("update.later"), flat=True)
        self.later.clicked.connect(self._on_later)
        for button in (self.yes, self.later):
            button.hide()
        self.hide()

    # --- данные ----------------------------------------------------------- #

    def blocking(self):
        """Идёт установка: панель нельзя ни закрыть, ни трогать."""
        return self.isVisible() and not self._asking

    def asking(self):
        return self.isVisible() and self._asking

    def ask(self, title):
        """Вопрос про найденное обновление: две кнопки вместо полосы."""
        self._title = title or ""
        self._asking = True
        self.yes.set_label(i18n.t("update.now"))
        self.later.set_label(i18n.t("update.later"))
        self._layout_buttons()
        # Кнопки покажем, когда карточка доедет: пока она выплывает снизу,
        # висящие в воздухе кнопки выглядели бы отдельными от неё.
        self.show()
        self.raise_()
        self._appear.set(0.0)
        self._appear.target(1.0, 0.26, QEasingCurve.OutCubic)

    def _on_appeared(self):
        if not self._asking or not self.isVisible():
            return
        self._layout_buttons()
        for button in (self.yes, self.later):
            button.show()
            button.raise_()

    def _on_yes(self):
        self._hide_buttons()
        self.accepted.emit()

    def _on_later(self):
        self.finish()
        self.dismissed.emit()

    def _hide_buttons(self):
        self._asking = False
        for button in (self.yes, self.later):
            button.hide()

    def _card_rect(self):
        card_w, card_h = s(CARD_W), s(CARD_H)
        left = (self.width() - card_w) / 2
        top = ((self.height() - card_h) / 2
               + s(RISE) * (1.0 - self._appear.value))
        return QRectF(left, top, card_w, card_h)

    def _layout_buttons(self):
        card = self._card_rect()
        widths = [max(s(64), button.width_hint()) for button in
                  (self.yes, self.later)]
        total = sum(widths) + s(BTN_GAP)
        x = card.left() + (card.width() - total) / 2
        y = card.top() + s(BTN_TOP)
        for button, width in zip((self.yes, self.later), widths):
            button.setGeometry(int(x), int(y), int(width), s(BTN_H))
            x += width + s(BTN_GAP)

    def start(self, title):
        self._title = title or ""
        self._fraction = 0.0
        self._hide_buttons()
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
        self._hide_buttons()
        self._appear.set(0.0)
        self.hide()

    def retranslate(self):
        self.yes.set_label(i18n.t("update.now"))
        self.later.set_label(i18n.t("update.later"))
        if self._asking:
            self._layout_buttons()

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

        card = self._card_rect()
        left, top = card.left(), card.top()
        card_w = card.width()
        p.setOpacity(progress)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface_alt"))
        p.drawRoundedRect(card, sf(CARD_R), sf(CARD_R))

        p.setFont(fonts.font(s(TITLE_PX), "Medium"))
        p.setPen(theme.color("text_bright"))
        p.drawText(QRectF(left, top + s(TITLE_TOP), card_w, s(16)),
                   int(Qt.AlignHCenter | Qt.AlignVCenter), self._title)

        if self._asking:
            # Кнопки — обычные виджеты поверх карточки, их двигаем следом за
            # ней: пока она выезжает, координаты меняются каждый кадр.
            self._layout_buttons()
            p.setOpacity(1.0)
            return

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
