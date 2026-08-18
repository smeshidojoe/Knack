"""Чтение и запись JSON-файлов данных: тихо, без падений на битом файле."""

import json
import os
import tempfile

from .constants import APP_DIR


def load(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default
    if type(data) is not type(default):
        return default
    return data


def save(path, data):
    """
    Пишем через временный файл рядом и подменяем им целевой.

    История буфера и заметки переписываются на каждое изменение; обрыв записи
    (выключили питание) оставил бы пустой файл вместо всех данных.
    """
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        directory = os.path.dirname(path) or APP_DIR
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass
