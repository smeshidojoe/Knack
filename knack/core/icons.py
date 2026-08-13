"""
Загрузка иконок и перекраска под тему.

В assets/icons лежат и SVG (выгрузка из Figma), и PNG. Все одноцветные, поэтому
цвет задаётся при отрисовке: рисуем силуэт и заливаем через SourceIn. Одна и та
же иконка работает и активной, и неактивной, и в любой будущей теме.

Размер задаётся ДЛИННОЙ СТОРОНОЙ САМОГО ГЛИФА, а не его холста. В макете боксы
разного размера (12, 13, 16, 17, 21, 24 px) и с разными полями — у song.png
глиф занимает меньше половины картинки. Выравнивать по холстам значило бы
получить визуально разный вес: нота вышла бы вдвое мельче остальных. Поэтому
прозрачные поля обрезаются, и все иконки приводятся к общей оптической высоте.
"""

import os

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .constants import ICONS_DIR

_PROBE = 128        # разрешение промера границ глифа

_cache = {}
_box_cache = {}
_missing = set()


def _path(name):
    for ext in (".svg", ".png"):
        p = os.path.join(ICONS_DIR, name + ext)
        if os.path.isfile(p):
            return p
    return None


def _dpr():
    scr = QGuiApplication.primaryScreen()
    return scr.devicePixelRatio() if scr else 1.0


def _draw_source(painter, path, side):
    """Рисует исходник вписанным в квадрат side x side."""
    if path.endswith(".svg"):
        r = QSvgRenderer(path)
        box = r.defaultSize()
        if box.isValid() and box.width() > 0 and box.height() > 0:
            k = min(side / box.width(), side / box.height())
            w, h = box.width() * k, box.height() * k
            r.render(painter, QRectF((side - w) / 2, (side - h) / 2, w, h))
        else:
            r.render(painter, QRectF(0, 0, side, side))
    else:
        src = QPixmap(path)
        if not src.isNull():
            src = src.scaled(int(side), int(side), Qt.KeepAspectRatio,
                             Qt.SmoothTransformation)
            painter.drawPixmap((int(side) - src.width()) // 2,
                               (int(side) - src.height()) // 2, src)


def _content_box(path):
    """Границы непрозрачной части в долях квадрата отрисовки: (x, y, w, h)."""
    box = _box_cache.get(path)
    if box is not None:
        return box

    img = QImage(_PROBE, _PROBE, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    _draw_source(p, path, _PROBE)
    p.end()

    bits = img.constBits()
    stride = img.bytesPerLine()
    x0, y0, x1, y1 = _PROBE, _PROBE, -1, -1
    for y in range(_PROBE):
        row = bits[y * stride: y * stride + _PROBE * 4]
        alpha = row[3::4]
        if not any(alpha):
            continue
        if y < y0:
            y0 = y
        y1 = y
        left = next(i for i, a in enumerate(alpha) if a)
        right = _PROBE - 1 - next(i for i, a in enumerate(reversed(alpha)) if a)
        x0 = min(x0, left)
        x1 = max(x1, right)

    if x1 < 0:                     # пустая картинка
        box = (0.0, 0.0, 1.0, 1.0)
    else:
        box = (x0 / _PROBE, y0 / _PROBE,
               (x1 - x0 + 1) / _PROBE, (y1 - y0 + 1) / _PROBE)
    _box_cache[path] = box
    return box


def pixmap(name, size, color, trim=True):
    """
    Иконка в квадрате `size`x`size` логических пикселей, залитая `color`.

    `size` — длинная сторона глифа; поля обрезаны, глиф отцентрован в квадрате.
    trim=False возвращает исходник вписанным в квадрат целиком, вместе с полями.
    """
    size = max(1, int(size))
    color = QColor(color)
    dpr = _dpr()
    key = (name, size, color.rgba(), round(dpr, 3), trim)
    pm = _cache.get(key)
    if pm is not None:
        return pm

    path = _path(name)
    if path is None:
        _missing.add(name)
        pm = QPixmap(1, 1)
        pm.fill(Qt.transparent)
        _cache[key] = pm
        return pm

    px = max(1, int(round(size * dpr)))
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)

    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    if trim:
        bx, by, bw, bh = _content_box(path)
        side = px / max(bw, bh)                  # квадрат, дающий нужный глиф
        p.translate((px - bw * side) / 2 - bx * side,
                    (px - bh * side) / 2 - by * side)
        _draw_source(p, path, side)
        p.resetTransform()
    else:
        _draw_source(p, path, px)

    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(pm.rect(), color)
    p.end()

    pm.setDevicePixelRatio(dpr)
    _cache[key] = pm
    return pm


def content_aspect(name):
    """Отношение ширины глифа к высоте — нужно, чтобы задать ширину виджету."""
    path = _path(name)
    if path is None:
        return 1.0
    _, _, w, h = _content_box(path)
    return (w / h) if h else 1.0


def missing():
    """Иконки, которых не нашлось (лог при старте)."""
    return sorted(_missing)


def clear_cache():
    _cache.clear()
