from __future__ import annotations

import os
import unittest
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.config import Settings
from app.history import Caption
from app.settings_dialog import SettingsDialog
from app.style import STYLE
from app.window import MainWindow


class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.window = MainWindow(Settings(provider="none"), test_mode=True)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_late_translation_does_not_replace_newer_caption(self):
        a = Caption(1, 0, 2, "first")
        b = Caption(2, 2, 4, "second")
        self.window.receive_caption("a", a)
        self.window.receive_caption("a", b)
        self.window.receive_caption("a", replace(a, translation="较早译文", status="已完成"))
        self.assertEqual(self.window.preview_source.text(), "second")
        self.assertEqual(len(self.window.records), 2)
        self.assertEqual(self.window.records[("a", 1)].translation, "较早译文")

    def test_demo_is_marked_and_not_persisted(self):
        self.window.start_demo()
        self.assertTrue(self.window.session.startswith("demo"))
        self.assertEqual(len(self.window.records), 1)
        self.assertEqual(next(iter(self.window.records.values())).status, "演示")
        self.assertIsNone(self.window.history)
        self.assertGreaterEqual(self.window.start_button.height(), 44)

    def test_passthrough_can_be_recovered_from_main_window(self):
        self.window.passthrough.setChecked(True)
        self.assertTrue(self.window.overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        self.window.passthrough.setChecked(False)
        self.assertFalse(self.window.overlay.windowFlags() & Qt.WindowType.WindowTransparentForInput)

    def test_settings_presets(self):
        dialog = SettingsDialog(self.window.s, self.window)
        dialog.provider.setCurrentIndex(dialog.provider.findData("ollama"))
        self.assertEqual(dialog.url.text(), "http://127.0.0.1:11434/v1")
        self.assertIn("Hy-MT2-1.8B", dialog.model.text())
        dialog.provider.setCurrentIndex(dialog.provider.findData("none"))
        self.assertFalse(dialog.url.isEnabled())
        dialog.close()


if __name__ == "__main__":
    unittest.main()
