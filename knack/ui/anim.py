"""
Общие часы анимаций.

QPropertyAnimation крутится от единого таймера Qt с шагом ~16.7 мс — это 60 к/с
независимо от монитора, и на 180 Гц выезд панели выглядит рвано. Здесь свой
таймер: частота берётся от частоты обновления экрана (или из настроек) и общая
на все анимации, поэтому сколько бы ни было живых твинов, тикает один таймер.

Значения считаются от реального прошедшего времени, а не от числа кадров: если
система придержала таймер, анимация не растянется, а просто перескочит.
"""

import ctypes
import time

from PySide6.QtCore import QEasingCurve, QObject, QPointF, Qt, QTimer
from PySide6.QtGui import QGuiApplication

# --- кривые ------------------------------------------------------------- #
# Встроенные кривые Qt слишком вялые для интерфейса. Берём те же значения,
# что и в вебе: сильный ease-out на появление и уход, ease-in-out на
# перемещение внутри экрана, отдельная кривая для выезжающих панелей.
#
# ease-in не используем нигде: он начинается медленно и придерживает ровно
# тот момент, ради которого человек и смотрит на экран.
def _bezier(x1, y1, x2, y2):
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(x1, y1), QPointF(x2, y2),
                                QPointF(1.0, 1.0))
    return curve


EASE_OUT = _bezier(0.23, 1.0, 0.32, 1.0)
EASE_IN_OUT = _bezier(0.77, 0.0, 0.175, 1.0)
EASE_DRAWER = _bezier(0.32, 0.72, 0.0, 1.0)

# --- длительности ------------------------------------------------------- #
# Весь интерфейс укладывается в 300 мс; числа держим здесь, чтобы они не
# расползались по файлам поодиночке.
PRESS = 0.12      # отклик на нажатие
FAST = 0.16       # наведение, переключатели, уход мелких элементов
BASE = 0.22       # обычное появление и возврат
DRAWER = 0.26     # выезд панели и карточек

FPS_MIN = 60
FPS_MAX = 240
FPS_AUTO = 0

_fps = FPS_AUTO
_resolved_fps = 60.0


# --- системная настройка анимаций --------------------------------------- #
SPI_GETCLIENTAREAANIMATION = 0x1042
_reduced = None


def refresh_reduced_motion():
    """
    Спрашивает Windows, показывать ли анимацию.

    Это галочка «Показывать анимацию в Windows» в специальных
    возможностях. Выключена — значит человек просил меньше движения, и
    спорить с системной настройкой ради красоты не стоит.
    """
    global _reduced
    value = ctypes.c_int(1)
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(value), 0)
        _reduced = bool(ok) and value.value == 0
    except Exception:
        _reduced = False
    return _reduced


def reduced_motion():
    """Движение просили убрать? Ответ кешируем: вызов не бесплатный."""
    if _reduced is None:
        refresh_reduced_motion()
    return _reduced


def motion(seconds):
    """
    Длительность для движения: при выключенной анимации — ноль.

    Прозрачность и цвет оставляем как есть: убирать надо перемещение, а не
    понимание того, что на экране что-то изменилось.
    """
    return 0.0 if reduced_motion() else seconds


def screen_fps(screen=None):
    """Частота обновления экрана, к которой стоит привязать анимации."""
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    rate = float(screen.refreshRate()) if screen else 0.0
    if rate < 1:
        rate = 60.0
    return max(FPS_MIN, min(FPS_MAX, rate))


def set_fps(value, screen=None):
    """value=0 — брать частоту экрана; иначе фиксированное значение из настроек."""
    global _fps, _resolved_fps
    _fps = value or FPS_AUTO
    _resolved_fps = screen_fps(screen) if not value else max(FPS_MIN, min(FPS_MAX, value))
    _clock().retune(_resolved_fps)
    return _resolved_fps


def fps():
    return _resolved_fps


class _Clock(QObject):
    def __init__(self):
        super().__init__()
        self._tweens = []
        self._last = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self.retune(_resolved_fps)

    def retune(self, value):
        self._timer.setInterval(max(1, int(round(1000.0 / value))))

    def add(self, tween):
        if tween not in self._tweens:
            self._tweens.append(tween)
        if not self._timer.isActive():
            self._last = time.monotonic()
            self._timer.start()

    def remove(self, tween):
        if tween in self._tweens:
            self._tweens.remove(tween)
        if not self._tweens:
            self._timer.stop()

    def _tick(self):
        now = time.monotonic()
        dt = now - self._last
        self._last = now
        for tween in list(self._tweens):
            tween.advance(dt)


_instance = None


def _clock():
    global _instance
    if _instance is None:
        _instance = _Clock()
    return _instance


class Tween:
    """
    Плавный переход одного числа.

    on_update(value) зовётся на каждом тике, on_done() — один раз в конце.
    Повторный target() во время хода перехватывает движение с текущей точки,
    поэтому наведение и увод мыши не дерутся за одно и то же значение.
    """

    def __init__(self, on_update, value=0.0, duration=0.18,
                 curve=QEasingCurve.OutCubic, on_done=None):
        self.on_update = on_update
        self.on_done = on_done
        self.value = float(value)
        self._from = self.value
        self._to = self.value
        self._t = 0.0
        self._duration = duration
        self._curve = QEasingCurve(curve)
        self._running = False

    def target(self, value, duration=None, curve=None):
        value = float(value)
        if duration is not None:
            self._duration = duration
            if duration <= 0:
                # Нулевая длительность приходит от motion(), когда система
                # просит убрать движение: ставим значение сразу, а не гоняем
                # твин ради одного кадра.
                self.set(value)
                return
        if curve is not None:
            self._curve = QEasingCurve(curve)
        if abs(value - self.value) < 1e-4:
            self.set(value)
            return
        self._from = self.value
        self._to = value
        self._t = 0.0
        if not self._running:
            self._running = True
            _clock().add(self)

    def set(self, value):
        """Поставить значение мгновенно, без анимации."""
        self.stop()
        self.value = self._from = self._to = float(value)
        self.on_update(self.value)

    def stop(self):
        if self._running:
            self._running = False
            _clock().remove(self)

    def is_running(self):
        return self._running

    def advance(self, dt):
        self._t += dt
        if self._duration <= 0 or self._t >= self._duration:
            self.value = self._to
            self.stop()
            self.on_update(self.value)
            if self.on_done:
                self.on_done()
            return
        k = self._curve.valueForProgress(self._t / self._duration)
        self.value = self._from + (self._to - self._from) * k
        self.on_update(self.value)


class Ticker:
    """Повторяющийся вызов на общих часах — для эквалайзера и позиции трека."""

    def __init__(self, on_tick):
        self.on_tick = on_tick
        self._running = False

    def start(self):
        if not self._running:
            self._running = True
            _clock().add(self)

    def stop(self):
        if self._running:
            self._running = False
            _clock().remove(self)

    def is_running(self):
        return self._running

    def advance(self, dt):
        self.on_tick(dt)
