import os

from PySide6.QtGui import QFont, QFontDatabase

from .constants import FONTS_DIR

FAMILY = "SF Pro Display"

# Все веса регистрируются под одним family с разными стилями.
_FILES = (
    "SF-Pro-Display-Thin.otf",
    "SF-Pro-Display-Light.otf",
    "SF-Pro-Display-Regular.otf",
    "SF-Pro-Display-Medium.otf",
    "SF-Pro-Display-Semibold.otf",
    "SF-Pro-Display-Bold.otf",
    "SF-Pro-Display-Heavy.otf",
)

_loaded = False
_cache = {}


def load():
    """Регистрирует шрифты приложения (один раз за сессию)."""
    global _loaded
    if _loaded:
        return
    for name in _FILES:
        path = os.path.join(FONTS_DIR, name)
        if os.path.isfile(path):
            try:
                QFontDatabase.addApplicationFont(path)
            except Exception:
                pass
    _loaded = True
    # Всё, что запросили до регистрации, попало в кеш запасным шрифтом.
    _cache.clear()


def font(px, style="Regular", letter_spacing=0.0):
    """
    QFont нужного стиля, размер задаётся В ПИКСЕЛЯХ.

    Макет размечен в px, а не в пунктах: setPointSize зависел бы от DPI дважды —
    один раз через Qt, второй через наш масштаб.

    style: Thin | Light | Regular | Medium | Semibold | Bold | Heavy
    """
    px = max(1, int(round(px)))
    key = (px, style, round(letter_spacing, 2))
    f = _cache.get(key)
    if f is None:
        f = QFontDatabase.font(FAMILY, style, 10)
        if f.family() != FAMILY:
            f = QFont(FAMILY)
        f.setPixelSize(px)
        if letter_spacing:
            f.setLetterSpacing(QFont.AbsoluteSpacing, letter_spacing)
        _cache[key] = f
    return QFont(f)
