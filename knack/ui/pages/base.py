"""Общий предок вкладок."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget


class Page(QWidget):
    key = ""        # ключ вкладки, совпадает с ключом в tabbar.TABS

    # Вкладкам с полями ввода панель отдаёт фокус: по умолчанию окно его не
    # берёт, чтобы не сбивать набор текста в активной программе.
    wants_keyboard = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    def relayout(self):
        """Пересчёт геометрии под текущий масштаб. Вызывается при показе и
        при смене экрана — координаты макета живут только здесь."""

    def retranslate(self):
        """Сменили язык интерфейса: перечитать строки."""

    def on_show(self):
        """Панель открылась и вкладка активна: можно запускать таймеры."""

    def on_hide(self):
        """Вкладка спрятана: таймеры и опросы нужно остановить."""
