"""
Левая колонка со вкладками.

Порядок и шаг взяты из макета: центры вкладок идут ровно через 26 px, шестая
позиция — шестерёнка настроек. Активная вкладка отмечена белой иконкой,
наведение — серой пилюлей 28x23.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget

from ..core.constants import (RAIL_FIRST_Y, RAIL_ICON_X, RAIL_PILL_H,
                              RAIL_PILL_R, RAIL_PILL_W, RAIL_STEP, RAIL_W)
from ..core.scale import s
from .widgets.buttons import IconButton

# (ключ вкладки, имя иконки, оптический размер глифа в px макета)
TABS = (
    ("media",     "music",     12),
    ("shelf",     "shelf",     11),
    ("clipboard", "clipboard", 11),
    ("snippets",  "snippets",  11),
    ("translate", "translate", 11),
    ("settings",  "settings",  11),
)


class TabBar(QWidget):
    selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._buttons = {}
        self._current = None

        for key, icon_name, icon_px in TABS:
            btn = IconButton(
                self,
                icon_name=icon_name,
                icon_px=icon_px,
                hover_shape="pill",
                hover_size=(RAIL_PILL_W, RAIL_PILL_H),
                hover_radius=RAIL_PILL_R,
                role="text_muted",
                role_hover="text_secondary",
                role_active="text_primary",
            )
            btn.clicked.connect(lambda k=key: self.selected.emit(k))
            self._buttons[key] = btn

    def keys(self):
        return [key for key, _, _ in TABS]

    def set_current(self, key):
        if key == self._current:
            return
        self._current = key
        for k, btn in self._buttons.items():
            btn.set_active(k == key)

    def current(self):
        return self._current

    def relayout(self):
        w, h = s(RAIL_PILL_W), s(RAIL_PILL_H)
        for i, (key, _, _) in enumerate(TABS):
            cy = s(RAIL_FIRST_Y + i * RAIL_STEP)
            self._buttons[key].setGeometry(s(RAIL_ICON_X) - w // 2, cy - h // 2, w, h)
        self.setFixedWidth(s(RAIL_W))
