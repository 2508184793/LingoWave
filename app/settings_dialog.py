from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
                               QFormLayout, QGroupBox, QLabel, QLineEdit, QMessageBox,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .config import Settings, get_secret, put_secret
from .providers import endpoint


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("模型与字幕设置 · LingoWave")
        self.resize(690, 760)
        self.result_settings = replace(settings)
        self.s = settings
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        layout = QVBoxLayout(body)
        title = QLabel("让翻译按你的方式工作")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        intro = QLabel("语音识别和翻译独立配置。选择「仅原文」可以先测试本地识别。")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        asr = QGroupBox("01  语音识别")
        form = QFormLayout(asr)
        self.asr = QComboBox()
        for label, value in [("Whisper · 本地分句识别", "faster-whisper"), ("Qwen3-ASR · 本地分句识别（可选安装）", "qwen"), ("兼容 API · 音频转写", "api")]:
            self.asr.addItem(label, value)
        self.asr.setCurrentIndex(max(0, self.asr.findData(settings.asr_engine)))
        form.addRow("识别引擎", self.asr)
        self.whisper = QComboBox()
        self.whisper.setEditable(True)
        self.whisper.addItems(["tiny", "base", "small", "medium", "large-v3"])
        self.whisper.setCurrentText(settings.whisper_model)
        form.addRow("Whisper 模型 / 路径", self.whisper)
        self.device = QComboBox()
        self.device.addItem("CPU · INT8（默认，无需 CUDA）", "cpu")
        self.device.addItem("NVIDIA GPU · 需要 CUDA / cuDNN", "cuda")
        self.device.setCurrentIndex(max(0, self.device.findData(settings.whisper_device)))
        form.addRow("本地推理设备", self.device)
        self.qwen = QLineEdit(settings.qwen_path)
        form.addRow("Qwen 模型 / 路径", self.qwen)
        self.asr_url = QLineEdit(settings.asr_url)
        self.asr_model = QLineEdit(settings.asr_model)
        self.asr_key = QLineEdit()
        self.asr_key.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("转写 API 地址", self.asr_url)
        form.addRow("转写 API 模型", self.asr_model)
        form.addRow("转写 API Key", self.asr_key)
        note = QLabel("API 模式按短音频上传 WAV，要求兼容 /audio/transcriptions。\nQwen 在 Windows 下采用分句推理；首次使用需额外安装依赖和下载权重。")
        note.setWordWrap(True)
        note.setObjectName("muted")
        form.addRow(note)
        layout.addWidget(asr)

        translation = QGroupBox("02  翻译模型")
        tf = QFormLayout(translation)
        self.provider = QComboBox()
        for label, value in [("Qwen-MT · 翻译专用 API", "qwen-mt"), ("通用兼容 API · 云端 / 本地", "compatible"), ("Ollama · 本地模型", "ollama"), ("仅原文 · 不调用翻译", "none")]:
            self.provider.addItem(label, value)
        self.provider.setCurrentIndex(max(0, self.provider.findData(settings.provider)))
        self.url = QLineEdit(settings.base_url)
        self.model = QLineEdit(settings.model)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        tf.addRow("翻译服务", self.provider)
        tf.addRow("服务地址", self.url)
        tf.addRow("模型名称", self.model)
        tf.addRow("API Key", self.key)
        self.provider_hint = QLabel()
        self.provider_hint.setWordWrap(True)
        self.provider_hint.setObjectName("muted")
        tf.addRow(self.provider_hint)
        self.privacy = QLabel("API Key 保存在 Windows 凭据管理器。云端翻译发送识别文字；云端识别发送音频。")
        self.privacy.setWordWrap(True)
        self.privacy.setObjectName("muted")
        tf.addRow(self.privacy)
        layout.addWidget(translation)

        subtitle = QGroupBox("03  字幕与分句")
        sf = QFormLayout(subtitle)
        self.max_segment = QDoubleSpinBox()
        self.max_segment.setRange(2, 10)
        self.max_segment.setSingleStep(0.5)
        self.max_segment.setSuffix(" 秒")
        self.max_segment.setValue(settings.max_segment)
        sf.addRow("最长音频分段", self.max_segment)
        self.silence = QSpinBox()
        self.silence.setRange(200, 2000)
        self.silence.setSingleStep(50)
        self.silence.setSuffix(" ms")
        self.silence.setValue(settings.silence_ms)
        sf.addRow("停顿断句", self.silence)
        self.font_size = QSpinBox()
        self.font_size.setRange(16, 60)
        self.font_size.setValue(settings.font_size)
        sf.addRow("译文字号", self.font_size)
        self.opacity = QSpinBox()
        self.opacity.setRange(0, 100)
        self.opacity.setSuffix(" %")
        self.opacity.setValue(settings.opacity)
        sf.addRow("字幕背景不透明度", self.opacity)
        self.width = QSpinBox()
        self.width.setRange(500, 1800)
        self.width.setSingleStep(50)
        self.width.setValue(settings.overlay_width)
        sf.addRow("字幕宽度", self.width)
        self.timeout = QSpinBox()
        self.timeout.setRange(3, 120)
        self.timeout.setSuffix(" 秒")
        self.timeout.setValue(settings.subtitle_seconds)
        sf.addRow("无新字幕时清空", self.timeout)
        self.source = QCheckBox("同时显示原文")
        self.source.setChecked(settings.show_source)
        self.gain = QCheckBox("低音量自动增益（最多放大 12 倍）")
        self.gain.setChecked(settings.auto_gain)
        self.history = QCheckBox("将真实字幕历史保存在本机（默认仅保留本次内存记录）")
        self.history.setChecked(settings.remember_history)
        sf.addRow(self.source)
        sf.addRow(self.gain)
        sf.addRow(self.history)
        layout.addWidget(subtitle)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存设置")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.provider.currentIndexChanged.connect(self.preset)
        self.url.editingFinished.connect(self.load_key)
        self.asr_url.editingFinished.connect(self.load_asr_key)
        self.load_key()
        self.load_asr_key()
        self.update_hint()

    def load_key(self):
        try:
            self.key.setText(get_secret(self.provider.currentData(), self.url.text()))
        except Exception:
            self.key.clear()

    def load_asr_key(self):
        try:
            self.asr_key.setText(get_secret("asr", self.asr_url.text()))
        except Exception:
            self.asr_key.clear()

    def preset(self):
        provider = self.provider.currentData()
        if provider == "qwen-mt":
            self.url.setText("https://dashscope.aliyuncs.com/compatible-mode/v1")
            self.model.setText("qwen-mt-flash")
        elif provider == "ollama":
            self.url.setText("http://127.0.0.1:11434/v1")
            self.model.setText("hf.co/tencent/Hy-MT2-1.8B-GGUF:Q4_K_M")
        elif provider == "compatible":
            self.model.setText("")
        self.load_key()
        self.update_hint()

    def update_hint(self):
        provider = self.provider.currentData()
        self.provider_hint.setText({
            "qwen-mt": "默认地址为阿里云中国内地服务。其他区域请填写对应地址与 API Key。",
            "compatible": "填写以 /v1 结尾的服务根地址。实时字幕建议在服务端关闭深度思考。",
            "ollama": "先启动 Ollama 并下载模型。软件使用本地 /api/chat，关闭思考模式。",
            "none": "只显示语音识别原文，不产生翻译 API 费用。",
        }[provider])
        for widget in (self.url, self.model, self.key):
            widget.setEnabled(provider != "none")

    def save(self):
        try:
            s = replace(self.s)
            s.asr_engine, s.whisper_model = self.asr.currentData(), self.whisper.currentText().strip()
            s.whisper_device, s.qwen_path = self.device.currentData(), self.qwen.text().strip()
            s.asr_url, s.asr_model = self.asr_url.text().strip(), self.asr_model.text().strip()
            s.provider, s.base_url, s.model = self.provider.currentData(), self.url.text().strip(), self.model.text().strip()
            if s.provider != "none":
                endpoint(s.base_url, "/chat/completions")
                if not s.model:
                    raise ValueError("请填写翻译模型名称。")
            if s.asr_engine == "api":
                endpoint(s.asr_url, "/audio/transcriptions")
                if not s.asr_model:
                    raise ValueError("请填写转写模型名称。")
            s.max_segment, s.silence_ms = self.max_segment.value(), self.silence.value()
            s.font_size, s.opacity = self.font_size.value(), self.opacity.value()
            s.overlay_width, s.subtitle_seconds = self.width.value(), self.timeout.value()
            s.show_source, s.auto_gain, s.remember_history = self.source.isChecked(), self.gain.isChecked(), self.history.isChecked()
            put_secret(s.provider, s.base_url, self.key.text().strip())
            put_secret("asr", s.asr_url, self.asr_key.text().strip())
            s.save()
            self.result_settings = s
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self, "设置未保存", str(exc))
