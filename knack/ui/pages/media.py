"""
Вкладка «Музыка».

Координаты — из макета (2560x1440), пересчёт в relayout() через scale.s().
Раскладка абсолютная: панель фиксированного размера, и раскладывать десяток
элементов вложенными layout'ами тут дороже, чем расставить их по числам из
Figma — зато каждое число в коде совпадает с числом в макете.

Позицию трека двигают общие часы, а не приход данных от службы: SMTC у части
источников обновляет таймлайн раз в несколько минут, и полоса замирала до
следующего нажатия паузы.
"""

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QWidget

from ...core import i18n
from ...core.constants import BODY_R, CONTENT_R, CONTENT_X, MEDIA_BTN_BOX
from ...core.scale import s, sf
from ..anim import Ticker
from ..widgets.artwork import Artwork
from ..widgets.buttons import IconButton
from ..widgets.equalizer import Equalizer
from ..widgets.seekbar import SeekBar
from ..widgets.text import Text
from ..widgets.volumebar import VolumeBar
from .base import Page

ART_X, ART_Y, ART_SIDE, ART_RADIUS = 54, 51, 109, 12

TITLE_Y,    TITLE_H    = 50, 17
SUBTITLE_Y, SUBTITLE_H = 69, 12

BTN_CY, BTN_HOVER, BTN_GAP = 115, 37, 51
ICON_SKIP, ICON_PLAY = 18, 15

# Треугольник Play легче своей правой части, и в общем боксе он выглядит
# сдвинутым влево относительно симметричной паузы. Смещаем оптически.
PLAY_DX = 1.0

# Громкость встала справа от кнопок: в этой строке это единственное свободное
# место, где она не спорит ни с обложкой, ни с названием трека.
VOL_X, VOL_H = 447, 20
VOL_POLL_MS = 400          # уровень могли сменить мимо нас, системным ползунком

ROW_Y, ROW_H = 149, 11
TIME_MIN_W, TIME_GAP = 21, 11

HEADER_Y, HEADER_H = 9, 11
EQ_GAP = 5


def format_time(seconds):
    if seconds is None or seconds < 0:
        seconds = 0
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, sec = divmod(rest, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, sec)
    return "%d:%02d" % (m, sec)


class _ClickArea(QWidget):
    """Прозрачная кликабельная зона поверх подписи источника."""

    clicked = Signal()
    hovered = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_Hover, True)

    def enterEvent(self, event):
        self.hovered.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hovered.emit(False)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.clicked.emit()


