"""
Вкладка «Настройки».

Макета для неё нет — собрана в языке остальных вкладок: секции подписаны так же,
как заголовок панели, строка настройки это подпись слева и контрол справа.
Содержимое выше окна, поэтому колонка прокручивается колесом.

Настройки применяются сразу, без кнопки «Сохранить»: панель сообщает наружу
сигналом `changed(ключ)`, а KnackApp решает, что с этим делать — пересчитать
масштаб, перерегистрировать хоткей, поменять язык.
"""

import os

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter
from PySide6.QtWidgets import QFileDialog, QWidget

from ...core import autostart, fonts, i18n
from ...core.constants import APP_VERSION, BODY_R, TRANSLATE_DIR
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

FPS_OPTIONS = (0, 60, 120, 144, 165, 180)


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
        # Мышь подписи нужна ради всплывающей подсказки. Колесо она не
        # обрабатывает, поэтому прокрутка колонки уходит выше по цепочке.
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

    def text_width(self):
        return QFontMetrics(self._font).horizontalAdvance(self.text())

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
        self.scale.released.connect(self._apply_scale)
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

        self.hover_delay = Stepper(box, 0, 2000, settings.get("hover_delay_ms", 150),
                                   25, " ms")
        self.hover_delay.changed.connect(lambda v: self._set("hover_delay_ms", v))
        self._row("settings.hover_delay", self.hover_delay)

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

        # --- полка ----------------------------------------------------------- #
        self._section("settings.section.shelf")

        self.video_thumbs = Toggle(box, settings.get("shelf_video_thumbs", True))
        self.video_thumbs.toggled.connect(
            lambda v: self._set("shelf_video_thumbs", v))
        self._row("settings.video_thumbs", self.video_thumbs,
                  hint="settings.video_thumbs.hint")

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

        self.autodetect = Toggle(box, settings.get("translate_autodetect", True))
        self.autodetect.toggled.connect(
            lambda v: self._set("translate_autodetect", v))
        self._row("settings.autodetect", self.autodetect)

        self.auto_download = Toggle(box, settings.get("translate_auto_download", True))
        self.auto_download.toggled.connect(
            lambda v: self._set("translate_auto_download", v))
        self.download_row = self._row("settings.auto_download", self.auto_download)

        self.models = TextButton(box, self._models_label())
        self.models.setToolTip(self._models_tooltip())
        self.models.clicked.connect(self._pick_models_dir)
        self.models_row = self._row("settings.models_dir", self.models)

        # --- раскладка -------------------------------------------------------- #
        self._section("settings.section.layout")

        self.layout_on = Toggle(box, settings.get("layout_switch_enabled", True))
        self.layout_on.toggled.connect(self._on_layout_enabled)
        self._row("settings.layout_switch", self.layout_on,
                  hint="settings.layout_switch.hint")

        self.layout_hotkey = HotkeyField(box, settings.get("layout_hotkey", ""))
        self.layout_hotkey.changed.connect(
            lambda v: self._set("layout_hotkey", v))
        self.layout_hotkey.capturing.connect(self.capturing.emit)
        self.layout_hotkey_row = self._row("settings.layout_hotkey",
                                           self.layout_hotkey)

        self.layout_restore = Toggle(
            box, settings.get("layout_restore_clipboard", True))
        self.layout_restore.toggled.connect(
            lambda v: self._set("layout_restore_clipboard", v))
        self.layout_restore_row = self._row("settings.layout_restore",
                                            self.layout_restore)

        # --- закрепление окна -------------------------------------------------- #
        self._section("settings.section.pin")

        self.pin_on = Toggle(box, settings.get("pin_enabled", True))
        self.pin_on.toggled.connect(self._on_pin_enabled)
        self._row("settings.pin", self.pin_on, hint="settings.pin.hint")

        self.pin_hotkey = HotkeyField(box, settings.get("pin_hotkey", ""))
        self.pin_hotkey.changed.connect(lambda v: self._set("pin_hotkey", v))
        self.pin_hotkey.capturing.connect(self.capturing.emit)
        self.pin_hotkey_row = self._row("settings.pin_hotkey", self.pin_hotkey)

        self.pin_release = Toggle(box, settings.get("pin_release_on_exit", True))
        self.pin_release.toggled.connect(
            lambda v: self._set("pin_release_on_exit", v))
        self.pin_release_row = self._row("settings.pin_release", self.pin_release)

        # --- система --------------------------------------------------------- #
        self._section("settings.section.system")

        self.autostart = Toggle(box, settings.get("autostart", True))
        self.autostart.toggled.connect(self._on_autostart)
        self.autostart_row = self._row("settings.autostart", self.autostart)

        # --- инструменты ------------------------------------------------------ #
        self._section("settings.section.tools")

        self.check_updates = Toggle(box, settings.get("check_updates", True))
        self.check_updates.toggled.connect(
            lambda v: self._set("check_updates", v))
        self._row("settings.check_updates", self.check_updates,
                  hint="settings.check_updates.hint")

        self._update_ready = False   # найдено обновление — кнопка ставит его
        self._ffmpeg_busy = False    # идёт загрузка, при возврате не сбрасываем
        self.update_button = TextButton(box, i18n.t("settings.check"))
        self.update_button.clicked.connect(self._on_update_button)
        self.update_row = self._row("settings.app_update", self.update_button)
        self.update_row[0].suffix = "  " + APP_VERSION

        self.ffmpeg_button = TextButton(box, self._ffmpeg_label())
        self.ffmpeg_button.clicked.connect(
            lambda: self.changed.emit("fetch_ffmpeg"))
        self.ffmpeg_row = self._row("settings.ffmpeg", self.ffmpeg_button,
                                    hint="settings.ffmpeg.hint")

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

    def _row(self, key, control, extra=None, width=None, hint=""):
        label = _Label(self.view.content, key)
        if hint:
            tip = i18n.t(hint)
            label.setToolTip(tip)
            if control is not None:
                control.setToolTip(tip)
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
            # Подпись занимает ровно свой текст, а не всю строку: она ловит
            # мышь ради подсказки и, будучи созданной позже контрола, лежит
            # поверх него — растянутая, она перехватывала все клики.
            label_w = min(inner - s(PAD) * 2, label.text_width() + s(4))
            label.setGeometry(s(PAD), y, max(s(20), label_w), label_h)
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

    @staticmethod
    def _ffmpeg_label():
        from ...core import tools
        return i18n.t("settings.reinstall" if tools.have_ffmpeg()
                      else "settings.download")

    def _on_update_button(self):
        self.changed.emit("install_update" if self._update_ready else "check_update")

    def set_update_status(self, text, ready=None):
        """Показывает ход обновления прямо на кнопке."""
        if ready is not None:
            self._update_ready = ready
        default = i18n.t("settings.install" if self._update_ready
                         else "settings.check")
        self.update_button.set_label(text or default)

    def set_ffmpeg_status(self, text, busy=None):
        if busy is not None:
            self._ffmpeg_busy = busy
        self.ffmpeg_button.set_label(text or self._ffmpeg_label())

    def _models_label(self):
        return i18n.t("settings.choose")

    def _models_tooltip(self):
        """Полный путь показываем подсказкой: в кнопку он не влезет."""
        return str(self.settings.get("translate_models_dir") or "").strip() or TRANSLATE_DIR

    def _pick_models_dir(self):
        start = str(self.settings.get("translate_models_dir") or "") or TRANSLATE_DIR
        folder = QFileDialog.getExistingDirectory(
            self, i18n.t("settings.models_pick"), start)
        if not folder:
            return
        self.settings["translate_models_dir"] = folder
        self.models.set_label(self._models_label())
        self.models.setToolTip(self._models_tooltip())
        self.changed.emit("translate_models_dir")
        self.relayout()

    def _sync_visibility(self):
        deepl = self.settings.get("translate_backend") == "deepl"
        for widget in (self.key_box, self.key_button, self.key_row[0]):
            widget.setVisible(deepl)
        for widget in (self.auto_download, self.download_row[0],
                       self.models, self.models_row[0]):
            widget.setVisible(not deepl)

        # Сочетание и возврат буфера имеют смысл, только когда смена раскладки
        # включена.
        layout_on = bool(self.settings.get("layout_switch_enabled", True))
        for widget in (self.layout_hotkey, self.layout_hotkey_row[0],
                       self.layout_restore, self.layout_restore_row[0]):
            widget.setVisible(layout_on)

        pin_on = bool(self.settings.get("pin_enabled", True))
        for widget in (self.pin_hotkey, self.pin_hotkey_row[0],
                       self.pin_release, self.pin_release_row[0]):
            widget.setVisible(pin_on)
        # Строка без видимых частей не должна занимать место в колонке.
        self._rows = [self._with_height(row) for row in self._rows]
        self.relayout()

    def layout_row_label(self):
        """Подпись строки «Менять раскладку выделенного» — у неё та же подсказка."""
        for label, control, _extra, _h, _hint in self._rows:
            if control is self.layout_on:
                return label
        return self.layout_on

    def _on_layout_enabled(self, value):
        self._set("layout_switch_enabled", value)
        self._sync_visibility()

    def _on_pin_enabled(self, value):
        self._set("pin_enabled", value)
        self._sync_visibility()

    def _with_height(self, row):
        # Видимость берём из настройки, а не из isVisible(): пока панель не
        # показана, скрытыми числятся все дочерние виджеты разом.
        deepl = self.settings.get("translate_backend") == "deepl"
        label, control, extra, height, hint = row
        if label is self.key_row[0]:
            height = ROW_H if deepl else 0
        elif label in (self.download_row[0], self.models_row[0]):
            height = 0 if deepl else ROW_H
        elif label in (self.layout_hotkey_row[0], self.layout_restore_row[0]):
            height = ROW_H if self.settings.get("layout_switch_enabled",
                                                True) else 0
        elif label in (self.pin_hotkey_row[0], self.pin_release_row[0]):
            height = ROW_H if self.settings.get("pin_enabled", True) else 0
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
        """Пока тянут — только призрак будущего размера и цифра рядом."""
        self.settings["ui_scale"] = round(value, 2)
        self._update_scale_label()
        self.changed.emit("ui_scale_preview")

    def _apply_scale(self):
        """Отпустили — вот теперь перестраиваем панель и сохраняем."""
        self.changed.emit("ui_scale")

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
        self.models.set_label(self._models_label())
        self.models.setToolTip(self._models_tooltip())
        self.update_button.set_label(i18n.t("settings.check"))
        self.ffmpeg_button.set_label(self._ffmpeg_label())
        self.layout_on.setToolTip(i18n.t("settings.layout_switch.hint"))
        self.layout_row_label().setToolTip(i18n.t("settings.layout_switch.hint"))
        self.relayout()

    def on_show(self):
        self.key_button.set_label(i18n.t("settings.save"))
        # Загрузка идёт фоном и не прерывается закрытием панели — вернувшись,
        # человек должен увидеть текущий процент, а не «Скачать».
        if not self._ffmpeg_busy:
            self.ffmpeg_button.set_label(self._ffmpeg_label())
        self.autostart.set_checked(self.settings.get("autostart", True))

    def on_hide(self):
        self._save_key_silently()

    def _save_key_silently(self):
        text = self.key_field.text().strip()
        if text != self.settings.get("deepl_key"):
            self.settings["deepl_key"] = text
            self.changed.emit("deepl_key")
