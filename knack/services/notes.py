"""
Заметки.

Заголовок в списке — первая непустая строка текста, как в Cyclop. Отдельного
поля названия нет: лишний ввод ради строчки, которая и так есть в тексте.

Пустые заметки при уходе с вкладки убираются сами — иначе список зарастает
нажатиями «New Note».
"""

import time
import uuid

from PySide6.QtCore import QObject, Signal

from ..core import jsonfile
from ..core.constants import NOTES_PATH


class NotesStore(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = [x for x in jsonfile.load(NOTES_PATH, [])
                      if isinstance(x, dict) and "text" in x]

    def _save(self):
        jsonfile.save(NOTES_PATH, self.items)
        self.changed.emit()

    @staticmethod
    def title_of(item):
        for line in (item.get("text") or "").splitlines():
            line = line.strip()
            if line:
                return line
        return ""

    def create(self):
        item = {"id": uuid.uuid4().hex[:12], "text": "", "updated": time.time()}
        self.items.insert(0, item)
        self._save()
        return item

    def set_text(self, note_id, text):
        for item in self.items:
            if item.get("id") == note_id:
                if item.get("text") == text:
                    return
                item["text"] = text
                item["updated"] = time.time()
                self._save()
                return

    def remove(self, note_id):
        before = len(self.items)
        self.items = [x for x in self.items if x.get("id") != note_id]
        if len(self.items) != before:
            self._save()

    def prune_empty(self, keep_id=None):
        """Выкидывает заметки без текста, кроме открытой сейчас."""
        before = len(self.items)
        self.items = [x for x in self.items
                      if (x.get("text") or "").strip() or x.get("id") == keep_id]
        if len(self.items) != before:
            self._save()

    def index_of(self, note_id):
        for index, item in enumerate(self.items):
            if item.get("id") == note_id:
                return index
        return -1
