"""
Контролы для вкладки настроек.

Штатные QCheckBox, QComboBox и QSlider тянут за собой системное оформление и
правятся только длинными таблицами стилей; здесь их пять штук, и нарисовать их
теми же цветами, что и остальную панель, короче и предсказуемее.

Все контролы работают в координатах макета: размеры приходят через scale.s().
"""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ...core import fonts
from ...core.scale import s, sf
from .. import theme
from ..anim import Tween

TEXT_PX = 9


class _Base(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._hover = False
        self._font = fonts.font(s(TEXT_PX), "Semibold")

    def restyle(self):
        self._font = fonts.font(s(TEXT_PX), "Semibold")
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)


class Toggle(_Base):
    """Переключатель «включено / выключено»."""

    toggled = Signal(bool)

    W, H = 30, 16
    KNOB = 12

    def __init__(self, parent=None, checked=False):
        super().__init__(parent)
        self._checked = bool(checked)
        self._pos = Tween(lambda _v: self.update(),
                          value=1.0 if self._checked else 0.0, duration=0.16)

    def is_checked(self):
        return self._checked

    def set_checked(self, value, animate=False):
        value = bool(value)
        if value == self._checked:
            return
        self._checked = value
        if animate:
            self._pos.target(1.0 if value else 0.0)
        else:
            self._pos.set(1.0 if value else 0.0)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self.set_checked(not self._checked, animate=True)
        self.toggled.emit(self._checked)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)

        track = QRectF(0, (self.height() - s(self.H)) / 2, s(self.W), s(self.H))
        radius = track.height() / 2
        p.setBrush(theme.color("text_bright" if self._checked
                               else ("surface_hover" if self._hover else "surface_alt")))
        p.drawRoundedRect(track, radius, radius)

        knob = sf(self.KNOB)
        margin = (track.height() - knob) / 2
        travel = track.width() - knob - margin * 2
        x = track.left() + margin + travel * self._pos.value
        p.setBrush(theme.color("bg" if self._checked else "text_button"))
        p.drawEllipse(QRectF(x, track.top() + margin, knob, knob))


class Segmented(_Base):
    """Ряд взаимоисключающих вариантов: язык, монитор, режим скрытия."""

    picked = Signal(str)

    H, RADIUS, PAD = 20, 7, 9

    def __init__(self, parent=None, options=(), value=""):
        super().__init__(parent)
        self.options = list(options)      # [(key, подпись), ...]
        self.value = value
        self._hover_index = -1

    def set_options(self, options, value=None):
        self.options = list(options)
        if value is not None:
            self.value = value
        self.update()

    def set_value(self, value):
        if value != self.value:
            self.value = value
            self.update()

    def width_hint(self):
        metrics = QFontMetrics(self._font)
        return sum(metrics.horizontalAdvance(label) + s(self.PAD) * 2
                   for _key, label in self.options)

    def _rects(self):
        metrics = QFontMetrics(self._font)
        x = 0.0
        out = []
        for key, label in self.options:
            w = metrics.horizontalAdvance(label) + s(self.PAD) * 2
            out.append((key, label, QRectF(x, 0, w, self.height())))
            x += w
        return out

    def mouseMoveEvent(self, event):
        point = event.position()
        index = -1
        for i, (_key, _label, rect) in enumerate(self._rects()):
            if rect.contains(point):
                index = i
                break
        if index != self._hover_index:
            self._hover_index = index
            self.update()

    def leaveEvent(self, event):
        self._hover_index = -1
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        for key, _label, rect in self._rects():
            if rect.contains(event.position()):
                if key != self.value:
                    self.value = key
                    self.update()
                    self.picked.emit(key)
                return

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self._font)

        radius = sf(self.RADIUS)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface"))
        p.drawRoundedRect(QRectF(self.rect()), radius, radius)

        for index, (key, label, rect) in enumerate(self._rects()):
            active = key == self.value
            if active:
                p.setBrush(theme.color("surface_hover"))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(rect.adjusted(sf(2), sf(2), -sf(2), -sf(2)),
                                  radius - sf(2), radius - sf(2))
            if active:
                role = "text_bright"
            elif index == self._hover_index:
                role = "text_secondary"
            else:
                role = "text_button"
            p.setPen(theme.color(role))
            p.drawText(rect, int(Qt.AlignCenter), label)


