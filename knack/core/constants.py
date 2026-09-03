import os
import sys

APP_NAME    = "Knack"
APP_VERSION = "0.1.8"

GITHUB_REPO   = "SmeshidoJoe/Knack"
DEVELOPER_URL = "https://github.com/SmeshidoJoe"

# Идентификатор для Windows: под ним группируются уведомления и панель задач.
APP_ID = "SmeshidoJoe.Knack"

# Именованный мьютекс защиты от второго запуска (см. main.py).
INSTANCE_MUTEX = "Knack-Single-Instance-Mutex"

# В сборке PyInstaller ресурсы лежат во временной папке _MEIPASS, в разработке —
# в корне репозитория.
if getattr(sys, "frozen", False):
    BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONTS_DIR  = os.path.join(ASSETS_DIR, "fonts")
ICONS_DIR  = os.path.join(ASSETS_DIR, "icons")
APP_ICO    = os.path.join(ASSETS_DIR, "app.ico")

# Пользовательские данные — в %APPDATA%\Knack (запасной путь для не-Windows).
_BASE = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
APP_DIR = os.path.join(_BASE, APP_NAME)

CONFIG_PATH    = os.path.join(APP_DIR, "config.json")
SHELF_DIR      = os.path.join(APP_DIR, "clipboard")               # файлы полки
SHELF_INDEX    = os.path.join(APP_DIR, "shelf.json")              # порядок и метаданные
CLIPBOARD_PATH = os.path.join(APP_DIR, "clipboard_history.json")  # история текста
SNIPPETS_PATH  = os.path.join(APP_DIR, "snippets.json")           # сниппеты
NOTES_PATH     = os.path.join(APP_DIR, "notes.json")              # заметки
TODO_PATH      = os.path.join(APP_DIR, "todo.json")               # список задач
TRANSLATE_DIR  = os.path.join(APP_DIR, "translate")               # модели перевода
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

# Левая колонка со вкладками. Центры распределяются равномерно между
# RAIL_FIRST_Y и RAIL_LAST_Y: при шести вкладках шаг выходит ровно 26 px, как в
# макете, а лишняя вкладка просто сожмёт шаг, не ломая колонку.
RAIL_W        = 54
RAIL_ICON_X   = 27
RAIL_FIRST_Y  = 40
RAIL_LAST_Y   = 170
RAIL_PILL_W   = 28
RAIL_PILL_H   = 23
RAIL_PILL_R   = 7

# «Заметки» в макете живут отдельной кнопкой у правого края, зеркально левой
# колонке: центр на тех же 27 px от края.
NOTES_TAB_X   = 547
NOTES_TAB_Y   = 90.5

# TODO встал под «Заметками» тем же шагом 26 px, что и в левой колонке: рядом
# стоящие кнопки с разным шагом читались бы как две разные группы.
TODO_TAB_Y    = 116.5

# Кликабельный бокс кнопки заметно больше подсветки: при наведении подсветка
# растёт, а с перелётом в конце клика доходит до ~1.17 своего размера — в бокс
# впритык она бы упёрлась и обрезалась по краям.
TAB_BOX_W     = 34
TAB_BOX_H     = 28
MEDIA_BTN_BOX = 44

# Контентная колонка (правее обложки).
CONTENT_X     = 179
CONTENT_R     = 558    # правая граница шапки: подпись источника и эквалайзер
# Всё, что ниже шапки, обрывается здесь: правее идёт вертикальная полоса кнопки
# «Заметки», и заезжать на неё содержимое вкладок не должно.
BODY_R        = 527
