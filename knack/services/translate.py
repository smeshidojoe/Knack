"""
Переводчик.

Два бэкенда: Argos (офлайн, пакет argostranslate) и DeepL (по ключу). Ни один не
входит в зависимости — вкладка обязана работать и без них, показывая, что
переводчик не настроен, а не падать на импорте.

Перевод считается в фоновом потоке: и загрузка модели Argos, и запрос к DeepL
занимают заметное время, а панель должна оставаться отзывчивой.
"""

import importlib.util
import logging
import os
import shutil
import threading

from PySide6.QtCore import QObject, Signal

from ..core import logbook
from ..core.constants import TRANSLATE_DIR

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

# Алфавит языка. Автоопределение направления работает только между кириллицей и
# латиницей: для иероглифов «преобладающая буква» ничего не значит.
SCRIPTS = {
    "ru": "cyrillic", "uk": "cyrillic",
    "en": "latin", "de": "latin", "fr": "latin", "es": "latin",
    "ja": "japanese", "zh": "han",
}

# Сколько букв должно набраться, прежде чем менять направление, и какая доля
# из них должна быть одного алфавита. Иначе направление скакало бы от первой же
# случайной буквы.
DETECT_MIN_LETTERS = 3
DETECT_SHARE = 0.6


def language_name(code):
    return LANG_NAMES.get(code, (code or "").upper())


def detect_script(text):
    """'cyrillic' | 'latin' | '' — по преобладанию букв во введённом тексте."""
    cyrillic = latin = 0
    for char in text or "":
        code = ord(char)
        if 0x0400 <= code <= 0x04FF:
            cyrillic += 1
        elif ("a" <= char <= "z") or ("A" <= char <= "Z"):
            latin += 1
    total = cyrillic + latin
    if total < DETECT_MIN_LETTERS:
        return ""
    if cyrillic / total >= DETECT_SHARE:
        return "cyrillic"
    if latin / total >= DETECT_SHARE:
        return "latin"
    return ""


def pick_direction(text, source, target):
    """
    Куда переводить, судя по набранному тексту.

    Меняем панели местами, только если текст явно написан алфавитом ВТОРОЙ
    панели: набрал кириллицу в поле с английским — панели меняются, и перевод
    идёт из русского. Если оба языка одного алфавита (английский и немецкий),
    менять нечего.
    """
    script = detect_script(text)
    if not script:
        return source, target
    if SCRIPTS.get(source) == script:
        return source, target
    if SCRIPTS.get(target) != script:
        return source, target
    return target, source


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
        """
        Есть ли чем переводить — БЕЗ загрузки самого движка.

        `import argostranslate` тянет ctranslate2 с моделями и в первый раз
        занимает несколько секунд. Вкладка спрашивает про доступность на каждое
        нажатие клавиши, поэтому здесь только проверяем, установлен ли пакет;
        сам импорт делает рабочий поток.
        """
        if self.backend() == "deepl":
            return bool(self.settings.get("deepl_key"))
        if self._argos is None:
            try:
                return importlib.util.find_spec("argostranslate") is not None
            except (ImportError, ValueError):
                return False
        return bool(self._argos)

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

    def warm_up(self):
        """
        Подгружает движок заранее, в фоне.

        Первый `import argostranslate` занимает около шести секунд, и вместе с
        загрузкой модели первый перевод ждал одиннадцать. Начинаем, как только
        открыли вкладку: пока человек набирает текст, движок уже готов.
        """
        if self.backend() != "argos" or self._argos is not None:
            return
        threading.Thread(target=self._load_argos, name="knack-argos-warmup",
                         daemon=True).start()

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

    def models_dir(self):
        return str(self.settings.get("translate_models_dir") or "").strip() or TRANSLATE_DIR

    def _prepare_env(self):
        """
        Куда argos кладёт модели.

        Свои пути он собирает при импорте `argostranslate.settings`, читая
        линуксовые XDG-переменные, и на Windows это оборачивается папками
        `.local` и `.config` прямо в профиле пользователя. Раскладываем всё в
        одном месте — по умолчанию рядом с остальными данными программы.
        Переменные ставим ДО импорта: позже они уже ни на что не влияют.
        """
        base = self.models_dir()
        data = os.path.join(base, "data")
        try:
            os.makedirs(data, exist_ok=True)
        except OSError:
            logbook.exc("translate models dir")
            return
        os.environ["XDG_DATA_HOME"] = data
        os.environ["XDG_CACHE_HOME"] = os.path.join(base, "cache")
        os.environ["XDG_CONFIG_HOME"] = os.path.join(base, "config")
        os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = os.path.join(
            data, "argos-translate", "packages")
        # Разбиение на предложения — только minisbd. По умолчанию argos берёт
        # stanza, а она тянет torch: полтора гигабайта и отдельная загрузка
        # модели ради того, чтобы поставить точки в нужных местах.
        os.environ.setdefault("ARGOS_CHUNK_TYPE", "MINISBD")
        self._migrate_legacy(os.path.join(data, "argos-translate", "packages"))

    @staticmethod
    def _migrate_legacy(packages_dir):
        """
        Разовый перенос моделей из папки, куда argos клал их по умолчанию.

        До появления настройки пути модели уходили в `~/.local/share/argos-translate`
        — линуксовая раскладка прямо в профиле пользователя. Языковая пара весит
        около двухсот мегабайт, качать её заново незачем, а держать две копии на
        системном диске тем более.
        """
        legacy = os.path.join(os.path.expanduser("~"), ".local", "share",
                              "argos-translate", "packages")
        if not os.path.isdir(legacy) or os.path.abspath(legacy) == os.path.abspath(packages_dir):
            return
        try:
            if os.path.isdir(packages_dir) and os.listdir(packages_dir):
                return          # у нас уже что-то стоит, не трогаем
            moved = 0
            os.makedirs(packages_dir, exist_ok=True)
            for name in os.listdir(legacy):
                source = os.path.join(legacy, name)
                target = os.path.join(packages_dir, name)
                if os.path.exists(target):
                    continue
                shutil.move(source, target)
                moved += 1
            if moved:
                logbook.log("перевод: перенёс %d языковых пакетов из %s"
                            % (moved, legacy))
        except OSError:
            logbook.exc("translate migrate")

    def loaded(self):
        """Движок уже подгружен — смена папки моделей подействует со следующего
        запуска."""
        return bool(self._argos)

    def _load_argos(self):
        if self._argos is not None:
            return self._argos or None
        self._prepare_env()
        # stanza, которую argos тянет для разбивки на предложения, сыплет в
        # консоль предупреждениями вида «package default expects mwt».
        # Это её штатная болтовня, к переводу отношения не имеет.
        for name in ("stanza", "argostranslate"):
            logging.getLogger(name).setLevel(logging.ERROR)
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
        self._prepare_env()
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
