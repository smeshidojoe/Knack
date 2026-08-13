"""
Что играет в системе — через Windows Media Session (SMTC).

Тот же источник, что кормит всплывашку громкости: браузеры, Spotify, плееры.
Работаем в отдельном потоке со своим циклом asyncio — WinRT отдаёт метаданные
асинхронно, и ждать их в потоке интерфейса нельзя.

Опрос идёт только пока вкладка «Музыка» открыта (set_active). Панель закрыта —
таймеров нет вовсе, как в Cyclop: постоянно тикающий опрос ради невидимого окна
это чистый расход батареи.
"""

import asyncio
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from PySide6.QtCore import QObject, Signal

from ..core import logbook

POLL_ACTIVE = 0.35      # секунд между опросами при открытой вкладке
STATUS_PLAYING = 4      # GlobalSystemMediaTransportControlsSessionPlaybackStatus

_APP_NAMES = {
    "chrome.exe":     "Google Chrome",
    "msedge.exe":     "Microsoft Edge",
    "firefox.exe":    "Mozilla Firefox",
    "opera.exe":      "Opera",
    "browser.exe":    "Яндекс Браузер",
    "vivaldi.exe":    "Vivaldi",
    "brave.exe":      "Brave",
    "spotify.exe":    "Spotify",
    "aimp.exe":       "AIMP",
    "foobar2000.exe": "foobar2000",
    "musicbee.exe":   "MusicBee",
    "vlc.exe":        "VLC",
    "itunes.exe":     "iTunes",
    "telegram.exe":   "Telegram",
    "discord.exe":    "Discord",
    "steam.exe":      "Steam",
}

# У приложений из Store вместо имени файла длинный AUMID — узнаём по куску.
_AUMID_HINTS = (
    ("spotify",    "Spotify"),
    ("zunemusic",  "Медиапроигрыватель"),
    ("zunevideo",  "Медиапроигрыватель"),
    ("yandex",     "Яндекс Браузер"),
    ("chrome",     "Google Chrome"),
    ("edge",       "Microsoft Edge"),
    ("firefox",    "Mozilla Firefox"),
    ("telegram",   "Telegram"),
    ("vlc",        "VLC"),
)


def app_name(app_id):
    """Человеческое имя источника звука из идентификатора приложения."""
    if not app_id:
        return ""
    low = app_id.lower()
    if low in _APP_NAMES:
        return _APP_NAMES[low]
    for hint, name in _AUMID_HINTS:
        if hint in low:
            return name
    name = app_id.split("!")[-1].split("_")[0]
    if name.lower().endswith(".exe"):
        name = name[:-4]
    name = name.replace(".", " ").replace("_", " ").strip()
    return name or app_id


@dataclass
class MediaState:
    app_id: str = ""
    app_name: str = ""
    title: str = ""
    artist: str = ""
    album: str = ""
    playing: bool = False
    can_prev: bool = False
    can_next: bool = False
    position: float = 0.0
    duration: float = 0.0
    sampled_at: float = field(default_factory=time.monotonic)
    art_key: str = ""
    art: bytes = None

    def elapsed(self):
        """Позиция с учётом времени, прошедшего с момента опроса."""
        if not self.playing:
            return self.position
        value = self.position + (time.monotonic() - self.sampled_at)
        if self.duration > 0:
            value = min(value, self.duration)
        return value

    def subtitle(self):
        parts = [p for p in (self.artist, self.album) if p]
        return " — ".join(parts)

    def track_key(self):
        return "%s|%s|%s" % (self.app_id, self.title, self.artist)


def _import_winrt():
    """Импорт проекций WinRT. None — если пакеты не установлены."""
    try:
        from winrt.runtime import ApartmentType, init_apartment
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager)
        from winrt.windows.storage.streams import Buffer, InputStreamOptions
        return Manager, Buffer, InputStreamOptions, init_apartment, ApartmentType
    except ImportError:
        return None


