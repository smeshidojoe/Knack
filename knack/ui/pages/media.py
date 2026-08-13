"""
Вкладка «Музыка».

Координаты — из макета (2560x1440), пересчёт в relayout() через scale.s().
Раскладка абсолютная: панель фиксированного размера, и раскладывать девять
элементов вложенными layout'ами тут дороже, чем расставить их по числам из
Figma — зато каждое число в коде совпадает с числом в макете.
"""

from PySide6.QtCore import Qt

from ...core.constants import CONTENT_R, CONTENT_X
from ...core.scale import s, sf
from ..widgets.artwork import Artwork
from ..widgets.buttons import IconButton
from ..widgets.equalizer import Equalizer
from ..widgets.seekbar import SeekBar
from ..widgets.text import Text
from .base import Page

ART_X, ART_Y, ART_SIDE, ART_RADIUS = 54, 51, 109, 12

TITLE_Y,    TITLE_H    = 50, 17
SUBTITLE_Y, SUBTITLE_H = 69, 12

BTN_CY, BTN_BOX, BTN_GAP = 115, 37, 51
ICON_SKIP, ICON_PLAY = 18, 15

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


class MediaPage(Page):
    key = "media"
    title = "МУЗЫКА"

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self._art_key = None
        self._has_session = False

        self.art = Artwork(self, radius=ART_RADIUS)
        self.title_text = Text(self, role="text_primary")
        self.subtitle = Text(self, role="text_secondary")

        self.source = Text(self, role="text_secondary", align=Qt.AlignRight)
        self.equalizer = Equalizer(self, role="text_secondary")

        self.prev = IconButton(self, icon_name="prev", icon_px=ICON_SKIP,
                               hover_shape="circle", hover_size=(BTN_BOX, BTN_BOX))
        self.play = IconButton(self, icon_name="play", icon_px=ICON_PLAY,
                               hover_shape="circle", hover_size=(BTN_BOX, BTN_BOX))
        self.next = IconButton(self, icon_name="next", icon_px=ICON_SKIP,
                               hover_shape="circle", hover_size=(BTN_BOX, BTN_BOX))

        self.time_left = Text(self, role="text_muted", align=Qt.AlignLeft)
        self.time_right = Text(self, role="text_muted", align=Qt.AlignRight)
        self.bar = SeekBar(self)

        self.prev.clicked.connect(self.service.previous)
        self.play.clicked.connect(self.service.toggle)
        self.next.clicked.connect(self.service.next)
        self.bar.seek.connect(self.service.seek)
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

        width = s(CONTENT_R) - s(CONTENT_X)
        self.title_text.setGeometry(s(CONTENT_X), s(TITLE_Y), width, s(TITLE_H))
        self.subtitle.setGeometry(s(CONTENT_X), s(SUBTITLE_Y), width, s(SUBTITLE_H))

        box = s(BTN_BOX)
        cx = (s(CONTENT_X) + s(CONTENT_R)) // 2
        cy = s(BTN_CY)
        for btn, dx in ((self.prev, -s(BTN_GAP)), (self.play, 0), (self.next, s(BTN_GAP))):
            btn.setGeometry(cx + dx - box // 2, cy - box // 2, box, box)

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
        self.equalizer.setGeometry(x - s(EQ_GAP) - eq_w, eq_bottom - eq_h, eq_w, eq_h)

    def _layout_progress(self):
        """Полоса ужимается под длину таймингов: у часовых треков они шире."""
        y, h = s(ROW_Y), s(ROW_H)
        lw = max(self.time_left.text_width(), s(TIME_MIN_W))
        rw = max(self.time_right.text_width(), s(TIME_MIN_W))
        gap = s(TIME_GAP)

        left = s(CONTENT_X)
        right = s(CONTENT_R) - s(8)     # правый тайминг в макете кончается на 550
        self.time_left.setGeometry(left, y, lw, h)
        self.time_right.setGeometry(right - rw, y, rw, h)

        bar_x = left + lw + gap
        bar_w = max(s(20), (right - rw - gap) - bar_x)
        self.bar.setGeometry(bar_x, y, bar_w, h)

    # --- данные ---------------------------------------------------------- #

    def apply_state(self, state):
        playing = bool(state and state.playing)
        self._has_session = state is not None

        if state is None:
            self.title_text.set_text("Ничего не играет")
            self.subtitle.set_text("")
            self.source.set_text("")
            if self._art_key is not None:
                self._art_key = None
                self.art.set_image(None)
            self.bar.set_values(0, 0)
            self.time_left.set_text("")
            self.time_right.set_text("")
        else:
            self.title_text.set_text(state.title or "Без названия")
            self.subtitle.set_text(state.subtitle())
            self.source.set_text(state.app_name)
            if state.art_key != self._art_key:
                self._art_key = state.art_key
                self.art.set_image(state.art)
            self.bar.set_values(state.elapsed(), state.duration)
            self.time_left.set_text(format_time(self.bar.fraction() * state.duration
                                                if self.bar.is_scrubbing()
                                                else state.elapsed()))
            self.time_right.set_text(format_time(state.duration))

        self.play.set_icon("pause" if playing else "play")
        self.equalizer.set_playing(playing)
        self.equalizer.setVisible(bool(state and state.app_name))

        self.prev.setEnabled(bool(state and state.can_prev))
        self.next.setEnabled(bool(state and state.can_next))
        self.play.setEnabled(state is not None)

        self._layout_header()
        self._layout_progress()

    # --- жизненный цикл -------------------------------------------------- #

    def on_show(self):
        self.service.set_active(True)

    def on_hide(self):
        self.service.set_active(False)
