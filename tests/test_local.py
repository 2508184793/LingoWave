from __future__ import annotations

import hashlib
import tempfile
import threading
import unittest
import numpy as np
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.download import checked_download
from app.local_translation import EmbeddedTranslator
from app.providers import Cancelled, Translator


class FakeModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.prompt = None
        self.stream_closed = False

    def token_eos(self):
        return 0

    def create_chat_completion(self, **kwargs):
        self.prompt = kwargs
        try:
            for piece in ("你好", "，世界。"):
                processor = kwargs["logits_processor"]
                logits = processor(np.array([1]), np.zeros(10, dtype=np.float32))
                if np.isneginf(logits[1:]).all():
                    break
                yield {"choices": [{"delta": {"content": piece}}]}
        finally:
            self.stream_closed = True

    def close(self):
        self.closed = True


class LocalTranslationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "model.gguf"
        self.path.write_bytes(b"GGUFfake model fixture")
        self.settings = Settings(local_model_path=str(self.path))

    def tearDown(self):
        self.temp.cleanup()

    def test_in_process_translation_uses_no_http_and_releases_model(self):
        with patch("llama_cpp.Llama", FakeModel), patch("llama_cpp.llama_supports_gpu_offload", return_value=False), patch("httpx.Client", side_effect=AssertionError("Local translation must not open HTTP")):
            translator = Translator(self.settings)
            self.assertIsNone(translator.local.model)
            partial = []
            try:
                text = translator.translate("Hello world.", [], threading.Event(), partial.append)
                model = translator.local.model
                self.assertEqual(text, "你好，世界。")
                self.assertEqual(partial, ["你好", "你好，世界。"])
                self.assertEqual(model.kwargs["n_gpu_layers"], 0)
                self.assertEqual(len(model.prompt["messages"]), 1)
                self.assertIn("Simplified Chinese", model.prompt["messages"][0]["content"])
            finally:
                translator.close()
            self.assertTrue(model.closed)
            self.assertTrue(model.stream_closed)
            self.assertIsNone(translator.local.model)
            translator.close()  # Idempotent release.

    def test_cancellation_closes_generation_stream(self):
        with patch("llama_cpp.Llama", FakeModel), patch("llama_cpp.llama_supports_gpu_offload", return_value=False):
            translator = Translator(self.settings)
            stop = threading.Event()
            try:
                with self.assertRaises(Cancelled):
                    translator.translate("Hello", [], stop, lambda _: stop.set())
                self.assertTrue(translator.local.model.stream_closed)
            finally:
                translator.close()

    def test_stopped_before_load_does_not_allocate_model(self):
        stop = threading.Event()
        stop.set()
        with patch("llama_cpp.Llama") as create:
            translator = Translator(self.settings)
            with self.assertRaises(Cancelled):
                translator.prepare(stop)
            create.assert_not_called()
            translator.close()

    def test_cancel_during_load_releases_before_return(self):
        stop = threading.Event()
        made = []

        def construct(**kwargs):
            model = FakeModel(**kwargs)
            made.append(model)
            stop.set()
            return model

        with patch("llama_cpp.Llama", side_effect=construct), patch("llama_cpp.llama_supports_gpu_offload", return_value=False):
            translator = Translator(self.settings)
            with self.assertRaises(Cancelled):
                translator.prepare(stop)
            self.assertTrue(made[0].closed)
            self.assertIsNone(translator.local.model)

    def test_explicit_gpu_requires_gpu_backend(self):
        with patch("llama_cpp.llama_supports_gpu_offload", return_value=False):
            translator = Translator(replace(self.settings, local_device="gpu"))
            with self.assertRaisesRegex(RuntimeError, "CPU 版"):
                translator.prepare(threading.Event())

    def test_missing_or_invalid_gguf_is_rejected(self):
        self.path.unlink()
        with self.assertRaisesRegex(ValueError, "尚未下载"):
            Translator(self.settings)
        self.path.write_bytes(b"not a model")
        with self.assertRaisesRegex(ValueError, "GGUF"):
            Translator(self.settings)


class DownloadHandler(BaseHTTPRequestHandler):
    payload = b"GGUF" + bytes(range(256)) * 20
    ignore_range = False
    corrupt = False
    seen_range = ""

    def log_message(self, *_):
        pass

    def do_GET(self):
        type(self).seen_range = self.headers.get("Range", "")
        offset = int(self.headers["Range"].split("=")[1].split("-")[0]) if self.headers.get("Range") and not self.ignore_range else 0
        body = self.payload[offset:]
        if self.corrupt:
            body = b"x" * len(body)
        self.send_response(206 if offset else 200)
        if offset:
            self.send_header("Content-Range", f"bytes {offset}-{len(self.payload)-1}/{len(self.payload)}")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class DownloadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DownloadHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/model"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.gguf"
        self.partial = self.path.with_suffix(".gguf.part")
        self.sha = hashlib.sha256(DownloadHandler.payload).hexdigest()
        DownloadHandler.ignore_range = DownloadHandler.corrupt = False

    def tearDown(self):
        self.temp.cleanup()

    def download(self):
        return checked_download(self.url, self.path, len(DownloadHandler.payload), self.sha, lambda _: None)

    def test_verified_resume_and_atomic_publish(self):
        self.partial.write_bytes(DownloadHandler.payload[:100])
        self.download()
        self.assertEqual(DownloadHandler.seen_range, "bytes=100-")
        self.assertEqual(self.path.read_bytes(), DownloadHandler.payload)
        self.assertFalse(self.partial.exists())

    def test_range_ignored_restarts_instead_of_appending(self):
        self.partial.write_bytes(DownloadHandler.payload[:100])
        DownloadHandler.ignore_range = True
        self.download()
        self.assertEqual(self.path.read_bytes(), DownloadHandler.payload)

    def test_corrupt_download_never_becomes_ready_model(self):
        DownloadHandler.corrupt = True
        with self.assertRaisesRegex(RuntimeError, "校验失败"):
            self.download()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.partial.exists())


if __name__ == "__main__":
    unittest.main()
