from __future__ import annotations

import os
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication

from app.config import Settings
from app.engine import Engine


class FakeRecognizer:
    def __init__(self, *_):
        self.count = 0

    def transcribe(self, audio):
        self.count += 1
        return f"Sentence {self.count}"


class FakeTranslator:
    def __init__(self, *_):
        pass

    def translate(self, source, context, stop, partial):
        result = "译文 " + source
        partial(result[:3])
        return result


class FakeCapture:
    dropped = 0

    def __init__(self, name, stop, on_audio, on_level, on_error):
        self.stop, self.on_audio = stop, on_audio

    def run(self):
        for _ in range(3):
            self.on_audio(np.ones(16000, np.float32) * 0.5)
            self.on_audio(np.zeros(16000, np.float32))
        self.stop.wait(3)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def pump(self, predicate, seconds=4):
        deadline = time.monotonic() + seconds
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertTrue(predicate(), "worker did not finish in time")

    def test_capture_recognition_translation_and_stop(self):
        captions, errors, finished = [], [], []
        with patch("app.engine.WhisperRecognizer", FakeRecognizer), patch("app.engine.Translator", FakeTranslator), patch("app.engine.LoopbackCapture", FakeCapture), patch("app.engine.SileroDetector", return_value=lambda audio: audio.max() > 0.01):
            engine = Engine(Settings(provider="compatible"))
            engine.caption.connect(captions.append)
            engine.error.connect(errors.append)
            engine.finished.connect(lambda: finished.append(True))
            engine.start()
            try:
                self.pump(lambda: sum(c.status == "已完成" for c in captions) == 3)
            finally:
                engine.stop()
                self.pump(lambda: bool(finished))
                engine.thread.join(1)
        self.assertEqual(errors, [])
        complete = [c for c in captions if c.status == "已完成"]
        self.assertEqual([c.id for c in complete], [1, 2, 3])
        self.assertEqual([c.translation for c in complete], ["译文 Sentence 1", "译文 Sentence 2", "译文 Sentence 3"])
        self.assertFalse(engine.thread.is_alive())

    def test_loading_can_be_stopped_before_capture(self):
        release = threading.Event()
        finished, captions = [], []

        class SlowRecognizer:
            def __init__(self, *_):
                release.wait(2)

        with patch("app.engine.WhisperRecognizer", SlowRecognizer), patch("app.engine.Translator", FakeTranslator), patch("app.engine.LoopbackCapture") as capture:
            engine = Engine(Settings())
            engine.finished.connect(lambda: finished.append(True))
            engine.caption.connect(captions.append)
            engine.start()
            engine.stop()
            release.set()
            self.pump(lambda: bool(finished))
            engine.thread.join(1)
            capture.assert_not_called()
        self.assertEqual(captions, [])


if __name__ == "__main__":
    unittest.main()
