from __future__ import annotations

import json
import queue
import tempfile
import threading
import unittest
import wave
import io
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

from app.audio import FRAME, RATE, Segmenter, SileroDetector, dbfs, normalize, to_mono_16k
from app.config import Settings
from app.engine import offer_latest
from app.history import Caption, History, export_captions, srt_time
from app.providers import APIRecognizer, Cancelled, Translator, endpoint, pcm_wav


class MockService(BaseHTTPRequestHandler):
    requests = []
    mode = "sse"

    def log_message(self, *_):
        pass

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.requests.append((self.path, body, self.headers.get("Authorization")))
        if self.mode == "error":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"secret-should-never-be-echoed"}')
            return
        self.send_response(200)
        if self.path.endswith("/audio/transcriptions"):
            content_type = "application/json"
            output = json.dumps({"text": "Hello world."}).encode()
        elif self.path.endswith("/api/chat"):
            content_type = "application/x-ndjson"
            output = b'\n'.join(json.dumps({"message": {"content": piece}}).encode() for piece in ["你好", "世界"])
        elif self.mode == "json":
            content_type = "application/json"
            output = json.dumps({"choices": [{"message": {"content": "你好世界"}}]}).encode()
        elif self.mode == "empty":
            content_type = "text/event-stream"
            output = b"data: [DONE]\n\n"
        else:
            content_type = "text/event-stream"
            output = b": ping\n\n" + b"".join(("data: " + json.dumps({"choices": [{"delta": {"content": piece}}]}) + "\n\n").encode() for piece in ["你好", "世界"]) + b"data: [DONE]\n\n"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(output)))
        self.end_headers()
        self.wfile.write(output)


class ProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockService)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()

    def setUp(self):
        MockService.requests.clear()
        MockService.mode = "sse"
        self.s = Settings(base_url=self.url, model="test")

    def test_qwen_special_payload_and_stream(self):
        partial = []
        result = Translator(self.s, "fake-test-key").translate("Hello", [("old", "旧")], threading.Event(), partial.append)
        self.assertEqual(result, "你好世界")
        path, body, auth = MockService.requests[-1]
        payload = json.loads(body)
        self.assertEqual(path, "/v1/chat/completions")
        self.assertEqual(auth, "Bearer fake-test-key")
        self.assertEqual(payload["translation_options"], {"source_lang": "auto", "target_lang": "Chinese"})
        self.assertEqual(payload["messages"], [{"role": "user", "content": "Hello"}])
        self.assertEqual(partial, ["你好", "你好世界"])

    def test_compatible_context_bounded(self):
        Translator(replace(self.s, provider="compatible")).translate("Hello", [(str(i), str(i)) for i in range(8)], threading.Event())
        payload = json.loads(MockService.requests[-1][1])
        self.assertEqual(len(payload["messages"]), 8)
        self.assertEqual(payload["messages"][-1]["content"], "Hello")

    def test_ollama_native_and_no_thinking(self):
        result = Translator(replace(self.s, provider="ollama")).translate("Hello", [], threading.Event())
        self.assertEqual(result, "你好世界")
        path, body, _ = MockService.requests[-1]
        self.assertEqual(path, "/api/chat")
        self.assertFalse(json.loads(body)["think"])

    def test_non_stream_fallback(self):
        MockService.mode = "json"
        self.assertEqual(Translator(self.s, "test").translate("Hello", [], threading.Event()), "你好世界")

    def test_error_hides_credentials(self):
        MockService.mode = "error"
        with self.assertRaisesRegex(RuntimeError, "401") as caught:
            Translator(self.s, "fake-test-key").translate("Hello", [], threading.Event())
        self.assertNotIn("secret", str(caught.exception))
        self.assertNotIn("fake-test-key", str(caught.exception))

    def test_empty_translation_is_failure(self):
        MockService.mode = "empty"
        with self.assertRaisesRegex(RuntimeError, "没有返回译文"):
            Translator(self.s, "test").translate("Hello", [], threading.Event())

    def test_cancel_and_original_only_make_no_request(self):
        stop = threading.Event()
        stop.set()
        with self.assertRaises(Cancelled):
            Translator(self.s, "test").translate("Hello", [], stop)
        self.assertEqual(Translator(replace(self.s, provider="none")).translate("Hello", [], threading.Event()), "")
        self.assertEqual(MockService.requests, [])

    def test_api_recognition_uploads_wav(self):
        recognizer = APIRecognizer(replace(self.s, asr_url=self.url, source="英语"), "test")
        self.assertEqual(recognizer.transcribe(np.zeros(RATE, np.float32)), "Hello world.")
        path, body, _ = MockService.requests[-1]
        self.assertEqual(path, "/v1/audio/transcriptions")
        self.assertIn(b"RIFF", body)
        self.assertIn(b"en", body)


class AudioTests(unittest.TestCase):
    def test_real_silero_silence(self):
        detector = SileroDetector()
        self.assertFalse(any(detector(np.zeros(FRAME, np.float32)) for _ in range(20)))

    def test_resampling_stereo(self):
        t = np.arange(4800) / 48000
        mono = np.sin(2 * np.pi * 440 * t).astype(np.float32)
        result = to_mono_16k(np.column_stack([mono, mono]).tobytes(), 2, 48000)
        self.assertEqual(len(result), 1600)
        self.assertAlmostEqual(float(np.max(result)), 1, places=2)

    def test_silence_not_amplified_and_gain_bounded(self):
        self.assertEqual(dbfs(np.zeros(100, np.float32)), -100)
        np.testing.assert_array_equal(normalize(np.zeros(100, np.float32)), np.zeros(100))
        self.assertLessEqual(float(normalize(np.ones(100, np.float32) * 0.001).max()), 0.01201)
        np.testing.assert_allclose(normalize(np.ones(100, np.float32) * 0.5), 0.5)

    def test_segment_boundaries_and_continuous_speech(self):
        segmenter = Segmenter(lambda x: x.max() > 0.1, max_seconds=2, silence_ms=200, gain=False)
        silence = np.zeros(FRAME * 10, np.float32)
        speech = np.ones(FRAME * 90, np.float32) * 0.5
        segments = segmenter.feed(np.concatenate([silence, speech, silence]))
        self.assertEqual(len(segments), 2)
        self.assertLessEqual(len(segments[0].audio), 2 * RATE)
        self.assertLessEqual(segments[0].end, segments[1].start)
        self.assertGreaterEqual(segments[0].start, 0)
        self.assertIsNone(segmenter.flush())

    def test_no_speech_no_captions(self):
        segmenter = Segmenter(lambda _: False)
        self.assertEqual(segmenter.feed(np.zeros(RATE * 5, np.float32)), [])
        self.assertIsNone(segmenter.flush())

    def test_short_click_is_discarded(self):
        segmenter = Segmenter(lambda x: x.max() > 0.1, silence_ms=200, gain=False)
        self.assertEqual(segmenter.feed(np.concatenate([np.ones(FRAME, np.float32), np.zeros(RATE, np.float32)])), [])

    def test_wav_format(self):
        with wave.open(io.BytesIO(pcm_wav(np.zeros(RATE, np.float32)))) as wav:
            self.assertEqual((wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()), (1, 2, RATE, RATE))

    def test_bounded_queue_keeps_recent(self):
        q = queue.Queue(2)
        offer_latest(q, 1)
        offer_latest(q, 2)
        self.assertEqual(offer_latest(q, 3), 1)
        self.assertEqual([q.get(), q.get()], [2, 3])


class StorageTests(unittest.TestCase):
    def test_history_updates_and_srt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            history = History(root / "history.db")
            caption = Caption(1, 1.25, 3.5, "Hello", "你好", "已完成")
            history.save("session-a", replace(caption, translation=""))
            history.save("session-a", caption)
            self.assertEqual(history.recent(), [("session-a", caption)])
            export_captions([caption], root / "result.srt")
            result = (root / "result.srt").read_text("utf-8-sig")
            self.assertIn("00:00:01,250 --> 00:00:03,500", result)
            self.assertIn("Hello\n你好", result)
            history.clear()
            self.assertEqual(history.recent(), [])
            history.close()

    def test_time_rounding(self):
        self.assertEqual(srt_time(59.9996), "00:01:00,000")

    def test_invalid_urls(self):
        for url in ("", "ftp://server", "https://user:password@host", "https://host?key=secret"):
            with self.assertRaises(ValueError):
                endpoint(url, "/api")


if __name__ == "__main__":
    unittest.main()
