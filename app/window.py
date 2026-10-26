from __future__ import annotations

import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFrame,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QProgressBar, QPushButton, QFileDialog, QScrollArea, QVBoxLayout, QWidget, QLayout)

from .audio import devices
from .config import DATA_DIR, LANGUAGES, Settings, get_secret
from .engine import Engine
from .history import Caption, History, export_captions
from .hotkeys import GlobalHotkeys
from .overlay import SubtitleOverlay
from .providers import Cancelled, Translator
from .download_dialog import ModelDownloadDialog
from .settings_dialog import SettingsDialog


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, name=None):
    widget = QPushButton(text)
    widget.setMinimumHeight(44 if name == "primary" else 34)
    if name:
        widget.setObjectName(name)
    widget.clicked.connect(callback)
    return widget


def card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return frame, layout


class CaptionRow(QWidget):
    def __init__(self, caption: Caption, session: str):
        super().__init__()
        self.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 14)
        layout.setSpacing(7)
        top = QHBoxLayout()
        self.time = label(f"{int(caption.start)//60:02}:{int(caption.start)%60:02}  ·  {'演示' if session.startswith('demo') else '语音字幕'}", "muted")
        self.state = label(caption.status, "muted")
        top.addWidget(self.time)
        top.addStretch()
        top.addWidget(self.state)
        layout.addLayout(top)
        self.original = label(caption.source)
        self.original.setWordWrap(True)
        self.original.setStyleSheet("color:#9eafbc;font-size:13px;")
        self.translated = label("")
        self.translated.setStyleSheet("color:#eaf3ef;font-size:16px;font-weight:500;")
        self.translated.setWordWrap(True)
        self.original.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.translated.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.original)
        layout.addWidget(self.translated)
        self.update_caption(caption)

    def update_caption(self, caption):
        self.state.setText(caption.status)
        self.translated.setText(caption.translation or ("正在翻译…" if caption.status in ("等待翻译", "翻译中") else ""))
        self.translated.setVisible(bool(self.translated.text()))


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings | None = None, test_mode=False):
        super().__init__()
        self.s = settings or Settings.load()
        self.test_mode = test_mode
        self.engine = None
        self.session = ""
        self.latest_key = None
        self.records: dict[tuple[str, int], Caption] = {}
        self.rows: dict[tuple[str, int], tuple] = {}
        self.history = History(DATA_DIR / "history.sqlite3") if self.s.remember_history and not test_mode else None
        self.demo_timer = QTimer(self)
        self.demo_timer.timeout.connect(self.demo_tick)
        self.demo_index = 0
        self.closing = False
        self.setWindowTitle("LingoWave · 大模型实时翻译")
        self.resize(1220, 850)
        self.setMinimumSize(1040, 740)
        self.overlay = SubtitleOverlay(self.s)
        self.overlay.moved.connect(self.overlay_moved)
        self.build_ui()
        self.refresh_devices()
        self.refresh_summary()
        if self.history:
            for session, caption in self.history.recent():
                self.receive_caption(session, caption, persist=False, display=False)
        self.hotkeys = GlobalHotkeys(QApplication.instance(), self, {
            0x77: self.toggle_listening, 0x78: self.toggle_overlay,
            0x79: lambda: self.passthrough.setChecked(not self.passthrough.isChecked()),
        }) if not test_mode else None
        if self.hotkeys and self.hotkeys.failed:
            self.statusBar().showMessage("部分全局快捷键被其他程序占用，已退回窗口内快捷键。")

    def build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        rail = QFrame()
        rail.setObjectName("rail")
        rail.setFixedWidth(178)
        nav = QVBoxLayout(rail)
        nav.setContentsMargins(22, 28, 22, 22)
        nav.setSpacing(12)
        mark = label("◉", "brand")
        mark.setStyleSheet("color:#8de0bb;font-size:38px;")
        nav.addWidget(mark)
        nav.addWidget(label("LingoWave", "brand"))
        nav.addWidget(label("桌面实时翻译", "muted"))
        nav.addSpacing(35)
        active = label("  ●   实时翻译")
        active.setStyleSheet("background:#1c352d;color:#a6e6ca;border-radius:8px;padding:12px 4px;")
        nav.addWidget(active)
        nav.addWidget(button("模型与字幕", self.open_settings, "quiet"))
        nav.addWidget(button("下载模型", self.download_model, "quiet"))
        nav.addStretch()
        nav.addWidget(label("LOCAL + CLOUD", "eyebrow"))
        tagline = label("声音留在当下\n语言不再设限", "muted")
        tagline.setStyleSheet("color:#728996;line-height:1.5;")
        nav.addWidget(tagline)
        nav.addSpacing(14)
        nav.addWidget(label("DESKTOP  /  v0.2", "muted"))
        root.addWidget(rail)

        area = QWidget()
        page = QVBoxLayout(area)
        page.setContentsMargins(28, 28, 28, 18)
        page.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(label("LISTEN. TRANSLATE. UNDERSTAND.", "eyebrow"))
        heading.addWidget(label("让每一句，都听得懂。", "hero"))
        heading.addWidget(label("捕获电脑声音，将世界的语言变成眼前的字幕。", "muted"))
        header.addLayout(heading)
        header.addStretch()
        self.badge = label("●  准备就绪", "badge")
        header.addWidget(self.badge, alignment=Qt.AlignmentFlag.AlignTop)
        page.addLayout(header)

        columns = QHBoxLayout()
        columns.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(16)
        input_card, input_box = card()
        input_box.addWidget(label("01  声音与语言", "sectionTitle"))
        device_row = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setMinimumContentsLength(15)
        self.device_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.refresh_button = button("刷新", self.refresh_devices, "quiet")
        device_row.addWidget(self.device_combo, 1)
        device_row.addWidget(self.refresh_button)
        input_box.addLayout(device_row)
        languages = QHBoxLayout()
        self.source_combo = QComboBox()
        self.source_combo.addItems(LANGUAGES.keys())
        self.source_combo.setCurrentText(self.s.source)
        self.target_combo = QComboBox()
        self.target_combo.addItems(k for k in LANGUAGES if k != "自动检测")
        self.target_combo.setCurrentText(self.s.target)
        languages.addWidget(self.source_combo, 1)
        languages.addWidget(label("  →  ", "muted"))
        languages.addWidget(self.target_combo, 1)
        input_box.addLayout(languages)
        left.addWidget(input_card)

        preview, preview_box = card()
        preview_top = QHBoxLayout()
        preview_top.addWidget(label("02  字幕预览", "sectionTitle"))
        preview_top.addStretch()
        self.preview_tag = label("等待语音", "muted")
        preview_top.addWidget(self.preview_tag)
        preview_box.addLayout(preview_top)
        self.preview_source = label("从一段视频、一场直播，或一次会议开始。")
        self.preview_source.setStyleSheet("color:#8fa6b5;font-size:14px;")
        self.preview_source.setWordWrap(True)
        self.preview_translation = label("播放声音，让翻译自然发生。")
        self.preview_translation.setStyleSheet("color:#e5f7ed;font-size:23px;font-weight:600;")
        self.preview_translation.setWordWrap(True)
        preview_box.addSpacing(8)
        preview_box.addWidget(self.preview_source)
        preview_box.addWidget(self.preview_translation)
        preview_box.addSpacing(8)
        left.addWidget(preview)

        transcript_header = QHBoxLayout()
        transcript_header.addWidget(label("字幕记录", "sectionTitle"))
        self.count_label = label("0 条", "muted")
        transcript_header.addWidget(self.count_label)
        transcript_header.addStretch()
        transcript_header.addWidget(button("导出本次", self.export_history, "quiet"))
        transcript_header.addWidget(button("清空", self.clear_history, "quiet"))
        left.addLayout(transcript_header)
        self.empty_hint = label("还没有字幕。点击「字幕演示」可先看看显示效果。", "muted")
        self.empty_hint.setWordWrap(True)
        left.addWidget(self.empty_hint)
        self.transcripts = QListWidget()
        self.transcripts.setSpacing(2)
        self.transcripts.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        left.addWidget(self.transcripts, 1)
        columns.addLayout(left, 1)

        right_widget = QWidget()
        right_widget.setFixedWidth(280)
        right = QVBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(16)
        right.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        control, controls = card()
        controls.addWidget(label("翻译控制", "sectionTitle"))
        self.start_button = button("▶  开始监听", self.toggle_listening, "primary")
        self.probe_button = button("声音检测 / 静音测试", self.toggle_probe)
        self.demo_button = button("字幕演示 · 无需 API", self.start_demo, "quiet")
        controls.addWidget(self.start_button)
        controls.addWidget(self.probe_button)
        controls.addWidget(self.demo_button)
        controls.addSpacing(6)
        meter_header = QHBoxLayout()
        meter_header.addWidget(label("系统声音电平", "muted"))
        meter_header.addStretch()
        self.level_label = label("— dBFS", "muted")
        meter_header.addWidget(self.level_label)
        controls.addLayout(meter_header)
        self.meter = QProgressBar()
        self.meter.setRange(0, 60)
        self.meter.setValue(0)
        self.meter.setTextVisible(False)
        controls.addWidget(self.meter)
        self.signal_hint = label("选择声音检测，验证当前输出设备。", "muted")
        self.signal_hint.setWordWrap(True)
        controls.addWidget(self.signal_hint)
        right.addWidget(control)

        model_card, model_box = card()
        model_box.addWidget(label("当前模型", "sectionTitle"))
        model_box.addWidget(label("语音识别", "eyebrow"))
        self.asr_summary = label("")
        self.asr_summary.setWordWrap(True)
        model_box.addWidget(self.asr_summary)
        model_box.addWidget(label("文字翻译", "eyebrow"))
        self.translation_summary = label("")
        self.translation_summary.setWordWrap(True)
        model_box.addWidget(self.translation_summary)
        self.settings_button = button("配置翻译模型", self.open_settings, "quiet")
        self.test_button = button("测试翻译", self.test_translation, "quiet")
        model_box.addWidget(self.settings_button)
        model_box.addWidget(self.test_button)
        right.addWidget(model_card)

        overlay_box = QHBoxLayout()
        self.show_overlay = QCheckBox("显示桌面字幕")
        self.show_overlay.setChecked(True)
        self.show_overlay.toggled.connect(self.overlay.setVisible)
        self.passthrough = QCheckBox("鼠标穿透")
        self.passthrough.toggled.connect(self.overlay.set_passthrough)
        overlay_box.addWidget(self.show_overlay)
        overlay_box.addWidget(self.passthrough)
        overlay_box.addStretch()
        overlay_box.addWidget(button("重置字幕位置", self.overlay.reset_position, "quiet"))
        preview_box.addLayout(overlay_box)
        shortcuts = label("Ctrl+Alt+F8 监听 · F9 字幕 · F10 穿透", "muted")
        shortcuts.setStyleSheet("color:#728996;font-size:10px;")
        shortcuts.setToolTip("Ctrl + Alt + F8：开始 / 停止监听\nCtrl + Alt + F9：显示 / 隐藏字幕\nCtrl + Alt + F10：开关鼠标穿透")
        right.addWidget(shortcuts)
        right.addStretch()
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setFixedWidth(292)
        right_scroll.setWidget(right_widget)
        columns.addWidget(right_scroll)
        page.addLayout(columns, 1)
        self.message = label("选择本地识别与内嵌翻译后，无需第三方软件或 API Key。", "muted")
        self.message.setWordWrap(True)
        page.addWidget(self.message)
        root.addWidget(area, 1)
        self.statusBar().showMessage("就绪 · 默认不保存音频，字幕历史可在设置中开启")

    def notify(self, text, error=False):
        self.message.setText(text)
        self.message.setStyleSheet("color:#f2b3a5;" if error else "color:#8fa5b4;")

    def refresh_devices(self):
        try:
            selected = self.device_combo.currentData() or self.s.device_name
            self.device_combo.clear()
            self.device_combo.addItem("跟随当前默认输出设备（启动时选择）", "")
            for device in devices():
                self.device_combo.addItem(device["name"].replace(" [Loopback]", ""), device["name"])
            index = self.device_combo.findData(selected)
            self.device_combo.setCurrentIndex(max(0, index))
            self.device_combo.setToolTip("监听所选输出设备的全部声音；切换耳机后请停止、刷新并重新开始。")
        except Exception as exc:
            self.notify(f"无法列出声音设备：{exc}", True)

    def refresh_summary(self):
        asr = {"faster-whisper": f"Whisper {self.s.whisper_model} · {self.s.whisper_device.upper()}", "qwen": f"Qwen3-ASR · {self.s.whisper_device.upper()}", "api": f"转写 API · {self.s.asr_model}"}
        self.asr_summary.setText(asr.get(self.s.asr_engine, "Whisper"))
        self.translation_summary.setText("仅显示原文" if self.s.provider == "none" else
                                         f"内嵌 · {Path(self.s.local_model_path).stem}" if self.s.provider == "embedded" else self.s.model)

    def save_inputs(self):
        self.s.device_name = self.device_combo.currentData() or ""
        self.s.source, self.s.target = self.source_combo.currentText(), self.target_combo.currentText()
        if not self.test_mode:
            self.s.save()

    def open_settings(self):
        if self.engine is not None or (hasattr(self, "_test_thread") and self._test_thread.is_alive()):
            self.notify("请先停止监听或等待翻译测试结束，再修改模型和字幕设置。")
            return
        self.save_inputs()
        dialog = SettingsDialog(self.s, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.s = dialog.result_settings
            self.overlay.apply_settings(self.s)
            self.refresh_summary()
            if self.s.remember_history and self.history is None:
                self.history = History(DATA_DIR / "history.sqlite3")
            elif not self.s.remember_history and self.history:
                self.history.close()
                self.history = None
            self.notify("设置已保存。" + ("内嵌翻译会随监听启动、停止，不需要其他软件。" if self.s.provider == "embedded" else "API Key 存放在 Windows 凭据管理器。"))

    def keys(self):
        key = "" if self.s.provider in ("embedded", "none") else get_secret(self.s.provider, self.s.base_url)
        asr_key = get_secret("asr", self.s.asr_url) if self.s.asr_engine == "api" else ""
        return key, asr_key

    def toggle_listening(self):
        if hasattr(self, "_test_thread") and self._test_thread.is_alive():
            self.notify("请等待翻译测试结束后再开始监听。")
            return
        if self.engine:
            self.engine.stop()
            self.start_button.setEnabled(False)
            self.probe_button.setEnabled(False)
            return
        self.start_session(probe=False)

    def toggle_probe(self):
        if self.engine:
            self.toggle_listening()
        else:
            self.start_session(probe=True)

    def start_session(self, probe=False):
        if hasattr(self, "_test_thread") and self._test_thread.is_alive():
            self.notify("请等待翻译测试释放模型后再开始。")
            return
        self.demo_timer.stop()
        self.save_inputs()
        try:
            key, asr_key = ("", "") if probe else self.keys()
            if not probe:
                Translator(self.s, key)  # Fail early before loading a local model.
        except Exception as exc:
            self.notify(str(exc), True)
            return
        self.session = datetime.now().isoformat(timespec="seconds") + "-" + uuid.uuid4().hex[:6]
        engine = Engine(self.s, key, asr_key, probe, self)
        self.engine = engine
        engine.status.connect(lambda text: self.notify(text) if self.engine is engine else None)
        engine.error.connect(lambda text: self.notify(text, True) if self.engine is engine else None)
        engine.level.connect(lambda value: self.update_level(value) if self.engine is engine else None)
        session = self.session
        engine.caption.connect(lambda caption: self.receive_caption(session, caption) if self.engine is engine else None)
        engine.metrics.connect(lambda delay, dropped: self.statusBar().showMessage(f"分句后处理耗时 {delay:.1f}s  ·  已跳过 {dropped} 段  ·  音频不落盘") if self.engine is engine else None)
        engine.finished.connect(lambda: self.session_finished(engine))
        self.set_running(True, probe)
        self.notify("正在打开声音设备…" if probe else "正在准备模型…")
        if self.show_overlay.isChecked() and not probe:
            self.overlay.clear_caption()
            self.overlay.show()
        engine.start()

    def set_running(self, running, probe=False):
        self.start_button.setText("■  停止监听" if running else "▶  开始监听")
        self.start_button.setEnabled(True)
        self.probe_button.setText("■  停止声音检测" if running and probe else "声音检测 / 静音测试")
        self.probe_button.setEnabled(not running or probe)
        for widget in (self.device_combo, self.refresh_button, self.source_combo, self.target_combo, self.settings_button, self.demo_button, self.test_button):
            widget.setEnabled(not running)
        self.badge.setText("●  声音检测中" if running and probe else "●  正在监听" if running else "●  准备就绪")

    def session_finished(self, engine):
        if self.engine is not engine:
            return
        self.engine = None
        for (session, _), caption in list(self.records.items()):
            if session == self.session and caption.status in ("等待翻译", "翻译中"):
                self.receive_caption(session, replace(caption, status="已停止"), display=False)
        self.set_running(False)
        self.meter.setValue(0)
        self.level_label.setText("— dBFS")
        self.statusBar().showMessage("已停止 · 模型资源已释放，可重新开始")
        engine.deleteLater()
        if self.closing:
            self.close()

    def update_level(self, value):
        self.level_label.setText(f"{value:.0f} dBFS")
        self.meter.setValue(max(0, min(60, int(value + 60))))
        self.signal_hint.setText("检测到内部音频信号。" if value > -55 else "暂无声音信号；请播放语音并确认输出设备。")

    def receive_caption(self, session, caption, persist=True, display=True):
        key = (session, caption.id)
        new = key not in self.records
        self.records[key] = caption
        near_bottom = self.transcripts.verticalScrollBar().maximum() - self.transcripts.verticalScrollBar().value() < 70
        if key not in self.rows:
            item = QListWidgetItem()
            row = CaptionRow(caption, session)
            self.transcripts.addItem(item)
            self.transcripts.setItemWidget(item, row)
            self.rows[key] = (item, row)
            if display:
                self.latest_key = key
        item, row = self.rows[key]
        row.setFixedWidth(max(200, self.transcripts.viewport().width() - 8))
        row.update_caption(caption)
        item.setSizeHint(row.sizeHint())
        if new and near_bottom:
            self.transcripts.scrollToBottom()
        # Cap visible/memory history, keeping the latest 300 captions.
        if len(self.rows) > 300:
            oldest = next(iter(self.rows))
            old_item, _ = self.rows.pop(oldest)
            self.transcripts.takeItem(self.transcripts.row(old_item))
            self.records.pop(oldest, None)
        self.count_label.setText(f"{len(self.rows)} 条")
        self.empty_hint.hide()
        if display and key == self.latest_key:
            self.preview_source.setText(caption.source)
            self.preview_translation.setText(caption.translation or ("正在翻译…" if caption.status in ("等待翻译", "翻译中") else caption.source))
            self.preview_tag.setText(caption.status)
            self.overlay.set_caption(caption.source, caption.translation, caption.status)
        if persist and self.history and not session.startswith("demo") and caption.status != "翻译中":
            self.history.save(session, caption)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "transcripts"):
            QTimer.singleShot(0, self.reflow_rows)

    def reflow_rows(self):
        for item, row in self.rows.values():
            row.setFixedWidth(max(200, self.transcripts.viewport().width() - 8))
            item.setSizeHint(row.sizeHint())

    def start_demo(self):
        if self.engine:
            return
        self.demo_timer.stop()
        self.demo_index = 0
        self.session = "demo-" + uuid.uuid4().hex[:6]
        self.notify("字幕演示中：这些是预设示例，不会录音，也不会调用 API。")
        self.badge.setText("●  字幕演示")
        if self.show_overlay.isChecked():
            self.overlay.show()
        self.demo_tick()
        self.demo_timer.start(3200)

    def demo_tick(self):
        samples = [
            ("Every voice opens a window to a different world.", "每一种声音，都打开一扇通往不同世界的窗。"),
            ("You can mute your speakers and still follow the conversation.", "即使听不到扬声器的声音，也能通过字幕跟上对话。"),
            ("Let's make language feel a little less like a barrier.", "让语言少一点隔阂，让理解多一点自然。"),
        ]
        if self.demo_index >= len(samples):
            self.demo_timer.stop()
            self.badge.setText("●  准备就绪")
            self.notify("演示结束。配置模型后，点击「开始监听」使用真实语音翻译。")
            return
        source, translated = samples[self.demo_index]
        index = self.demo_index
        self.demo_index += 1
        self.receive_caption(self.session, Caption(index + 1, index * 3.2, index * 3.2 + 3, source, translated, "演示"))

    def toggle_overlay(self):
        self.show_overlay.setChecked(not self.show_overlay.isChecked())

    def overlay_moved(self, x, y):
        self.s.overlay_x, self.s.overlay_y = x, y
        if not self.test_mode:
            self.s.save()

    def export_history(self):
        session = self.session
        captions = [c for (s, _), c in self.records.items() if s == session]
        if not captions and self.records:
            session = next(reversed(self.records))[0]
            captions = [c for (s, _), c in self.records.items() if s == session]
        if not captions:
            self.notify("当前没有可导出的字幕。")
            return
        path, _ = QFileDialog.getSaveFileName(self, "导出当前会话字幕", f"LingoWave-{datetime.now():%Y%m%d-%H%M%S}.srt", "字幕文件 (*.srt);;文本文件 (*.txt)")
        if path:
            try:
                export_captions(sorted(captions, key=lambda c: c.start), Path(path))
                self.notify(f"已导出 {len(captions)} 条字幕：{path}")
            except OSError as exc:
                self.notify(f"导出失败：{exc}", True)

    def clear_history(self):
        if self.engine:
            self.notify("请先停止监听，再清空历史记录。")
            return
        self.demo_timer.stop()
        if self.history and QMessageBox.question(self, "清空历史", "清空本机保存的全部字幕历史？") != QMessageBox.StandardButton.Yes:
            return
        if self.history:
            self.history.clear()
        self.records.clear()
        self.rows.clear()
        self.latest_key = None
        self.transcripts.clear()
        self.count_label.setText("0 条")
        self.empty_hint.show()
        self.overlay.clear_caption()
        self.notify("字幕记录已清空。")

    def test_translation(self):
        if self.engine:
            return
        self.save_inputs()
        try:
            key, _ = self.keys()
            translator = Translator(self.s, key)
            if self.s.provider == "none":
                self.notify("当前为仅原文模式，无需测试翻译连接。")
                return
        except Exception as exc:
            self.notify(str(exc), True)
            return
        # Reuse Engine's queued Qt signals for a short, audio-free connectivity test.
        signals = Engine(self.s, parent=self)
        self._test_signals = signals
        self.test_button.setEnabled(False)
        self.start_button.setEnabled(False)
        self.notify("正在测试翻译 · Hello, world.…")
        signals.status.connect(self.notify)
        signals.error.connect(lambda text: self.notify(text, True))

        def done():
            self.test_button.setEnabled(True)
            self.start_button.setEnabled(True)
            signals.deleteLater()
            if self.closing:
                QTimer.singleShot(50, self.close)

        signals.finished.connect(done)

        def run():
            try:
                translator.prepare(signals.stop_event, signals.status.emit)
                text = translator.translate("Hello, world.", [], signals.stop_event)
                signals.status.emit(f"翻译成功 · {text}")
            except Cancelled:
                pass
            except Exception as exc:
                signals.error.emit(str(exc))
            finally:
                try:
                    translator.close()
                finally:
                    signals.finished.emit()

        self._test_thread = threading.Thread(target=run, daemon=True)
        self._test_thread.start()

    def download_model(self):
        if self.engine:
            self.notify("请先停止监听，再下载模型。")
            return
        dialog = ModelDownloadDialog(self.s.whisper_model, "translation" if self.s.provider == "embedded" else "whisper", self)
        dialog.exec()
        if dialog.completed:
            self.notify("本地模型已准备好，可以开始监听。")

    def closeEvent(self, event):
        if self.engine:
            self.closing = True
            self.engine.stop()
            self.notify("正在停止监听并释放模型，完成后关闭窗口…")
            event.ignore()
            return
        if hasattr(self, "_test_thread") and self._test_thread.is_alive():
            self.closing = True
            self._test_signals.stop_event.set()
            self.notify("正在结束翻译连接测试，请稍候再关闭。")
            event.ignore()
            return
        self.demo_timer.stop()
        self.overlay.close()
        self.save_inputs()
        if self.hotkeys:
            self.hotkeys.close()
        if self.history:
            self.history.close()
        event.accept()
