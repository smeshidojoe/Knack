"""Все службы панели в одном месте: создание, запуск, остановка."""

from PySide6.QtCore import QObject

from .audio import AudioSessions
from .clipboard import ClipboardService
from .layout import LayoutSwitcher
from .media import MediaService
from .notes import NotesStore
from .pin import PinService
from .shelf import ShelfStore
from .snippets import SnippetStore
from .todo import TodoStore
from .translate import Translator
from .volume import VolumeService
from .updates import UpdateService


class Services(QObject):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.media = MediaService(self)
        self.shelf = ShelfStore(settings, self)
        self.clipboard = ClipboardService(settings, self.shelf, self)
        self.snippets = SnippetStore(self)
        self.notes = NotesStore(self)
        self.todo = TodoStore(self)
        self.translator = Translator(settings, self)
        self.layout = LayoutSwitcher(settings, self.clipboard, self)
        self.pin = PinService(self)
        self.volume = VolumeService(self)
        self.audio = AudioSessions(self)
        self.updates = UpdateService(settings, self)

    def start(self):
        self.media.start()
        self.clipboard.start()

    def stop(self):
        if self.settings.get("pin_release_on_exit", True):
            self.pin.release_all()
        self.media.stop()
        self.volume.shutdown()
        self.audio.shutdown()
        self.shelf.shutdown()
