"""
Список задач.

Строка — это текст и галочка, больше ничего: ни сроков, ни приоритетов, ни
вложенности. Отмеченные задачи остаются на месте, а не уезжают вниз: список
короткий, и прыгающая под курсором строка раздражала бы сильнее, чем помогала
сортировка.

Пустые задачи убираются при уходе с вкладки — как пустые заметки.
"""

import time
import uuid

from PySide6.QtCore import QObject, Signal

from ..core import jsonfile
from ..core.constants import TODO_PATH


class TodoStore(QObject):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = [x for x in jsonfile.load(TODO_PATH, [])
                      if isinstance(x, dict) and "text" in x]

    def _save(self):
        jsonfile.save(TODO_PATH, self.items)
        self.changed.emit()

    def create(self):
        """Новая задача заводится сверху: её сразу начинают набирать."""
        item = {"id": uuid.uuid4().hex[:12], "text": "", "done": False,
                "updated": time.time()}
        self.items.insert(0, item)
        self._save()
        return item

    def set_text(self, task_id, text):
        for item in self.items:
            if item.get("id") == task_id:
                text = text.strip()
                if item.get("text") == text:
                    return
                item["text"] = text
                item["updated"] = time.time()
                self._save()
                return

    def toggle(self, index):
        if not 0 <= index < len(self.items):
            return
        item = self.items[index]
        item["done"] = not item.get("done")
        item["updated"] = time.time()
        self._save()

    def remove(self, index):
        if 0 <= index < len(self.items):
            del self.items[index]
            self._save()

    def prune_empty(self, keep_id=None):
        """Выкидывает задачи без текста, кроме той, что правят прямо сейчас."""
        before = len(self.items)
        self.items = [x for x in self.items
                      if (x.get("text") or "").strip() or x.get("id") == keep_id]
        if len(self.items) != before:
            self._save()

    def index_of(self, task_id):
        for index, item in enumerate(self.items):
            if item.get("id") == task_id:
                return index
        return -1