class Slider(_Base):
    """Ползунок величины: размер панели."""

    changed = Signal(float)

    H, BAR_H, KNOB = 16, 4, 6

    def __init__(self, parent=None, minimum=0.7, maximum=1.6, value=1.0, step=0.05):
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.value = value
        self._drag = False

    def set_value(self, value):
        value = max(self.minimum, min(self.maximum, float(value)))
        if abs(value - self.value) > 1e-6:
            self.value = value
            self.update()

    def _fraction(self):
        span = self.maximum - self.minimum
        return (self.value - self.minimum) / span if span else 0.0

    def _value_at(self, x):
        span = self.maximum - self.minimum
        frac = max(0.0, min(1.0, x / max(1, self.width())))
        raw = self.minimum + frac * span
        return round(raw / self.step) * self.step

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self._drag = True
        self.set_value(self._value_at(event.position().x()))
        self.changed.emit(self.value)

    def mouseMoveEvent(self, event):
        if self._drag:
            before = self.value
            self.set_value(self._value_at(event.position().x()))
            if abs(before - self.value) > 1e-6:
                self.changed.emit(self.value)

    def mouseReleaseEvent(self, event):
        self._drag = False

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)

        h = sf(self.BAR_H)
        y = (self.height() - h) / 2
        r = h / 2
        p.setBrush(theme.color("track"))
        p.drawRoundedRect(QRectF(0, y, self.width(), h), r, r)

        knob = sf(self.KNOB)
        fill = max(h, self.width() * self._fraction())
        p.setBrush(theme.color("track_fill"))
        p.drawRoundedRect(QRectF(0, y, fill, h), r, r)
        cx = min(max(self.width() * self._fraction(), knob), self.width() - knob)
        p.drawEllipse(QRectF(cx - knob, self.height() / 2 - knob, knob * 2, knob * 2))


class Stepper(_Base):
    """Целое число с кнопками «минус» и «плюс»: лимиты и задержки."""

    changed = Signal(int)

    H, RADIUS, SIDE = 20, 7, 22

    def __init__(self, parent=None, minimum=0, maximum=100, value=0, step=1,
                 suffix=""):
        super().__init__(parent)
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.suffix = suffix
        self.value = value
        self._hot = 0        # -1 минус, +1 плюс

    def set_value(self, value):
        value = max(self.minimum, min(self.maximum, int(value)))
        if value != self.value:
            self.value = value
            self.update()

    def text(self):
        return "%d%s" % (self.value, self.suffix)

    def width_hint(self):
        metrics = QFontMetrics(self._font)
        return s(self.SIDE) * 2 + metrics.horizontalAdvance(self.text()) + s(16)

    def _zone(self, x):
        if x < s(self.SIDE):
            return -1
        if x > self.width() - s(self.SIDE):
            return 1
        return 0

    def mouseMoveEvent(self, event):
        zone = self._zone(event.position().x())
        if zone != self._hot:
            self._hot = zone
            self.update()

    def leaveEvent(self, event):
        self._hot = 0
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        zone = self._zone(event.position().x())
        if zone:
            before = self.value
            self.set_value(self.value + self.step * zone)
            if self.value != before:
                self.changed.emit(self.value)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self._font)
        radius = sf(self.RADIUS)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface"))
        p.drawRoundedRect(QRectF(self.rect()), radius, radius)

        side = s(self.SIDE)
        for sign, rect in ((-1, QRectF(0, 0, side, self.height())),
                           (1, QRectF(self.width() - side, 0, side, self.height()))):
            enabled = (self.value > self.minimum) if sign < 0 else (self.value < self.maximum)
            if not enabled:
                role = "text_muted"
            elif self._hot == sign:
                role = "text_bright"
            else:
                role = "text_button"
            p.setPen(theme.color(role))
            p.drawText(rect, int(Qt.AlignCenter), "−" if sign < 0 else "+")

        p.setPen(theme.color("text_bright"))
        p.drawText(QRectF(side, 0, self.width() - side * 2, self.height()),
                   int(Qt.AlignCenter), self.text())


