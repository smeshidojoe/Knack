"""
Минимальный лог в %APPDATA%\\Knack\\knack.log.

Панель живёт без консоли (в сборке — windowed), а медиа-служба работает в
отдельном потоке: без файла ошибки оттуда просто исчезают.
"""

import os
import time
import traceback

from .constants import APP_DIR, LOG_PATH

_MAX_BYTES = 512 * 1024
_console = True     # в dev дублируем в stdout


def set_console(on):
    global _console
    _console = bool(on)


def log(*parts):
    line = "%s  %s" % (time.strftime("%H:%M:%S"),
                       " ".join(str(p) for p in parts))
    if _console:
        try:
            print(line, flush=True)
        except Exception:
            pass
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        if os.path.isfile(LOG_PATH) and os.path.getsize(LOG_PATH) > _MAX_BYTES:
            os.replace(LOG_PATH, LOG_PATH + ".1")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def exc(where):
    log("ERROR", where + ":", traceback.format_exc(limit=6).strip())
