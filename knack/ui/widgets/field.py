"""
Поля ввода в теме панели.

Ввод текста отдаём штатным QLineEdit и QPlainTextEdit: курсор, выделение,
раскладки, ввод иероглифов — всё это уже есть, и переписывать его ради внешнего
вида смысла нет. Фон рисует сама вкладка, поле остаётся прозрачным.
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

from ...core import fonts
from ...core.scale import s
from .. import theme

_QSS = """
%(cls)s {
    background: transparent;
    border: none;
    padding: 0;
    color: %(text)s;
    selection-background-color: %(sel)s;
    selection-color: %(text)s;
}
%(cls)s[readOnly="true"] { color: %(dim)s; }
"""


def _style(widget, cls):
    widget.setStyleSheet(_QSS % {
        "cls": cls,
        "text": theme.current().text_bright,
        "dim": theme.current().text_secondary,
        "sel": theme.current().hover,
    })


def line_edit(parent, px=10, style="Medium", placeholder=""):
    field = QLineEdit(parent)
    field.setFont(fonts.font(s(px), style))
    field.setPlaceholderText(placeholder)
    field.setFrame(False)
    field.setAttribute(Qt.WA_MacShowFocusRect, False)
    _style(field, "QLineEdit")
    return field


def text_edit(parent, px=11, style="Medium", placeholder="", read_only=False):
    field = QPlainTextEdit(parent)
    field.setFont(fonts.font(s(px), style))
    field.setPlaceholderText(placeholder)
    field.setFrameShape(QPlainTextEdit.NoFrame)
    field.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    field.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    field.setReadOnly(read_only)
    _style(field, "QPlainTextEdit")
    return field


def restyle(field, px, style="Medium"):
    """Пересчёт при смене масштаба или темы."""
    field.setFont(fonts.font(s(px), style))
    _style(field, field.metaObject().className())
