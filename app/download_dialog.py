from __future__ import annotations

import sys

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QComboBox, QDialog, QLabel, QPushButton, QVBoxLayout

from .config import DEFAULT_LOCAL_MODEL, ROOT
from .download import WHISPER_MODELS


class ModelDownloadDialog(QDialog):
    def __init__(self, whisper_model="small", kind="whisper", parent=None):
        super().__init__(parent)
        self.setWindowTitle("下载本地模型 · LingoWave")
        self.resize(580, 410)
        self.completed = False
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(ROOT))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.finished.connect(self.finished_download)
        self.process.errorOccurred.connect(lambda _: self.log.setText("下载进程无法启动或已中断，请重试。"))
        self.output = ""
        box = QVBoxLayout(self)
        self.kind = QComboBox()
        self.kind.addItem("语音识别 · Whisper", "whisper")
        self.kind.addItem("本地翻译 · Hy-MT2-1.8B Q4_K_M", "translation")
        self.kind.setCurrentIndex(max(0, self.kind.findData(kind)))
        box.addWidget(self.kind)
        self.model = QComboBox()
        self.model.addItems(WHISPER_MODELS)
        self.model.setCurrentText(whisper_model)
        box.addWidget(self.model)
        self.source = QComboBox()
        self.source.addItem("Hugging Face", "huggingface")
        self.source.addItem("ModelScope", "modelscope")
        box.addWidget(self.source)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setObjectName("muted")
        box.addWidget(self.info)
        self.log = QLabel("等待开始…")
        self.log.setWordWrap(True)
        self.log.setObjectName("muted")
        box.addWidget(self.log, 1)
        self.start_button = QPushButton("下载模型")
        self.start_button.setMinimumHeight(38)
        self.start_button.clicked.connect(self.start_download)
        box.addWidget(self.start_button)
        self.kind.currentIndexChanged.connect(self.update_kind)
        self.update_kind()

    def update_kind(self):
        local = self.kind.currentData() == "translation"
        self.model.setVisible(not local)
        self.info.setText("翻译模型约 1.1GB，来自腾讯官方仓库。支持断点续传及 SHA-256 校验，下载后可离线使用。关闭此窗口会停止下载。"
                          if local else "下载 Whisper 识别权重，small 约 0.5GB。ModelScope 使用社区转换仓库。关闭此窗口会停止下载。")

    def start_download(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            return
        self.output = ""
        self.completed = False
        self.process.setProgram(sys.executable)
        self.process.setArguments(["-X", "utf8", "-u", "-m", "app.download", "--kind", self.kind.currentData(),
                                   "--model", self.model.currentText(), "--source", self.source.currentData()])
        for control in (self.kind, self.model, self.source, self.start_button):
            control.setEnabled(False)
        self.log.setText("正在连接下载源…")
        self.process.start()

    def read_output(self):
        self.output = (self.output + bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace"))[-5000:]
        self.log.setText("\n".join(self.output.splitlines()[-8:]))

    def finished_download(self, code, _status):
        self.read_output()
        self.completed = code == 0
        for control in (self.kind, self.model, self.source, self.start_button):
            control.setEnabled(True)
        self.start_button.setText("重新校验模型" if self.completed else "重试下载")
        if self.completed:
            self.log.setText("模型已下载并校验完成。关闭此窗口后即可开始监听。\n" + (str(ROOT / DEFAULT_LOCAL_MODEL) if self.kind.currentData() == "translation" else self.log.text()))

    def closeEvent(self, event):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(1500):
                self.process.kill()
                self.process.waitForFinished(1000)
        super().closeEvent(event)
