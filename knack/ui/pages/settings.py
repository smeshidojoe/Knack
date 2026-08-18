"""
Вкладка «Настройки».

Макета для неё нет — собрана в языке остальных вкладок: секции подписаны так же,
как заголовок панели, строка настройки это подпись слева и контрол справа.
Содержимое выше окна, поэтому колонка прокручивается колесом.

Настройки применяются сразу, без кнопки «Сохранить»: панель сообщает наружу
сигналом `changed(ключ)`, а KnackApp решает, что с этим делать — пересчитать
масштаб, перерегистрировать хоткей, поменять язык.
"""

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from ...core import autostart, fonts, i18n
from ...core.constants import BODY_R
from ...core.scale import s, sf
from .. import theme
from ..widgets.controls import (HotkeyField, Segmented, Slider, Stepper,
                                TextButton, Toggle)
from ..widgets.field import line_edit, restyle
from .base import Page

AREA_X, AREA_Y, AREA_BOTTOM = 54, 27, 180
GUTTER = 8            # место под полосу прокрутки

SECTION_H, SECTION_PX = 18, 8
ROW_H, LABEL_PX = 26, 10
PAD = 10

SCROLL_W = 2

FPS_OPTIONS = (0, 60, 120, 144, 180)


class _Viewport(QWidget):
    """Окно прокрутки: содержимое двигается целиком, полоса рисуется поверх."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.content = QWidget(self)
        self.content.setAttribute(Qt.WA_TranslucentBackground, True)
        self._offset = 0
        self._height = 0

    def set_content_height(self, height):
        self._height = height
        self.content.setGeometry(0, -self._offset, self.width() - s(GUTTER), height)
        self._clamp()

    def max_offset(self):
        return max(0, self._height - self.height())

    def _clamp(self):
        self._offset = max(0, min(self._offset, self.max_offset()))
        self.content.move(0, -self._offset)
        self.update()

    def wheelEvent(self, event):
        if self.max_offset() <= 0:
            return
        self._offset -= event.angleDelta().y() * s(ROW_H) // 120
        self._clamp()

    def paintEvent(self, _event):
        span = self.max_offset()
        if span <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        width = sf(SCROLL_W)
        x = self.width() - width
        p.setBrush(theme.color("scroll_track"))
        p.drawRoundedRect(QRectF(x, 0, width, self.height()), width / 2, width / 2)
        visible = self.height() / max(1.0, float(self._height))
        thumb = max(sf(12), self.height() * visible)
        top = (self.height() - thumb) * (self._offset / span)
        p.setBrush(theme.color("scroll_thumb"))
        p.drawRoundedRect(QRectF(x, top, width, thumb), width / 2, width / 2)


class _Label(QWidget):
    """Подпись строки или заголовок секции."""

    def __init__(self, parent, key, section=False):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.key = key
        self.section = section
        self.suffix = ""
        self._font = None
        self.restyle()

    def restyle(self):
        if self.section:
            self._font = fonts.font(s(SECTION_PX), "Bold")
        else:
            self._font = fonts.font(s(LABEL_PX), "Medium")

    def text(self):
        return i18n.t(self.key) + self.suffix

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self._font)
        p.setPen(theme.color("text_muted" if self.section else "text_bright"))
        p.drawText(self.rect(), int(Qt.AlignLeft | Qt.AlignVCenter), self.text())


class _FieldBox(QWidget):
    """Подложка под однострочное поле ввода."""

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.color("surface"))
        r = sf(7)
        p.drawRoundedRect(QRectF(self.rect()), r, r)


class SettingsPage(Page):
    key = "settings"
    wants_keyboard = True

    changed = Signal(str)          # что поменяли: ключ настройки
    capturing = Signal(bool)       # идёт захват сочетания — глушим глобальный хоткей

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.settings = settings

        self.view = _Viewport(self)
        box = self.view.content
        self._rows = []            # (виджет-подпись, контрол, высота)

        # --- внешний вид -------------------------------------------------- #
        self._section("settings.section.look")

        self.language = Segmented(box, [(code, name) for code, name
                                        in i18n.LANGUAGES.items()],
                                  settings.get("language", "ru"))
        self.language.picked.connect(self._on_language)
        self._row("settings.language", self.language)

        self.scale = Slider(box, 0.7, 1.6, settings.get("ui_scale", 1.0), 0.05)
        self.scale.changed.connect(self._on_scale)
        self.scale_value = _Label(box, "", section=False)
        self._row("settings.scale", self.scale, extra=self.scale_value, width=120)

        self.fps = Segmented(box, self._fps_options(),
                             str(settings.get("animation_fps", 0)))
        self.fps.picked.connect(self._on_fps)
        self._row("settings.fps", self.fps)

        # --- панель --------------------------------------------------------- #
        self._section("settings.section.panel")

        self.trigger = Segmented(box, self._options(
            "settings.trigger", ("hover+hotkey", "hover", "hotkey", "tray")),
            settings.get("trigger"))
        self.trigger.picked.connect(lambda v: self._set("trigger", v))
        self._row("settings.trigger", self.trigger)

        self.hotkey = HotkeyField(box, settings.get("hotkey", ""))
        self.hotkey.changed.connect(self._on_hotkey)
        self.hotkey.capturing.connect(self.capturing.emit)
        self._row("settings.hotkey", self.hotkey)

        self.hide_mode = Segmented(box, self._options(
            "settings.hide", ("leave", "click_outside", "manual")),
            settings.get("hide_mode"))
        self.hide_mode.picked.connect(lambda v: self._set("hide_mode", v))
        self._row("settings.hide", self.hide_mode)

        self.hide_delay = Stepper(box, 0, 3000, settings.get("hide_delay_ms", 220),
                                  50, " ms")
        self.hide_delay.changed.connect(lambda v: self._set("hide_delay_ms", v))
        self._row("settings.hide_delay", self.hide_delay)

        self.monitor = Segmented(box, self._options(
            "settings.monitor", ("cursor", "primary")), settings.get("monitor"))
        self.monitor.picked.connect(lambda v: self._set("monitor", v))
        self._row("settings.monitor", self.monitor)

        self.edge_gap = Stepper(box, 0, 60, settings.get("edge_gap", 0), 2, " px")
        self.edge_gap.changed.connect(self._on_edge_gap)
        self._row("settings.edge_gap", self.edge_gap)

        # --- буфер ---------------------------------------------------------- #
        self._section("settings.section.clipboard")

        self.limit = Stepper(box, 10, 1000, settings.get("clipboard_limit", 100), 10)
        self.limit.changed.connect(lambda v: self._set("clipboard_limit", v))
        self._row("settings.clipboard_limit", self.limit)

        # --- переводчик ------------------------------------------------------ #
        self._section("settings.section.translate")

        self.backend = Segmented(box, self._options(
            "settings.backend", ("argos", "deepl")),
            settings.get("translate_backend"))
        self.backend.picked.connect(self._on_backend)
        self._row("settings.backend", self.backend)

        self.key_box = _FieldBox(box)
        self.key_field = line_edit(self.key_box, 9, "Medium",
                                   i18n.t("settings.deepl_hint"))
        self.key_field.setText(settings.get("deepl_key", ""))
        self.key_field.returnPressed.connect(self._save_key)
        self.key_button = TextButton(box, i18n.t("settings.save"))
        self.key_button.clicked.connect(self._save_key)
        self.key_row = self._row("settings.deepl_key", self.key_box,
                                 extra=self.key_button, width=250)

        self.auto_download = Toggle(box, settings.get("translate_auto_download", True))
        self.auto_download.toggled.connect(
            lambda v: self._set("translate_auto_download", v))
        self.download_row = self._row("settings.auto_download", self.auto_download)

        # --- система --------------------------------------------------------- #
        self._section("settings.section.system")

        self.autostart = Toggle(box, settings.get("autostart", True))
        self.autostart.toggled.connect(self._on_autostart)
        self.autostart_row = self._row("settings.autostart", self.autostart)

        self._sync_visibility()

    # --- сборка строк ------------------------------------------------------ #

    def _options(self, prefix, keys):
        return [(k, i18n.t("%s.%s" % (prefix, k))) for k in keys]

    def _fps_options(self):
        return [(str(v), i18n.t("settings.fps.auto") if v == 0 else str(v))
                for v in FPS_OPTIONS]

    def _section(self, key):
        label = _Label(self.view.content, key, section=True)
        self._rows.append((label, None, None, SECTION_H, 0))
        return label

    def _row(self, key, control, extra=None, width=None):
        label = _Label(self.view.content, key)
        row = (label, control, extra, ROW_H, width)
        self._rows.append(row)
        return row

    # --- геометрия --------------------------------------------------------- #

    def relayout(self):
        x, width = s(AREA_X), s(BODY_R) - s(AREA_X)
        self.view.setGeometry(x, s(AREA_Y), width, s(AREA_BOTTOM) - s(AREA_Y))
        inner = width - s(GUTTER)

        restyle(self.key_field, 9)
        y = 0
        for label, control, extra, height, hint in self._rows:
            # Скрытая строка задана нулевой высотой: полагаться на isVisible()
            # нельзя, до первого показа панели он ложен у всех виджетов.
            label_h = s(height)
            if not label_h:
                continue
            label.restyle()
            label.setGeometry(s(PAD), y, inner - s(PAD) * 2, label_h)
            if control is not None:
                if hasattr(control, "restyle"):
                    control.restyle()
                cw = s(hint) if hint else self._control_width(control)
                ch = s(getattr(control, "H", 20))
                right = inner - s(PAD)
                if extra is not None:
                    if hasattr(extra, "restyle"):
                        extra.restyle()
                    ew = self._control_width(extra)
                    eh = s(getattr(extra, "H", 20))
                    extra.setGeometry(right - ew, y + (label_h - eh) // 2, ew, eh)
                    right -= ew + s(8)
                control.setGeometry(right - cw, y + (label_h - ch) // 2, cw, ch)
                if control is self.key_box:
                    pad = s(8)
                    self.key_field.setGeometry(pad, 0, cw - pad * 2, ch)
            y += label_h
        self.view.set_content_height(y)
        self._update_scale_label()

    @staticmethod
    def _control_width(control):
        if hasattr(control, "width_hint"):
            return int(control.width_hint())
        return s(getattr(control, "W", 30))

    def _sync_visibility(self):
        deepl = self.settings.get("translate_backend") == "deepl"
        for widget in (self.key_box, self.key_button, self.key_row[0]):
            widget.setVisible(deepl)
        for widget in (self.auto_download, self.download_row[0]):
            widget.setVisible(not deepl)
        # Строка без видимых частей не должна занимать место в колонке.
        self._rows = [self._with_height(row) for row in self._rows]
        self.relayout()

    def _with_height(self, row):
        # Видимость берём из настройки, а не из isVisible(): пока панель не
        # показана, скрытыми числятся все дочерние виджеты разом.
        deepl = self.settings.get("translate_backend") == "deepl"
        label, control, extra, height, hint = row
        if label is self.key_row[0]:
            height = ROW_H if deepl else 0
        elif label is self.download_row[0]:
            height = 0 if deepl else ROW_H
        return (label, control, extra, height, hint)

    def _update_scale_label(self):
        self.scale_value.suffix = " %d%%" % round(self.scale.value * 100)
        self.scale_value.update()

    # --- обработчики -------------------------------------------------------- #

    def _set(self, key, value):
        self.settings[key] = value
        self.changed.emit(key)

    def _on_language(self, code):
        self._set("language", code)

    def _on_scale(self, value):
        self._update_scale_label()
        self._set("ui_scale", round(value, 2))

    def _on_fps(self, value):
        self._set("animation_fps", int(value))

    def _on_edge_gap(self, value):
        self._set("edge_gap", value)

    def _on_hotkey(self, combo):
        self._set("hotkey", combo)

    def _on_backend(self, value):
        self.settings["translate_backend"] = value
        self._sync_visibility()
        self.changed.emit("translate_backend")

    def _save_key(self):
        self.settings["deepl_key"] = self.key_field.text().strip()
        self.key_button.set_label(i18n.t("settings.saved"))
        self.changed.emit("deepl_key")

    def _on_autostart(self, value):
        self.settings["autostart"] = value
        autostart.set_enabled(value)
        self.changed.emit("autostart")

    # --- жизненный цикл ------------------------------------------------------ #

    def retranslate(self):
        self.trigger.set_options(self._options(
            "settings.trigger", ("hover+hotkey", "hover", "hotkey", "tray")))
        self.hide_mode.set_options(self._options(
            "settings.hide", ("leave", "click_outside", "manual")))
        self.monitor.set_options(self._options(
            "settings.monitor", ("cursor", "primary")))
        self.backend.set_options(self._options(
            "settings.backend", ("argos", "deepl")))
        self.fps.set_options(self._fps_options())
        self.key_field.setPlaceholderText(i18n.t("settings.deepl_hint"))
        self.key_button.set_label(i18n.t("settings.save"))
        self.relayout()

    def on_show(self):
        self.key_button.set_label(i18n.t("settings.save"))
        self.autostart.set_checked(self.settings.get("autostart", True))

    def on_hide(self):
        self._save_key_silently()

    def _save_key_silently(self):
        text = self.key_field.text().strip()
        if text != self.settings.get("deepl_key"):
            self.settings["deepl_key"] = text
            self.changed.emit("deepl_key")