class MediaPage(Page):
    key = "media"

    def __init__(self, service, volume=None, parent=None):
        super().__init__(parent)
        self.service = service
        self.volume = volume
        self._art_key = None
        self._state = None
        self._ticker = Ticker(self._tick)

        self.art = Artwork(self, radius=ART_RADIUS)
        self.title_text = Text(self, role="text_primary")
        self.subtitle = Text(self, role="text_secondary")

        self.source = Text(self, role="text_secondary", align=Qt.AlignRight)
        self.equalizer = Equalizer(self, role="text_secondary")
        self.source_click = _ClickArea(self)
        self.source_click.clicked.connect(self._switch_source)
        self.source_click.hovered.connect(self._on_source_hover)
        self.source_click.hide()

        self.prev = IconButton(self, icon_name="prev", icon_px=ICON_SKIP,
                               hover_shape="circle", hover_size=(BTN_HOVER, BTN_HOVER))
        self.play = IconButton(self, icon_name="play", icon_px=ICON_PLAY,
                               hover_shape="circle", hover_size=(BTN_HOVER, BTN_HOVER),
                               icon_offset=(PLAY_DX, 0))
        self.next = IconButton(self, icon_name="next", icon_px=ICON_SKIP,
                               hover_shape="circle", hover_size=(BTN_HOVER, BTN_HOVER))

        self.volume_bar = VolumeBar(self)
        self.volume_bar.moved.connect(self._on_volume)
        self.volume_bar.mute_clicked.connect(self._on_mute)
        self._volume_timer = QTimer(self)
        self._volume_timer.setInterval(VOL_POLL_MS)
        self._volume_timer.timeout.connect(self._sync_volume)
        # Без устройства вывода регулировать нечего — полосы тогда нет вовсе.
        self.volume_bar.setVisible(bool(volume and volume.available()))

        self.time_left = Text(self, role="text_muted", align=Qt.AlignLeft)
        self.time_right = Text(self, role="text_muted", align=Qt.AlignRight)
        self.bar = SeekBar(self)

        self.prev.clicked.connect(self.service.previous)
        self.play.clicked.connect(self.service.toggle)
        self.next.clicked.connect(self.service.next)
        self.bar.seek.connect(self.service.seek)
        self.bar.scrubbing.connect(self._on_scrub)
        self.service.updated.connect(self.apply_state)

        self.apply_state(None)

    # --- геометрия ------------------------------------------------------- #

    def relayout(self):
        self.art.setGeometry(s(ART_X), s(ART_Y), s(ART_SIDE), s(ART_SIDE))

        self.title_text.set_font_px(s(14), "Bold")
        self.subtitle.set_font_px(s(10), "Medium", letter_spacing=sf(0.3))
        self.source.set_font_px(s(9), "Bold")
        self.time_left.set_font_px(s(9), "Medium")
        self.time_right.set_font_px(s(9), "Medium")

        width = s(BODY_R) - s(CONTENT_X)
        self.title_text.setGeometry(s(CONTENT_X), s(TITLE_Y), width, s(TITLE_H))
        self.subtitle.setGeometry(s(CONTENT_X), s(SUBTITLE_Y), width, s(SUBTITLE_H))

        box = s(MEDIA_BTN_BOX)
        cx = (s(CONTENT_X) + s(CONTENT_R)) // 2
        cy = s(BTN_CY)
        for btn, dx in ((self.prev, -s(BTN_GAP)), (self.play, 0),
                        (self.next, s(BTN_GAP))):
            btn.setGeometry(cx + dx - box // 2, cy - box // 2, box, box)

        self.volume_bar.setGeometry(s(VOL_X), s(BTN_CY) - s(VOL_H) // 2,
                                    s(BODY_R) - s(VOL_X), s(VOL_H))
        self._layout_header()
        self._layout_progress()

    def _layout_header(self):
        """Источник звука прижат к правому краю, эквалайзер — слева от него."""
        tw = max(self.source.text_width(), 1)
        x = s(CONTENT_R) - tw
        self.source.setGeometry(x, s(HEADER_Y), tw, s(HEADER_H))

        eq_w, eq_h = self.equalizer.base_size()
        eq_w, eq_h = s(eq_w), s(eq_h)
        eq_bottom = s(HEADER_Y) + s(HEADER_H) - s(1)
        eq_x = x - s(EQ_GAP) - eq_w
        self.equalizer.setGeometry(eq_x, eq_bottom - eq_h, eq_w, eq_h)

        pad = s(4)
        self.source_click.setGeometry(eq_x - pad, s(HEADER_Y) - pad,
                                      s(CONTENT_R) - eq_x + pad * 2,
                                      s(HEADER_H) + pad * 2)
        self.source_click.raise_()

    def _layout_progress(self):
        """Полоса ужимается под длину таймингов: у часовых треков они шире."""
        y, h = s(ROW_Y), s(ROW_H)
        lw = max(self.time_left.text_width(), s(TIME_MIN_W))
        rw = max(self.time_right.text_width(), s(TIME_MIN_W))
        gap = s(TIME_GAP)

        left = s(CONTENT_X)
        right = s(BODY_R)
        self.time_left.setGeometry(left, y, lw, h)
        self.time_right.setGeometry(right - rw, y, rw, h)

        bar_x = left + lw + gap
        bar_w = max(s(20), (right - rw - gap) - bar_x)
        self.bar.setGeometry(bar_x, y, bar_w, h)

    # --- данные ---------------------------------------------------------- #

    def apply_state(self, state):
        self._state = state
        playing = bool(state and state.playing)

        if state is None:
            self.title_text.set_text(i18n.t("media.idle"))
            self.subtitle.set_text("")
            self.source.set_text("")
            if self._art_key is not None:
                self._art_key = None
                self.art.set_image(None)
            self.bar.set_values(0, 0)
            self.time_left.set_text("")
            self.time_right.set_text("")
        else:
            self.title_text.set_text(state.title or i18n.t("media.untitled"))
            self.subtitle.set_text(state.subtitle())
            self.source.set_text(state.app_name)
            if state.art_key != self._art_key:
                self._art_key = state.art_key
                self.art.set_image(state.art)
            self.bar.set_values(state.elapsed(), state.duration)
            self.time_left.set_text(format_time(self._display_position()))
            self.time_right.set_text(format_time(state.duration))

        self.play.set_icon("pause" if playing else "play")
        self.equalizer.set_playing(playing)
        self.equalizer.setVisible(bool(state and state.app_name))

        self.prev.setEnabled(bool(state and state.can_prev))
        self.next.setEnabled(bool(state and state.can_next))
        self.play.setEnabled(state is not None)
        # Перемотку принимают не все источники: браузерные плееры часто её не
        # объявляют, и клик по полосе у них просто ничего не делает. В таком
        # случае полоса остаётся индикатором, но перестаёт ловить мышь.
        self.bar.setEnabled(bool(state and state.can_seek and state.duration > 0))

        # Переключатель источника нужен, только когда источников больше одного.
        many = self.service.source_count() > 1
        self.source_click.setVisible(many)
        self.source_click.setCursor(Qt.PointingHandCursor if many else Qt.ArrowCursor)
        self.source_click.setToolTip(i18n.t("media.source_switch") if many else "")

        self.volume_bar.setGeometry(s(VOL_X), s(BTN_CY) - s(VOL_H) // 2,
                                    s(BODY_R) - s(VOL_X), s(VOL_H))
        self._layout_header()
        self._layout_progress()
        self._sync_ticker()

    def _display_position(self):
        state = self._state
        if state is None:
            return 0.0
        if self.bar.is_scrubbing():
            return self.bar.fraction() * state.duration
        return state.elapsed()

    def _on_source_hover(self, on):
        self.source.set_role("text_primary" if on else "text_secondary")

    def _switch_source(self):
        self.service.next_source()

    def _on_scrub(self, active):
        self._sync_ticker()
        if not active:
            self._tick(0)

    # --- живая позиция ---------------------------------------------------- #

    def _sync_ticker(self):
        need = (self.isVisible() and self._state is not None
                and (self._state.playing or self.bar.is_scrubbing()))
        if need:
            self._ticker.start()
        else:
            self._ticker.stop()

    # --- громкость -------------------------------------------------------- #

    def _sync_volume(self):
        if not self.volume:
            return
        level = self.volume.level()
        if level is None:
            self.volume_bar.hide()
            return
        self.volume_bar.set_values(level, self.volume.muted())

    def _on_volume(self, value):
        if self.volume:
            self.volume.set_level(value)

    def _on_mute(self):
        if not self.volume:
            return
        self.volume.toggle_mute()
        self._sync_volume()

    def _tick(self, _dt):
        state = self._state
        if state is None:
            return
        position = self._display_position()
        self.bar.set_values(position, state.duration)
        text = format_time(position)
        if text != self.time_left.text():
            self.time_left.set_text(text)
            self._layout_progress()

    # --- жизненный цикл -------------------------------------------------- #

    def retranslate(self):
        self.apply_state(self._state)

    def on_show(self):
        self.service.set_active(True)
        self._sync_ticker()
        if self.volume_bar.isVisible():
            self._sync_volume()
            self._volume_timer.start()

    def on_hide(self):
        self.service.set_active(False)
        self._ticker.stop()
        self._volume_timer.stop()
