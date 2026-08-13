"""
Три полоски рядом с названием источника звука.

Волна идёт справа налево: правая полоска поднимается первой, средняя с
задержкой, левая последней; дойдя до максимума, правая начинает опускаться, и
та же очередь повторяется вниз. На паузе полоски плавно оседают почти в ноль,
таймер останавливается.
"""

import math
import time

from PySide6.QtCore import Qt, QRectF, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from ...core.scale import sf
from .. import theme

BAR_W    = 2      # ширина полоски, px макета
BAR_GAP  = 2      # просвет между полосками
BAR_MIN  = 1      # высота «почти не видно»
BARS     = (3, 5, 7)   # максимум для левой, средней, правой

PERIOD   = 1.15   # секунд на полный цикл вверх-вниз
LAG      = 0.13   # задержка соседней полоски, доля периода
FPS      = 30


class Equalizer(QWidget):
    def __init__(self, parent=None, role="text_secondary"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._role = role
        self._playing = False
        self._level = 0.0          # общая амплитуда 0..1, плавно гасится на паузе
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(int(1000 / FPS))
        self._timer.timeout.connect(self._tick)

    def base_size(self):
        """Размер в координатах макета: 3 полоски по 2 px с просветами."""
        w = len(BARS) * BAR_W + (len(BARS) - 1) * BAR_GAP
        return w, max(BARS)

    def set_playing(self, playing):
        playing = bool(playing)
        if playing == self._playing:
            return
        self._playing = playing
        if playing:
            self._t0 = time.monotonic()
            if self.isVisible():
                self._timer.start()
        # На паузе таймер не глушим сразу: даём полоскам осесть в _tick.

    def showEvent(self, event):
        super().showEvent(event)
        if self._playing or self._level > 0.01:
            self._timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._timer.stop()

    def _tick(self):
        target = 1.0 if self._playing else 0.0
        self._level += (target - self._level) * 0.18
        if not self._playing and self._level < 0.01:
            self._level = 0.0
            self._timer.stop()
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color(self._role))

        bar_w = sf(BAR_W)
        gap = sf(BAR_GAP)
        bottom = self.height()
        phase = (time.monotonic() - self._t0) / PERIOD

        for i, peak in enumerate(BARS):
            # i = 0 — левая полоска, она отстаёт сильнее всех.
            lag = (len(BARS) - 1 - i) * LAG
            wave = 0.5 - 0.5 * math.cos(2 * math.pi * (phase - lag))
            lo = sf(BAR_MIN)
            hi = sf(peak)
            h = lo + (hi - lo) * wave * self._level
            x = i * (bar_w + gap)
            r = QRectF(x, bottom - h, bar_w, h)
            p.drawRoundedRect(r, bar_w / 2, bar_w / 2)
