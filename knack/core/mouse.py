"""Состояние кнопок мыши в обход Qt.

Qt знает о кнопках только из событий, которые дошли до наших окон. Панель живёт
без фокуса и часто вообще вне курсора, а во время перетаскивания ползунка
Windows забирает захват мыши при изменении размера окна — в обоих случаях
спрашивать надо систему.
"""

import ctypes

VK_LBUTTON = 0x01


def left_down():
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)
    except Exception:
        return False
