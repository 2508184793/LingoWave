from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from .config import Settings


class SubtitleOverlay(QWidget):
    moved = Signal(int, int)

    def __init__(self, settings: Settings):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle("LingoWave · 悬浮字幕")
        self.s = settings
        self.drag_offset = None
        self.layout_box = QVBoxLayout(self)
        self.layout_box.setContentsMargins(24, 14, 24, 18)
        self.layout_box.setSpacing(7)
        self.tag = QLabel("LINGOWAVE  /  实时字幕")
        self.tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.source = QLabel("电脑声音，实时读懂。")
        self.translation = QLabel("播放语音后，双语字幕会显示在这里")
        for label in (self.tag, self.source, self.translation):
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.layout_box.addWidget(label)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.clear_caption)
        self.apply_settings(settings)
        self.reset_position(saved=True)

    def apply_settings(self, settings: Settings):
        self.s = settings
        self.setFixedWidth(settings.overlay_width)
        self.tag.setStyleSheet("color:#79d9ba;font:10px 'Segoe UI';letter-spacing:2px;background:transparent;")
        self.source.setStyleSheet(f"color:#c7ced4;font:{max(14, settings.font_size - 8)}px 'Microsoft YaHei UI';background:transparent;")
        self.translation.setStyleSheet(f"color:white;font:600 {settings.font_size}px 'Microsoft YaHei UI';background:transparent;")
        self.source.setVisible(settings.show_source)
        self.adjustSize()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(13, 19, 25, round(255 * self.s.opacity / 100)))
        painter.drawRoundedRect(self.rect(), 16, 16)

    def set_passthrough(self, enabled: bool):
        visible = self.isVisible()
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, enabled)
        if visible:
            self.show()

    def set_caption(self, original: str, translated: str, state: str = ""):
        self.source.setText(original)
        self.translation.setText(translated or ("正在翻译…" if state in ("等待翻译", "翻译中") else original))
        self.source.setVisible(self.s.show_source and bool(translated or state in ("等待翻译", "翻译中")))
        self.adjustSize()
        self.timer.start(self.s.subtitle_seconds * 1000)

    def clear_caption(self):
        self.source.setText("")
        self.translation.setText("")
        self.adjustSize()

    def reset_position(self, saved=False):
        screen = QApplication.primaryScreen().availableGeometry()
        x = self.s.overlay_x if saved and self.s.overlay_x >= 0 else screen.center().x() - self.width() // 2
        y = self.s.overlay_y if saved and self.s.overlay_y >= 0 else screen.bottom() - 220
        self.move(max(screen.left(), min(x, screen.right() - self.width())), max(screen.top(), min(y, screen.bottom() - self.height())))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self.drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.drag_offset is not None:
            self.drag_offset = None
            self.moved.emit(self.x(), self.y())