class HotkeyField(_Base):
    """Поле сочетания: клик, затем нажать нужные клавиши."""

    changed = Signal(str)
    capturing = Signal(bool)

    H, RADIUS, PAD = 20, 7, 10

    _MODS = ((Qt.ControlModifier, "ctrl"), (Qt.AltModifier, "alt"),
             (Qt.ShiftModifier, "shift"), (Qt.MetaModifier, "win"))
    _SKIP = (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta,
             Qt.Key_AltGr, Qt.Key_unknown)

    def __init__(self, parent=None, value=""):
        super().__init__(parent)
        self.value = value
        self._active = False
        self.setFocusPolicy(Qt.StrongFocus)

    def set_value(self, value):
        self.value = value
        self.update()

    def width_hint(self):
        metrics = QFontMetrics(self._font)
        return metrics.horizontalAdvance(self.text()) + s(self.PAD) * 2

    def text(self):
        if self._active:
            return "…"
        return "+".join(part.upper() for part in self.value.split("+"))

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        self._start()

    def _start(self):
        if self._active:
            return
        self._active = True
        self.setFocus(Qt.MouseFocusReason)
        self.grabKeyboard()
        self.capturing.emit(True)
        self.update()

    def _stop(self):
        if not self._active:
            return
        self._active = False
        self.releaseKeyboard()
        self.capturing.emit(False)
        self.update()

    def focusOutEvent(self, event):
        self._stop()
        super().focusOutEvent(event)

    def keyPressEvent(self, event):
        if not self._active:
            return
        if event.key() == Qt.Key_Escape:
            self._stop()
            return
        if event.key() in self._SKIP:
            return
        parts = [name for flag, name in self._MODS if event.modifiers() & flag]
        if not parts:
            return          # без модификатора сочетание перехватило бы обычную клавишу
        text = event.text().strip().lower()
        key = event.key()
        if Qt.Key_F1 <= key <= Qt.Key_F24:
            parts.append("f%d" % (key - Qt.Key_F1 + 1))
        elif text and text.isprintable() and len(text) == 1 and text.isalnum():
            parts.append(text)
        elif Qt.Key_A <= key <= Qt.Key_Z:
            parts.append(chr(key).lower())
        elif Qt.Key_0 <= key <= Qt.Key_9:
            parts.append(chr(key))
        else:
            return
        self.value = "+".join(parts)
        self._stop()
        self.changed.emit(self.value)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self._font)
        radius = sf(self.RADIUS)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface_hover" if (self._hover or self._active)
                               else "surface"))
        p.drawRoundedRect(QRectF(self.rect()), radius, radius)
        p.setPen(theme.color("text_bright" if self._active else "text_button"))
        p.drawText(self.rect(), int(Qt.AlignCenter), self.text())


class TextButton(_Base):
    """Небольшая текстовая кнопка («Ок» рядом с ключом)."""

    clicked = Signal()

    H, RADIUS, PAD = 20, 7, 12

    def __init__(self, parent=None, label=""):
        super().__init__(parent)
        self.label = label

    def set_label(self, label):
        self.label = label
        self.update()

    def width_hint(self):
        return QFontMetrics(self._font).horizontalAdvance(self.label) + s(self.PAD) * 2

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.clicked.emit()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self._font)
        radius = sf(self.RADIUS)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface_hover" if self._hover else "surface"))
        p.drawRoundedRect(QRectF(self.rect()), radius, radius)
        p.setPen(theme.color("text_bright" if self._hover else "text_button"))
        p.drawText(self.rect(), int(Qt.AlignCenter), self.label)
