"""
Три полоски рядом с названием источника звука.

Волна идёт справа налево: правая полоска поднимается первой, средняя с
задержкой, левая последней; дойдя до максимума, правая начинает опускаться, и
та же очередь повторяется вниз. На паузе полоски плавно оседают почти в ноль и
анимация снимается с общих часов.
"""

import math
import time

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from ...core.scale import sf
from .. import theme
from ..anim import Ticker

BAR_W    = 2      # ширина полоски, px макета
BAR_GAP  = 2      # просвет между полосками
BAR_MIN  = 1      # высота «почти не видно»
BARS     = (3, 5, 7)   # максимум для левой, средней, правой

PERIOD   = 1.15   # секунд на полный цикл вверх-вниз
LAG      = 0.13   # задержка соседней полоски, доля периода
FADE     = 4.0    # скорость затухания на паузе, 1/с


class Equalizer(QWidget):
    def __init__(self, parent=None, role="text_secondary"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._role = role
        self._playing = False
        self._level = 0.0          # общая амплитуда 0..1
        self._t0 = time.monotonic()
        self._ticker = Ticker(self._tick)

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
        self._sync()

    def _sync(self):
        need = self.isVisible() and (self._playing or self._level > 0.01)
        if need:
            self._ticker.start()
        else:
            self._ticker.stop()

    def showEvent(self, event):
        super().showEvent(event)
        self._sync()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._ticker.stop()

    def _tick(self, dt):
        target = 1.0 if self._playing else 0.0
        self._level += (target - self._level) * min(1.0, FADE * dt)
        if not self._playing and self._level < 0.01:
            self._level = 0.0
            self._ticker.stop()
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
            p.drawRoundedRect(QRectF(x, bottom - h, bar_w, h),
                              bar_w / 2, bar_w / 2)
