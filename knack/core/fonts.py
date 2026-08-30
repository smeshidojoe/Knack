import os
import threading

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics, QImage, QPainter

from .constants import FONTS_DIR

FAMILY = "SF Pro Display"

# В SF Pro эмодзи нет, и на первую же цветную картинку Qt уходит перебирать
# шрифты системы. Называем запасной шрифт сам: перебор тогда не начинается.
EMOJI_FAMILY = "Segoe UI Emoji"

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


# Строка с эмодзи, нарисованная первой за запуск, стоит около полусекунды: Qt
# поднимает цветной шрифт и его таблицы. Дальше это уже бесплатно. Платим этот
# раз в фоне на старте, иначе он выпадает на первое открытие вкладки с буфером —
# ровно тогда, когда панель выезжает, и выезд встаёт колом.
_WARM_SAMPLE = "😊🚀✅👨‍👩‍👧"
_warmed = False


def warm_up():
    """Прогревает цветной шрифт в отдельном потоке. Зовётся один раз на старте."""
    global _warmed
    if _warmed:
        return
    _warmed = True
    threading.Thread(target=_warm_worker, name="knack-fontwarm",
                     daemon=True).start()


def _warm_worker():
    # Рисуем в QImage, а не в QPixmap: только он разрешён вне главного потока.
    try:
        f = font(12, "Medium")
        image = QImage(64, 24, QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(image)
        painter.setFont(f)
        QFontMetrics(f).horizontalAdvance(_WARM_SAMPLE)
        painter.drawText(image.rect(), int(Qt.AlignLeft | Qt.AlignVCenter),
                         _WARM_SAMPLE)
        painter.end()
    except Exception:
        pass


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
        f.setFamilies([FAMILY, EMOJI_FAMILY])
        f.setPixelSize(px)
        if letter_spacing:
            f.setLetterSpacing(QFont.AbsoluteSpacing, letter_spacing)
        _cache[key] = f
    return QFont(f)
