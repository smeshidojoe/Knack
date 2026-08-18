"""
Сниппеты: почта, телефон, ссылки — то, что набирать вручную надоело.

Файл %APPDATA%\\Knack\\snippets.json правится и руками: список словарей
{"name": ..., "value": ..., "icon": ...}. Поле icon необязательное — имя файла
из assets/icons без расширения.
"""

from PySide6.QtCore import QObject, Signal

from ..core import jsonfile
from ..core.constants import SNIPPETS_PATH


class SnippetStore(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = [x for x in jsonfile.load(SNIPPETS_PATH, [])
                      if isinstance(x, dict) and x.get("name")]

    def _save(self):
        jsonfile.save(SNIPPETS_PATH, self.items)
        self.changed.emit()

    def search(self, query):
        """
        Поиск по имени, как в макете: «Почта» оставляет в списке только почту.

        По значению тоже ищем — так находится сниппет, чьё имя забыл.
        """
        query = (query or "").strip().lower()
        if not query:
            return list(enumerate(self.items))
        out = []
        for index, item in enumerate(self.items):
            name = str(item.get("name", "")).lower()
            value = str(item.get("value", "")).lower()
            if query in name or query in value:
                out.append((index, item))
        return out

    def add(self, name, value, icon=""):
        item = {"name": name.strip(), "value": value.strip()}
        if icon:
            item["icon"] = icon
        self.items.append(item)
        self._save()
        return item

    def update(self, index, name=None, value=None):
        if not 0 <= index < len(self.items):
            return
        if name is not None:
            self.items[index]["name"] = name.strip()
        if value is not None:
            self.items[index]["value"] = value.strip()
        self._save()

    def remove(self, index):
        if 0 <= index < len(self.items):
            self.items.pop(index)
            self._save()
