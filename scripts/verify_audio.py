"""Local integration check: play a generated WAV with system output muted.

The previous mute state is restored in finally. No recorded user audio is saved.
Requires optional pycaw and an input WAV (generate with make-speech.ps1).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import wave
import winsound
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.audio import LoopbackCapture, Segmenter, SileroDetector, dbfs
from app.config import ROOT, Settings
from app.providers import WhisperRecognizer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("wave", type=Path)
    args = parser.parse_args()
    from pycaw.pycaw import AudioUtilities

    endpoint = AudioUtilities.GetSpeakers().EndpointVolume
    previous_mute = endpoint.GetMute()
    chunks, errors = [], []
    stop = threading.Event()
    capture = LoopbackCapture("", stop, chunks.append, lambda _: None, errors.append)
    worker = threading.Thread(target=capture.run)
    try:
        endpoint.SetMute(1, None)
        worker.start()
        time.sleep(0.6)
        winsound.PlaySound(str(args.wave.resolve()), winsound.SND_FILENAME)
        time.sleep(0.8)
    finally:
        stop.set()
        worker.join(timeout=3)
        endpoint.SetMute(previous_mute, None)
    audio = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
    s = Settings(provider="none", source="英语")
    recognizer = WhisperRecognizer(s, print)
    with wave.open(str(args.wave)) as wav:
        original = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768
        rate = wav.getframerate()
    if rate != 16000:
        import math
        divisor = math.gcd(rate, 16000)
        original = resample_poly(original, 16000 // divisor, rate // divisor)
    started = time.monotonic()
    original_text = recognizer.transcribe(original)
    direct_seconds = time.monotonic() - started
    segmenter = Segmenter(SileroDetector())
    segments = segmenter.feed(audio)
    tail = segmenter.flush()
    if tail:
        segments.append(tail)
    captured_text = [recognizer.transcribe(segment.audio) for segment in segments]
    result = {"system_muted_during_capture": True, "previous_mute_restored": bool(endpoint.GetMute()) == bool(previous_mute),
              "captured_seconds": round(len(audio) / 16000, 2), "captured_dbfs": round(dbfs(audio), 2),
              "errors": errors, "original_asr": original_text, "original_inference_seconds": round(direct_seconds, 2),
              "muted_capture_asr": captured_text,
              "segments": [[round(x.start, 2), round(x.end, 2)] for x in segments]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    (ROOT / "artifacts" / "audio-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    if errors or not captured_text or not any(captured_text) or not result["previous_mute_restored"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
