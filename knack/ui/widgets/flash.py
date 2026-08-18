"""
Вспышка на элементе, который только что скопировали.

Клик по строке или карточке ничего не двигает на экране: буфер меняется молча, и
без отклика непонятно, сработало ли. Поэтому элемент коротко подсвечивается и
гаснет — этого хватает, чтобы увидеть, что именно ушло в буфер.
"""

from PySide6.QtGui import QColor

from ..anim import Tween

DURATION = 0.55
PEAK_ALPHA = 0.22


class Flash:
    def __init__(self, on_update):
        self.index = -1
        self._tween = Tween(self._step, value=0.0, duration=DURATION,
                            on_done=self._finish)
        self._on_update = on_update

    def start(self, index):
        self.index = index
        self._tween.set(1.0)
        self._tween.target(0.0, DURATION)

    def alpha(self, index):
        """0..1 для конкретного элемента; 0 — вспышки нет."""
        if index != self.index or self._tween.value <= 0.001:
            return 0.0
        return self._tween.value

    def color(self, index, role_color):
        """Цвет наложения поверх элемента или None."""
        value = self.alpha(index)
        if value <= 0:
            return None
        color = QColor(role_color)
        color.setAlphaF(PEAK_ALPHA * value)
        return color

    def stop(self):
        self._tween.set(0.0)
        self.index = -1

    def _step(self, _value):
        self._on_update()

    def _finish(self):
        self.index = -1
        self._on_update()
