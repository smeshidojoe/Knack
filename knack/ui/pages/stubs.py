"""
Заглушки вкладок, для которых ещё нет макета.

Каждая — отдельный класс, а не одна параметризованная: как только приедет
дизайн, файл вкладки создаётся рядом, а строка из этого модуля просто удаляется.
Ключи и подписи уже настоящие, поэтому переключение вкладок и подпись в углу
панели работают целиком.
"""

from PySide6.QtCore import Qt

from ...core.constants import CONTENT_R, RAIL_W
from ...core.scale import s
from ..widgets.text import Text
from .base import Page


class _Stub(Page):
    hint = "Скоро"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.label = Text(self, text=self.hint, role="text_muted",
                          align=Qt.AlignHCenter)

    def relayout(self):
        self.label.set_font_px(s(11), "Medium")
        x = s(RAIL_W)
        self.label.setGeometry(x, 0, s(CONTENT_R) - x, self.height() or s(192))


class ShelfPage(_Stub):
    key = "shelf"
    title = "ПОЛКА"
    hint = "Скриншоты из буфера появятся здесь"


class ClipboardPage(_Stub):
    key = "clipboard"
    title = "БУФЕР"
    hint = "История скопированного текста"


class SnippetsPage(_Stub):
    key = "snippets"
    title = "ЗАГОТОВКИ"
    hint = "Почта, телефон и прочее под рукой"


class TranslatePage(_Stub):
    key = "translate"
    title = "ПЕРЕВОДЧИК"
    hint = "Два поля перевода"


class SettingsPage(_Stub):
    key = "settings"
    title = "НАСТРОЙКИ"
    hint = "Тема, хоткей, автозапуск"
