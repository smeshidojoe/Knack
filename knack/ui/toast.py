"""
Своя всплывающая плашка вместо системного уведомления.

Уведомления Windows показываются не всегда: «Фокусировка внимания», отключённые
уведомления приложения, полноэкранный режим — и сообщение о новой версии просто
не доходит. Поэтому рисуем свою, в теме панели.

Плашка про обновление висит, пока её не тронут: пропустить единственное
сообщение о том, что вышла новая версия, обиднее, чем увидеть его лишний раз.
Клик по ней — поставить обновление, крестик — отложить.
"""

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..core import fonts
from ..core.scale import s, sf
from . import theme
from .anim import Tween

CARD_W, CARD_H, CARD_R = 236, 58, 12
PAD_X, TITLE_Y, SUB_Y = 14, 12, 30
TITLE_PX, SUB_PX = 11, 9
CLOSE_BOX, CLOSE_INSET = 16, 7
MARGIN = 14                # отступ от края экрана
RISE = 16                  # на сколько выплывает снизу
FADE_S = 0.22


class Toast(QWidget):
    """clicked — щёлкнули по плашке, dismissed — закрыли крестиком."""

    clicked = Signal()
    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint
                         | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        self._title = ""
        self._subtitle = ""
        self._hover = False
        self._hover_close = False
        self._appear = Tween(self._on_appear, value=0.0, duration=FADE_S,
                             on_done=self._on_appear_done)
        self._life = QTimer(self)
        self._life.setSingleShot(True)
        self._life.timeout.connect(self.close_message)

    # --- показ ------------------------------------------------------------- #

    def show_message(self, title, subtitle="", timeout_ms=0):
        """timeout_ms=0 — висит, пока не тронут: так показываем новую версию."""
        self._title = title or ""
        self._subtitle = subtitle or ""
        self._life.stop()
        if timeout_ms:
            self._life.start(int(timeout_ms))
        self._place()
        self.show()
        self.raise_()
        self._appear.set(0.0)
        self._appear.target(1.0, FADE_S, QEasingCurve.OutCubic)

    def close_message(self):
        self._life.stop()
        if not self.isVisible():
            return
        self._appear.target(0.0, FADE_S)

    def _on_appear(self, _value):
        self._place()
        self.update()

    def _on_appear_done(self):
        if self._appear.value <= 0.001:
            self.hide()

    def _place(self):
        """Правый нижний угол экрана, на котором сейчас курсор."""
        screen = (QGuiApplication.screenAt(QCursor.pos())
                  or QGuiApplication.primaryScreen())
        if screen is None:
            return
        area = screen.availableGeometry()
        width, height = s(CARD_W), s(CARD_H)
        rise = int(s(RISE) * (1.0 - self._appear.value))
        self.setGeometry(area.right() - s(MARGIN) - width + 1,
                         area.bottom() - s(MARGIN) - height + 1 + rise,
                         width, height)

    # --- события ----------------------------------------------------------- #

    def _close_rect(self):
        box = s(CLOSE_BOX)
        return QRectF(self.width() - s(CLOSE_INSET) - box, s(CLOSE_INSET),
                      box, box)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = self._hover_close = False
        self.update()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        near_close = self._close_rect().contains(event.position())
        if near_close != self._hover_close:
            self._hover_close = near_close
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._close_rect().contains(event.position()):
            self.close_message()
            self.dismissed.emit()
            return
        self.close_message()
        self.clicked.emit()

    # --- отрисовка --------------------------------------------------------- #

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setOpacity(self._appear.value)

        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface_hover" if self._hover else "surface_alt"))
        p.drawRoundedRect(QRectF(self.rect()), sf(CARD_R), sf(CARD_R))

        right = self.width() - s(CLOSE_INSET) - s(CLOSE_BOX)
        title_font = fonts.font(s(TITLE_PX), "Semibold")
        p.setFont(title_font)
        p.setPen(theme.color("text_bright"))
        box = QRectF(s(PAD_X), s(TITLE_Y), right - s(PAD_X), s(14))
        metrics = QFontMetrics(title_font)
        p.drawText(box, int(Qt.AlignLeft | Qt.AlignVCenter),
                   metrics.elidedText(self._title, Qt.ElideRight, int(box.width())))

        if self._subtitle:
            sub_font = fonts.font(s(SUB_PX), "Medium")
            p.setFont(sub_font)
            p.setPen(theme.color("text_secondary"))
            box = QRectF(s(PAD_X), s(SUB_Y), self.width() - s(PAD_X) * 2, s(12))
            metrics = QFontMetrics(sub_font)
            p.drawText(box, int(Qt.AlignLeft | Qt.AlignVCenter),
                       metrics.elidedText(self._subtitle, Qt.ElideRight,
                                          int(box.width())))

        # Крестик показываем только при наведении: в покое плашка чище.
        if not self._hover:
            return
        rect = self._close_rect()
        pen = QPen(theme.color("text_bright" if self._hover_close
                               else "text_button"))
        pen.setWidthF(max(1.0, sf(1.2)))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        pad = rect.width() * 0.3
        box = rect.adjusted(pad, pad, -pad, -pad)
        p.drawLine(box.topLeft(), box.bottomRight())
        p.drawLine(box.topRight(), box.bottomLeft())
