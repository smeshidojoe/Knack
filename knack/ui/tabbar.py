"""
Вкладки панели.

Шесть в колонке слева и «Заметки» отдельной кнопкой у правого края — так в
макете. Центры левой колонки распределяются равномерно между RAIL_FIRST_Y и
RAIL_LAST_Y: при шести вкладках шаг выходит ровно 26 px, как нарисовано.

TabBar не виджет, а раскладчик: кнопки живут прямо на панели. Контейнер шириной
54 px обрезал бы подсветку, которая при наведении вырастает за свои границы, и
не дал бы поставить кнопку у правого края.

Активная вкладка отмечена белой иконкой, наведение — серой пилюлей 28x23,
которая растёт вместе с иконкой (см. widgets/buttons.py).
"""

from PySide6.QtCore import QObject, Signal

from ..core.constants import (NOTES_TAB_X, NOTES_TAB_Y, RAIL_FIRST_Y,
                              RAIL_ICON_X, RAIL_LAST_Y, RAIL_PILL_H,
                              RAIL_PILL_R, RAIL_PILL_W, TAB_BOX_H, TAB_BOX_W)
from ..core.scale import s
from .widgets.buttons import IconButton

# (ключ вкладки, имя иконки, оптический размер глифа в px макета)
LEFT_TABS = (
    ("media",     "music",     12),
    ("shelf",     "shelf",     11),
    ("clipboard", "clipboard", 12),
    ("snippets",  "snippets",  12),
    ("translate", "translate", 11),
    ("settings",  "settings",  11),
)

RIGHT_TABS = (
    ("notes", "notes", 11),
)


class TabBar(QObject):
    selected = Signal(str)

    def __init__(self, panel):
        super().__init__(panel)
        self.panel = panel
        self._buttons = {}
        self._current = None

        for key, icon_name, icon_px in LEFT_TABS + RIGHT_TABS:
            btn = IconButton(
                panel,
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
        return [key for key, _, _ in LEFT_TABS + RIGHT_TABS]

    def set_current(self, key):
        if key == self._current:
            return
        self._current = key
        for k, btn in self._buttons.items():
            btn.set_active(k == key)

    def current(self):
        return self._current

    def raise_all(self):
        for btn in self._buttons.values():
            btn.raise_()

    def relayout(self):
        w, h = s(TAB_BOX_W), s(TAB_BOX_H)

        count = len(LEFT_TABS)
        step = (RAIL_LAST_Y - RAIL_FIRST_Y) / (count - 1) if count > 1 else 0
        for i, (key, _, _) in enumerate(LEFT_TABS):
            self._place(key, RAIL_ICON_X, RAIL_FIRST_Y + i * step, w, h)

        for key, _, _ in RIGHT_TABS:
            self._place(key, NOTES_TAB_X, NOTES_TAB_Y, w, h)

    def _place(self, key, cx, cy, w, h):
        self._buttons[key].setGeometry(s(cx) - w // 2, s(cy) - h // 2, w, h)
