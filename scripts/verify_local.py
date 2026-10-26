"""Real, offline ASR -> embedded translation -> cancellation and model release."""
from __future__ import annotations

import gc
import json
import os
import sys
import threading
import time
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import ROOT, Settings
from app.providers import Cancelled, Translator, WhisperRecognizer


def resident_mb():
    try:
        import psutil
        return round(psutil.Process().memory_info().rss / 1024**2, 1)
    except ImportError:
        return None


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    source_file = ROOT / "artifacts" / "test-speech.wav"
    if not source_file.exists():
        raise SystemExit("Generate the local test WAV with scripts/make-speech.ps1 first.")
    with wave.open(str(source_file)) as handle:
        rate, channels = handle.getframerate(), handle.getnchannels()
        audio = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2").astype(np.float32) / 32768
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != 16000:
        import math
        divisor = math.gcd(rate, 16000)
        audio = resample_poly(audio, 16000 // divisor, rate // divisor)
    settings = Settings(source="英语", local_device="cpu")
    asr = translator = None
    report = {"offline": True, "http_requests_allowed": False, "backend": "CPU", "rss_before_mb": resident_mb()}
    try:
        with patch("httpx.Client", side_effect=AssertionError("Offline verification must not use HTTP")):
            asr = WhisperRecognizer(settings, print)
            translator = Translator(settings)
            started = time.monotonic()
            translator.prepare(threading.Event(), print)
            report["load_seconds"] = round(time.monotonic() - started, 3)
            started = time.monotonic()
            original = asr.transcribe(audio)
            report["asr_seconds"] = round(time.monotonic() - started, 3)
            started = time.monotonic()
            translated = translator.translate(original, [], threading.Event())
            report["translation_seconds"] = round(time.monotonic() - started, 3)
            report.update(original=original, translated=translated, rss_loaded_mb=resident_mb())
            stop = threading.Event()
            cancel_started = [0.0]

            def cancel(_):
                if not stop.is_set():
                    cancel_started[0] = time.monotonic()
                    stop.set()

            try:
                translator.translate("Translate this long sentence about a desktop application that listens to computer audio and shows live subtitles.", [], stop, cancel)
            except Cancelled:
                report["cancelled_during_generation"] = True
                report["cancel_seconds"] = round(time.monotonic() - cancel_started[0], 3)
            else:
                report["cancelled_during_generation"] = False
            # The model must also remain usable after cancelling one generation.
            report["after_cancel_translation"] = translator.translate("Good morning.", [], threading.Event())
    finally:
        if translator:
            translator.close()
            report["translation_model_released"] = translator.local.model is None
        if asr:
            asr.close()
            report["asr_model_released"] = asr.model is None
        gc.collect()
        report["rss_after_mb"] = resident_mb()
        (ROOT / "artifacts" / "local-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), "utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report.get("translated") or not report.get("cancelled_during_generation") or not report.get("translation_model_released") or not report.get("asr_model_released"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
