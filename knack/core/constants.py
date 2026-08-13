import os
import sys

APP_NAME = "Knack"
VERSION = "0.1.0"


def _root():
    """Корень приложения: рядом с exe в сборке, корень репозитория в dev."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # knack/core/constants.py -> knack/core -> knack -> корень
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


ROOT_DIR   = _root()
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
FONTS_DIR  = os.path.join(ASSETS_DIR, "fonts")
ICONS_DIR  = os.path.join(ASSETS_DIR, "icons")

# Пользовательские данные — в %APPDATA%\Knack (запасной путь для не-Windows).
_BASE = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
APP_DIR = os.path.join(_BASE, APP_NAME)

CONFIG_PATH    = os.path.join(APP_DIR, "config.json")
SHELF_DIR      = os.path.join(APP_DIR, "clipboard")               # файлы скриншотов
SHELF_INDEX    = os.path.join(APP_DIR, "shelf.json")              # порядок и метаданные
CLIPBOARD_PATH = os.path.join(APP_DIR, "clipboard_history.json")  # история текста
SNIPPETS_PATH  = os.path.join(APP_DIR, "snippets.json")           # заготовки
LOG_PATH       = os.path.join(APP_DIR, "knack.log")

# Первый ли это запуск — снимаем до того, как что-либо создаст APP_DIR.
IS_FIRST_RUN = not os.path.isdir(APP_DIR)

# --- Геометрия панели ------------------------------------------------------ #
# Макет нарисован под монитор 2560x1440; всё остальное — масштаб от него
# (см. core/scale.py). Числа ниже — «сырые» координаты Figma.
BASE_SCREEN_W = 2560
PANEL_W       = 574
PANEL_H       = 192
PANEL_RADIUS  = 19

# Левая колонка со вкладками.
RAIL_W        = 54     # до левого края обложки
RAIL_ICON_X   = 27     # центр иконок по X
RAIL_FIRST_Y  = 40     # центр первой вкладки по Y
RAIL_STEP     = 26     # шаг между вкладками
RAIL_PILL_W   = 28     # подсветка при наведении
RAIL_PILL_H   = 23
RAIL_PILL_R   = 7

# Контентная колонка (правее обложки).
CONTENT_X     = 179
CONTENT_R     = 558    # правая граница текста и прогресса
