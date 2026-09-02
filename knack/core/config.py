import os
import json

from .constants import APP_DIR, CONFIG_PATH


def defaults():
    return {
        "theme":             "dark",       # имя темы из ui/theme.py
        "language":          "en",

        # Как открывать панель: hover | hotkey | hover+hotkey | tray
        "trigger":           "hover+hotkey",
        "hotkey":            "ctrl+alt+k",
        # Как прятать: leave (курсор ушёл) | click_outside | manual
        "hide_mode":         "leave",
        # Сколько курсор должен продержаться в полосе у края, прежде чем панель
        # поедет. Без задержки она выпрыгивала от любого касания края экрана.
        "hover_delay_ms":    150,
        "hide_delay_ms":     220,          # задержка перед уходом, гасит дрожание
        "monitor":           "cursor",     # cursor | primary
        "edge_gap":          0,            # отступ панели от края экрана, px макета
        "scale_override":    0.0,          # 0 = считать от ширины экрана
        "ui_scale":          1.0,          # ползунок размера панели (множитель)
        "animation_fps":     0,            # 0 = частота монитора; иначе 60/120/144/…

        "autostart":         True,
        # Тихая проверка обновлений раз в два часа и вопрос о найденной версии.
        "check_updates":     True,
        # Версия, о которой уже спросили и получили «позже»: второй раз не лезем.
        "update_dismissed_version": "",
        "last_tab":          "media",

        # Смена раскладки у выделенного текста по горячей клавише.
        "layout_switch_enabled":   True,
        "layout_hotkey":           "ctrl+alt+l",
        "layout_restore_clipboard": True,

        # Закрепление активного окна поверх остальных по горячей клавише.
        "pin_enabled":       True,
        "pin_hotkey":        "ctrl+alt+p",
        # Отпускать закреплённые окна при выходе: иначе снять закрепление
        # после закрытия Knack было бы нечем.
        "pin_release_on_exit": True,
        # Значок закрепления в углу активного окна.
        "pin_badge":         True,

        "clipboard_limit":   100,          # длина истории текстового буфера

        # Превью кадра для видео и обложки для музыки на полке. Требует ffmpeg,
        # он качается по требованию в %APPDATA%/Knack/tools.
        "shelf_video_thumbs": True,

        # Переводчик: argos (офлайн) | deepl (ключ). Переключатель — в настройках.
        "translate_backend": "argos",
        "deepl_key":         "",
        "translate_from":    "en",
        "translate_to":      "ru",
        # Argos ставит языковые пары отдельной загрузкой; без них перевода нет.
        "translate_auto_download": True,
        # Куда качать модели. Пусто — папка translate в данных программы.
        "translate_models_dir": "",
        # Кириллица в поле с латиницей сама разворачивает направление перевода.
        "translate_autodetect": True,
    }


_ENUMS = {
    "trigger":           ("hover", "hotkey", "hover+hotkey", "tray"),
    "hide_mode":         ("leave", "click_outside", "manual"),
    "monitor":           ("cursor", "primary"),
    "translate_backend": ("argos", "deepl"),
    "language":          ("ru", "en"),
}


def _num_in(v, lo, hi, fallback, integer=True):
    """Число в диапазоне [lo, hi] или fallback (bool числом не считаем)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return fallback
    if integer:
        if float(v) != int(v):
            return fallback
        v = int(v)
    return v if lo <= v <= hi else fallback


def validate(data):
    """Приводит настройки к рабочему виду: битое значение заменяется дефолтом."""
    d = defaults()

    # Общее правило: тип не совпал с типом дефолта — берём дефолт.
    for key, dv in d.items():
        if key not in data:
            continue
        v = data[key]
        if isinstance(dv, bool):
            ok = isinstance(v, bool)
        elif isinstance(dv, (int, float)):
            ok = isinstance(v, (int, float)) and not isinstance(v, bool)
        else:
            ok = isinstance(v, type(dv))
        data[key] = v if ok else dv

    for key, allowed in _ENUMS.items():
        if data.get(key) not in allowed:
            data[key] = d[key]

    data["clipboard_limit"] = _num_in(data.get("clipboard_limit"), 10, 1000, 100)
    data["hover_delay_ms"]  = _num_in(data.get("hover_delay_ms"), 0, 2000, 150)
    data["hide_delay_ms"]   = _num_in(data.get("hide_delay_ms"), 0, 3000, 220)
    data["edge_gap"]        = _num_in(data.get("edge_gap"), 0, 200, 0)
    data["scale_override"]  = _num_in(data.get("scale_override"), 0.0, 3.0, 0.0,
                                      integer=False)
    data["ui_scale"]        = _num_in(data.get("ui_scale"), 0.7, 1.6, 1.0,
                                      integer=False)
    data["animation_fps"]   = _num_in(data.get("animation_fps"), 0, 360, 0)

    for key in ("hotkey", "layout_hotkey"):
        if not str(data.get(key) or "").strip():
            data[key] = d[key]
    # Два одинаковых сочетания — второе просто не зарегистрируется, и настройка
    # выглядела бы рабочей, ничего не делая.
    if data["layout_hotkey"] == data["hotkey"]:
        data["layout_hotkey"] = d["layout_hotkey"]
        if data["layout_hotkey"] == data["hotkey"]:
            data["hotkey"] = d["hotkey"]

    return data


def load():
    """Читает настройки с диска, дополняя отсутствующие ключи дефолтами."""
    data = defaults()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            data.update(saved)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return validate(data)


def save(settings):
    """Сохраняет настройки на диск (тихо, без падений на ошибках ФС)."""
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except OSError:
        pass
