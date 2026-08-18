"""
Цвета интерфейса.

Хранятся ролями, а не значениями: тем будет больше одной, и код виджетов не
должен знать, что «неактивная вкладка» — это именно #525252. Добавить тему =
дописать один Theme в THEMES.

Первая тема собрана из макета: чёрный фон, белый текст и два оттенка серого.
"""

from dataclasses import dataclass, fields

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Theme:
    name: str
    title: str

    bg: str             # фон панели
    hover: str          # подсветка при наведении (пилюля вкладки, круг кнопки)

    text_primary: str   # название трека, активные иконки
    text_secondary: str # исполнитель, источник звука
    text_muted: str     # подпись вкладки, тайминги, неактивные иконки

    track: str          # полоса прогресса, пустая часть
    track_fill: str     # заполненная часть
    track_preview: str  # метка «сюда встанет ползунок» под курсором
    placeholder: str    # заглушка обложки плеера
    card: str           # подложка карточки на полке
    flash: str          # вспышка «скопировано»

    surface: str        # поля ввода, строки списков, поле поиска
    surface_alt: str    # строка заметки, панель выпадающего списка
    surface_hover: str  # строка под курсором

    text_bright: str    # содержимое строк списков
    text_button: str    # подпись служебной кнопки («New Note», «+»)
    text_placeholder: str   # подсказка в пустом поле
    text_faint: str     # «Очистить» и прочие второстепенные действия

    scroll_track: str
    scroll_thumb: str

    menu_bg: str        # фон меню в трее
    menu_border: str    # обводка меню


DARK = Theme(
    name="dark",
    title="Тёмная",
    bg="#000000",
    hover="#242424",
    text_primary="#FFFFFF",
    text_secondary="#8C8C8C",
    text_muted="#525252",
    track="#141414",
    track_fill="#E7E7E7",
    track_preview="#5C5C5C",
    placeholder="#D9D9D9",
    card="#1A181A",
    flash="#FFFFFF",
    surface="#151315",
    surface_alt="#201F20",
    surface_hover="#2A282A",
    text_bright="#FDFBFD",
    text_button="#898889",
    text_placeholder="#565556",
    text_faint="#707070",
    scroll_track="#323232",
    scroll_thumb="#8C8C8C",
    menu_bg="#0A0A0A",
    menu_border="#242424",
)

THEMES = {t.name: t for t in (DARK,)}
DEFAULT = DARK.name

_current = DARK
_qcolors = {}


def current():
    return _current


def apply(name):
    """Ставит активную тему. True — если она изменилась."""
    global _current
    theme = THEMES.get(name, DARK)
    if theme is _current:
        return False
    _current = theme
    _qcolors.clear()
    return True


def color(role):
    """QColor по имени роли ('bg', 'hover', ...). Кешируется."""
    key = (_current.name, role)
    c = _qcolors.get(key)
    if c is None:
        c = QColor(getattr(_current, role))
        _qcolors[key] = c
    return c


def roles():
    """Имена цветовых ролей — для будущего редактора тем."""
    skip = {"name", "title"}
    return [f.name for f in fields(Theme) if f.name not in skip]
