"""
Переводчик.

Два бэкенда: Argos (офлайн, пакет argostranslate) и DeepL (по ключу). Ни один не
входит в зависимости — вкладка обязана работать и без них, показывая, что
переводчик не настроен, а не падать на импорте.

Перевод считается в фоновом потоке: и загрузка модели Argos, и запрос к DeepL
занимают заметное время, а панель должна оставаться отзывчивой.
"""

import threading

from PySide6.QtCore import QObject, Signal

from ..core import logbook

# Языки в порядке макета. Код — двухбуквенный, он же уходит в оба бэкенда.
LANGUAGES = (
    ("en", "ENGLISH"),
    ("ru", "RUSSIAN"),
    ("uk", "UKRAINIAN"),
    ("ja", "JAPANESE"),
    ("de", "GERMAN"),
    ("fr", "FRENCH"),
    ("es", "SPANISH"),
    ("zh", "CHINESE"),
)

LANG_NAMES = dict(LANGUAGES)


def language_name(code):
    return LANG_NAMES.get(code, (code or "").upper())


class Translator(QObject):
    """`done(request_id, text)` — результат; `failed(request_id, reason)` — нет."""

    done = Signal(int, str)
    failed = Signal(int, str)
    status = Signal(int, str)       # ключ строки для показа во второй панели

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self._seq = 0
        self._argos = None

    def backend(self):
        return self.settings.get("translate_backend", "argos")

    def available(self):
        if self.backend() == "deepl":
            return bool(self.settings.get("deepl_key"))
        return self._load_argos() is not None

    def pair_ready(self, source, target):
        """Установлен ли путь перевода. Для DeepL всегда да."""
        if self.backend() == "deepl":
            return bool(self.settings.get("deepl_key"))
        argos = self._load_argos()
        if argos is None:
            return False
        langs = {lang.code: lang for lang in argos.get_installed_languages()}
        a, b = langs.get(source), langs.get(target)
        try:
            return bool(a and b and a.get_translation(b))
        except Exception:
            return False

    def translate(self, text, source, target):
        """Ставит перевод в очередь. Возвращает номер запроса.

        Номер нужен, чтобы отбросить ответ на текст, который пользователь уже
        успел переписать: приходят они не по порядку.
        """
        self._seq += 1
        request = self._seq
        text = (text or "").strip()
        if not text:
            self.done.emit(request, "")
            return request
        threading.Thread(target=self._work, args=(request, text, source, target),
                         name="knack-translate", daemon=True).start()
        return request

    # --- бэкенды ---------------------------------------------------------- #

    def _work(self, request, text, source, target):
        try:
            if self.backend() == "deepl":
                result = self._deepl(text, source, target)
            else:
                result = self._argos_translate(request, text, source, target)
        except Exception as error:
            logbook.exc("translate")
            self.failed.emit(request, str(error))
            return
        if result is None:
            self.failed.emit(request, "backend")
            return
        self.done.emit(request, result)

    def _load_argos(self):
        if self._argos is not None:
            return self._argos or None
        try:
            from argostranslate import translate as argos
            self._argos = argos
        except ImportError:
            self._argos = False
        return self._argos or None

    def _argos_translate(self, request, text, source, target):
        """
        Перевод офлайн-моделью.

        Сам пакет argostranslate моделей не содержит: языковые пары качаются
        отдельно, и без нужной пары `get_translation` возвращает None, а вызов
        падает с AttributeError. Поэтому пару сначала проверяем, при
        необходимости ставим, и только потом переводим.
        """
        argos = self._load_argos()
        if argos is None:
            return None
        if not self.pair_ready(source, target):
            if not self.settings.get("translate_auto_download", True):
                raise RuntimeError("no-pack")
            self.status.emit(request, "translate.downloading")
            if not self._install_pair(source, target):
                raise RuntimeError("no-pack")
        return argos.translate(text, source, target)

    def _install_pair(self, source, target):
        """Скачивает и ставит недостающие языковые пакеты. True — получилось."""
        try:
            from argostranslate import package
        except ImportError:
            return False
        try:
            package.update_package_index()
            available = package.get_available_packages()
        except Exception:
            logbook.exc("argos index")
            return False

        def find(a, b):
            for item in available:
                if item.from_code == a and item.to_code == b:
                    return item
            return None

        plan = []
        direct = find(source, target)
        if direct is not None:
            plan = [direct]
        else:
            # Прямой пары может не быть вовсе (украинский в японский); argos
            # умеет ходить через английский, если стоят обе половины.
            first, second = find(source, "en"), find("en", target)
            if first is not None and second is not None:
                plan = [first, second]
        if not plan:
            return False

        for item in plan:
            try:
                logbook.log("argos: ставлю пакет %s->%s" % (item.from_code, item.to_code))
                package.install_from_path(item.download())
            except Exception:
                logbook.exc("argos install")
                return False
        return self.pair_ready(source, target)

    def _deepl(self, text, source, target):
        key = str(self.settings.get("deepl_key") or "").strip()
        if not key:
            return None
        try:
            import requests
        except ImportError:
            return None
        host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
        response = requests.post(
            "https://%s/v2/translate" % host,
            data={"text": text, "target_lang": target.upper(),
                  "source_lang": source.upper()},
            headers={"Authorization": "DeepL-Auth-Key " + key},
            timeout=15,
        )
        response.raise_for_status()
        return response.json()["translations"][0]["text"]
