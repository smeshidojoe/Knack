"""
Строки интерфейса на двух языках.

Ключ — точка входа, значения — словарь по коду языка. Пропущенный перевод
подменяется русским, а не падает: недостающая строка не должна ронять вкладку.
"""

LANGUAGES = {"en": "English", "ru": "Русский"}
DEFAULT = "en"

_language = DEFAULT

STRINGS = {
    # Подписи вкладок в левом верхнем углу панели.
    "tab.media":     {"ru": "МУЗЫКА",     "en": "MUSIC"},
    "tab.shelf":     {"ru": "ПОЛКА",      "en": "SHELF"},
    "tab.clipboard": {"ru": "БУФЕР",      "en": "CLIPBOARD"},
    "tab.snippets":  {"ru": "СНИППЕТЫ",   "en": "SNIPPETS"},
    "tab.notes":     {"ru": "ЗАМЕТКИ",    "en": "NOTES"},
    "tab.translate": {"ru": "ПЕРЕВОДЧИК", "en": "TRANSLATE"},
    "tab.settings":  {"ru": "НАСТРОЙКИ",  "en": "SETTINGS"},

    # Вкладка «Музыка».
    "media.idle":     {"ru": "Ничего не играет", "en": "Nothing is playing"},
    "media.untitled": {"ru": "Без названия",     "en": "Untitled"},
    "media.source_switch": {
        "ru": "Нажми, чтобы переключить источник звука",
        "en": "Click to switch the audio source",
    },

    # Заглушки вкладок, пока нет вёрстки.
    "stub.shelf":     {"ru": "Скриншоты из буфера появятся здесь",
                       "en": "Screenshots from the clipboard land here"},
    "stub.clipboard": {"ru": "История скопированного текста",
                       "en": "Copied text history"},
    "stub.snippets":  {"ru": "Почта, телефон и прочее под рукой",
                       "en": "Email, phone and the rest at hand"},
    "stub.notes":     {"ru": "Быстрые заметки", "en": "Quick notes"},
    "stub.translate": {"ru": "Два поля перевода", "en": "Two translation panes"},
    "stub.settings":  {"ru": "Тема, хоткей, автозапуск",
                       "en": "Theme, hotkey, autostart"},

    # Полка.
    "shelf.empty":   {"ru": "Скопируй скриншот или перетащи файл сюда",
                      "en": "Copy a screenshot or drop a file here"},
    "shelf.shot":    {"ru": "Снимок", "en": "Shot"},
    "shelf.copied":  {"ru": "Скопировано", "en": "Copied"},

    # Буфер.
    "clipboard.empty": {"ru": "Скопированный текст появится здесь",
                        "en": "Copied text shows up here"},
    "clipboard.clear": {"ru": "Очистить", "en": "Clear"},

    # Сниппеты.
    "snippets.search": {"ru": "Поиск", "en": "Search"},
    "snippets.empty":  {"ru": "Пока пусто — добавь через +",
                        "en": "Nothing here yet — add with +"},
    "snippets.name":   {"ru": "Название", "en": "Name"},
    "snippets.value":  {"ru": "Значение", "en": "Value"},

    # Заметки.
    "notes.new":         {"ru": "Новая заметка", "en": "New Note"},
    "notes.untitled":    {"ru": "Пустая заметка", "en": "Empty note"},
    "notes.placeholder": {"ru": "Запиши что-нибудь...", "en": "Jot something down..."},

    # Переводчик.
    "translate.placeholder": {"ru": "Введи текст", "en": "Enter text"},
    "translate.working":     {"ru": "Перевожу...", "en": "Translating..."},
    "translate.offline":     {"ru": "Переводчик не настроен",
                              "en": "Translator is not set up"},
    "translate.downloading": {"ru": "Скачиваю языковой пакет...",
                              "en": "Downloading language pack..."},
    "translate.no_pack":     {"ru": "Нет языкового пакета для этой пары",
                              "en": "No language pack for this pair"},

    # Настройки.
    "settings.section.look":      {"ru": "ВНЕШНИЙ ВИД", "en": "APPEARANCE"},
    "settings.section.panel":     {"ru": "ПАНЕЛЬ", "en": "PANEL"},
    "settings.section.shelf":     {"ru": "ПОЛКА", "en": "SHELF"},
    "settings.section.clipboard": {"ru": "БУФЕР", "en": "CLIPBOARD"},
    "settings.section.translate": {"ru": "ПЕРЕВОДЧИК", "en": "TRANSLATOR"},
    "settings.section.layout":    {"ru": "ЗАМЕНА СИМВОЛОВ",
                                  "en": "CHARACTER REPLACE"},
    "settings.section.system":    {"ru": "СИСТЕМА", "en": "SYSTEM"},
    "settings.section.tools":     {"ru": "ИНСТРУМЕНТЫ", "en": "TOOLS"},

    "settings.language":  {"ru": "Язык интерфейса", "en": "Interface language"},
    "settings.scale":     {"ru": "Размер панели", "en": "Panel size"},
    "settings.fps":       {"ru": "Плавность анимаций", "en": "Animation rate"},
    "settings.fps.auto":  {"ru": "Авто", "en": "Auto"},

    "settings.trigger":            {"ru": "Открывать", "en": "Open with"},
    "settings.trigger.hover+hotkey": {"ru": "Наведение и хоткей",
                                      "en": "Hover and hotkey"},
    "settings.trigger.hover":      {"ru": "Наведение", "en": "Hover"},
    "settings.trigger.hotkey":     {"ru": "Хоткей", "en": "Hotkey"},
    "settings.trigger.tray":       {"ru": "Трей", "en": "Tray"},

    "settings.hotkey":       {"ru": "Сочетание", "en": "Shortcut"},
    "settings.hotkey.busy":  {"ru": "Занято другой программой",
                              "en": "Taken by another app"},

    "settings.hide":              {"ru": "Прятать", "en": "Hide on"},
    "settings.hide.leave":        {"ru": "Уход курсора", "en": "Pointer leaves"},
    "settings.hide.click_outside": {"ru": "Клик вне", "en": "Click outside"},
    "settings.hide.manual":       {"ru": "Вручную", "en": "Manually"},

    "settings.hover_delay":     {"ru": "Задержка наведения", "en": "Hover delay"},
    "settings.hide_delay":      {"ru": "Задержка скрытия", "en": "Hide delay"},
    "settings.monitor":         {"ru": "Монитор", "en": "Monitor"},
    "settings.monitor.cursor":  {"ru": "С курсором", "en": "With pointer"},
    "settings.monitor.primary": {"ru": "Основной", "en": "Primary"},
    "settings.edge_gap":        {"ru": "Отступ от края", "en": "Edge gap"},

    "settings.video_thumbs": {"ru": "Превью для видео и музыки",
                              "en": "Previews for video and music"},
    "settings.video_thumbs.hint": {
        "ru": "Кадр из видео и обложка из музыки. Для этого один раз скачается ffmpeg",
        "en": "A frame from video and cover art from music. Downloads ffmpeg once",
    },

    "settings.clipboard_limit": {"ru": "Длина истории", "en": "History length"},

    "settings.backend":         {"ru": "Движок", "en": "Engine"},
    "settings.backend.argos":   {"ru": "Офлайн", "en": "Offline"},
    "settings.backend.deepl":   {"ru": "DeepL", "en": "DeepL"},
    "settings.deepl_key":       {"ru": "Ключ DeepL", "en": "DeepL key"},
    "settings.deepl_hint":      {"ru": "Вставь ключ и нажми Ок",
                                 "en": "Paste the key and press OK"},
    "settings.auto_download":   {"ru": "Качать языковые пакеты",
                                 "en": "Download language packs"},
    "settings.autodetect":      {"ru": "Определять язык по тексту",
                                 "en": "Detect language from text"},
    "settings.models_dir":      {"ru": "Папка моделей", "en": "Models folder"},
    "settings.choose":          {"ru": "Выбрать", "en": "Choose"},
    "settings.models_pick":     {"ru": "Выбрать папку для языковых моделей",
                                 "en": "Choose the language models folder"},
    "settings.restart_needed":  {"ru": "нужен перезапуск", "en": "restart needed"},
    "settings.save":            {"ru": "Ок", "en": "OK"},
    "settings.saved":           {"ru": "Сохранено", "en": "Saved"},

    "settings.layout_switch": {"ru": "Менять раскладку выделенного",
                               "en": "Switch layout of selection"},
    "settings.layout_switch.hint": {
        "ru": "Выдели текст и нажми сочетание — символы сменят раскладку",
        "en": "Select text and press the shortcut — the characters switch layout",
    },
    "settings.layout_hotkey": {"ru": "Сочетание", "en": "Shortcut"},
    "settings.layout_restore": {"ru": "Возвращать буфер после замены",
                                "en": "Restore clipboard afterwards"},

    "settings.app_update":  {"ru": "Версия программы", "en": "App version"},
    "settings.check":       {"ru": "Проверить", "en": "Check"},
    "settings.install":     {"ru": "Обновить", "en": "Update"},
    "settings.percent":     {"ru": "%d%%", "en": "%d%%"},
    "update.card":          {"ru": "Обновление до %s", "en": "Updating to %s"},
    "update.card.restart":  {"ru": "Перезапускаюсь", "en": "Restarting"},
    "settings.ffmpeg":      {"ru": "ffmpeg для превью", "en": "ffmpeg for previews"},
    "settings.ffmpeg.hint": {"ru": "Нужен, чтобы показывать кадр видео и обложку музыки",
                             "en": "Needed to show a video frame and music cover art"},
    "settings.download":    {"ru": "Скачать", "en": "Download"},
    "settings.reinstall":   {"ru": "Переустановить", "en": "Reinstall"},
    "settings.working":     {"ru": "Качаю…", "en": "Downloading…"},
    "settings.done":        {"ru": "Готово", "en": "Done"},
    "settings.failed":      {"ru": "Не вышло", "en": "Failed"},

    "settings.autostart":     {"ru": "Запускать с Windows", "en": "Start with Windows"},
    "settings.autostart.dev": {"ru": "Только в собранном exe",
                               "en": "Built exe only"},

    # Трей.
    "tray.show":      {"ru": "Показать панель",     "en": "Show panel"},
    "tray.autostart": {"ru": "Запускать с Windows", "en": "Start with Windows"},
    "tray.update":    {"ru": "Проверить обновление", "en": "Check for updates"},
    "tray.quit":      {"ru": "Выход",               "en": "Quit"},

    "update.checking":    {"ru": "Проверяю обновления…", "en": "Checking for updates…"},
    "update.current":     {"ru": "Установлена последняя версия",
                           "en": "You are on the latest version"},
    "update.available":   {"ru": "Есть версия %s — качаю",
                           "en": "Version %s is available — downloading"},
    "update.downloading": {"ru": "Качаю обновление…", "en": "Downloading update…"},
    "update.ready":       {"ru": "Обновление готово, перезапускаюсь",
                           "en": "Update ready, restarting"},
    "update.error":       {"ru": "Не удалось проверить обновления",
                           "en": "Could not check for updates"},
    "update.dev":         {"ru": "Обновление работает только в собранной программе",
                           "en": "Updates work only in the built app"},
}


def set_language(code):
    """Ставит язык интерфейса. True — если он изменился."""
    global _language
    code = code if code in LANGUAGES else DEFAULT
    if code == _language:
        return False
    _language = code
    return True


def language():
    return _language


def t(key):
    """Строка по ключу на текущем языке."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(_language) or entry.get(DEFAULT) or key