class MediaService(QObject):
    """Сигнал `updated` отдаёт MediaState или None, если ничего не играет."""

    updated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._loop = None
        self._stop = threading.Event()
        self._active = threading.Event()
        self._wake = None            # asyncio.Event, будит цикл при set_active
        self._manager = None
        self._art_cache = ("", None)  # (track_key, bytes)
        self._available = _import_winrt() is not None
        if not self._available:
            logbook.log("media: winrt не установлен, вкладка «Музыка» будет пустой")

    # --- управление -------------------------------------------------------- #

    def available(self):
        return self._available

    def start(self):
        if not self._available or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="knack-media",
                                        daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._wake_up)

    def set_active(self, active):
        """Открыта ли вкладка «Музыка»: от этого зависит, идёт ли опрос."""
        if active:
            self._active.set()
        else:
            self._active.clear()
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._wake_up)

    def _wake_up(self):
        if self._wake is not None:
            self._wake.set()

    # --- команды плеера ----------------------------------------------------- #

    def toggle(self):
        self._command(lambda s: s.try_toggle_play_pause_async())

    def next(self):
        self._command(lambda s: s.try_skip_next_async())

    def previous(self):
        self._command(lambda s: s.try_skip_previous_async())

    def seek(self, seconds):
        ticks = max(0, int(seconds * 10_000_000))    # WinRT считает в 100 нс
        self._command(lambda s: s.try_change_playback_position_async(ticks))

    def _command(self, call):
        loop = self._loop
        if loop is None:
            return

        async def run():
            session = self._session()
            if session is None:
                return
            try:
                await call(session)
            except Exception:
                logbook.exc("media command")
            await self._push()

        asyncio.run_coroutine_threadsafe(run(), loop)

    # --- поток -------------------------------------------------------------- #

    def _run(self):
        parts = _import_winrt()
        if parts is None:
            return
        Manager, Buffer, InputStreamOptions, init_apartment, ApartmentType = parts
        self._Buffer = Buffer
        self._InputStreamOptions = InputStreamOptions

        # Поток службы живёт в MTA: обращения к SMTC идут не из потока
        # интерфейса, и без инициализации апартамента первый же вызов упадёт.
        try:
            init_apartment(ApartmentType.MULTI_THREADED)
        except Exception:
            logbook.exc("media apartment")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._main(Manager))
        except Exception:
            logbook.exc("media loop")
        finally:
            self._loop = None
            loop.close()

    async def _main(self, Manager):
        self._wake = asyncio.Event()
        try:
            self._manager = await Manager.request_async()
        except Exception:
            logbook.exc("media manager")
            return

        while not self._stop.is_set():
            if self._active.is_set():
                await self._push()
                try:
                    await asyncio.wait_for(self._wake.wait(), POLL_ACTIVE)
                except asyncio.TimeoutError:
                    pass
                self._wake.clear()
            else:
                # Вкладка закрыта: спим до set_active, опросов нет вовсе.
                await self._wake.wait()
                self._wake.clear()
                if not self._stop.is_set() and self._active.is_set():
                    await self._push()

    def _session(self):
        try:
            return self._manager.get_current_session() if self._manager else None
        except Exception:
            return None

    async def _push(self):
        self.updated.emit(await self._collect())

    async def _collect(self):
        session = self._session()
        if session is None:
            return None
        state = MediaState()
        try:
            state.app_id = session.source_app_user_model_id or ""
            state.app_name = app_name(state.app_id)

            info = session.get_playback_info()
            state.playing = int(info.playback_status) == STATUS_PLAYING
            controls = info.controls
            state.can_prev = bool(controls.is_previous_enabled)
            state.can_next = bool(controls.is_next_enabled)

            timeline = session.get_timeline_properties()
            start = timeline.start_time.total_seconds()
            state.duration = max(0.0, timeline.end_time.total_seconds() - start)
            position = max(0.0, timeline.position.total_seconds() - start)
            if state.playing:
                # Позиция отдаётся на момент last_updated_time, а не «сейчас».
                drift = (datetime.now(timezone.utc)
                         - timeline.last_updated_time).total_seconds()
                if 0 <= drift < 30:
                    position += drift
            if state.duration:
                position = min(position, state.duration)
            state.position = position
            state.sampled_at = time.monotonic()

            props = await session.try_get_media_properties_async()
            state.title = props.title or ""
            state.artist = props.artist or ""
            state.album = props.album_title or ""

            key = state.track_key()
            if self._art_cache[0] == key:
                state.art = self._art_cache[1]
            else:
                state.art = await self._read_thumbnail(props)
                self._art_cache = (key, state.art)
            state.art_key = key
        except Exception:
            logbook.exc("media collect")
            return None
        return state

    async def _read_thumbnail(self, props):
        ref = getattr(props, "thumbnail", None)
        if ref is None:
            return None
        try:
            stream = await ref.open_read_async()
            size = int(stream.size)
            if size <= 0:
                return None
            buffer = self._Buffer(size)
            await stream.read_async(buffer, size, self._InputStreamOptions.READ_AHEAD)
            return bytes(buffer)
        except Exception:
            logbook.exc("media thumbnail")
            return None
