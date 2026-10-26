from __future__ import annotations

import math
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy.signal import resample_poly

RATE = 16000
FRAME = 512


def devices() -> list[dict]:
    import pyaudiowpatch as pa

    with pa.PyAudio() as p:
        return [dict(d) for d in p.get_loopback_device_info_generator()]


def default_device() -> dict:
    import pyaudiowpatch as pa

    with pa.PyAudio() as p:
        return dict(p.get_default_wasapi_loopback())


def to_mono_16k(raw: bytes, channels: int, sample_rate: int) -> np.ndarray:
    samples = np.frombuffer(raw, dtype=np.float32).reshape(-1, channels)
    mono = samples.mean(axis=1)
    if sample_rate != RATE:
        divisor = math.gcd(sample_rate, RATE)
        mono = resample_poly(mono, RATE // divisor, sample_rate // divisor)
    return np.nan_to_num(mono, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)


def dbfs(audio: np.ndarray) -> float:
    if not audio.size:
        return -100.0
    return max(-100.0, 20 * math.log10(max(1e-5, float(np.sqrt(np.mean(audio * audio))))))


def normalize(audio: np.ndarray) -> np.ndarray:
    rms = float(np.sqrt(np.mean(audio * audio))) if audio.size else 0.0
    if rms < 0.00003:
        return audio
    # Cap amplification to avoid treating background noise as speech.
    return np.clip(audio * max(1.0, min(12.0, 0.08 / rms)), -1.0, 1.0).astype(np.float32)


class SileroDetector:
    """Use the ONNX model bundled with faster-whisper; no network or Torch needed."""

    def __init__(self):
        from faster_whisper.vad import get_vad_model

        # Run ONNX directly so each capture session owns its recurrent state.
        # faster-whisper changed its high-level VAD wrapper between releases.
        self.session = get_vad_model().session
        self.inputs = {item.name for item in self.session.get_inputs()}
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.h = np.zeros((1, 1, 128), dtype=np.float32)
        self.c = np.zeros((1, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, 64), dtype=np.float32)

    def __call__(self, audio: np.ndarray) -> bool:
        window = np.concatenate((self.context, audio.reshape(1, -1)), axis=1)
        if "state" in self.inputs:
            out, self.state = self.session.run(None, {"input": window, "state": self.state, "sr": np.array(RATE, dtype=np.int64)})
        else:
            out, self.h, self.c = self.session.run(None, {"input": window, "h": self.h, "c": self.c})
        self.context = window[:, -64:]
        return float(out.item()) >= 0.5


@dataclass
class Utterance:
    audio: np.ndarray
    start: float
    end: float
    created: float


class Segmenter:
    """Bounded, non-overlapping speech segments with pre-roll and silence endpointing."""

    def __init__(self, detector, max_seconds=4.0, silence_ms=550, gain=True):
        self.detector = detector
        self.max_frames = max(1, int(max_seconds * RATE / FRAME))
        self.silence_frames = max(1, math.ceil(silence_ms / 32))
        self.gain = gain
        self.pending = np.empty(0, np.float32)
        self.pre = deque(maxlen=6)
        self.active: list[np.ndarray] = []
        self.position = 0
        self.start = 0
        self.quiet = 0
        self.speech_count = 0

    def feed(self, audio: np.ndarray) -> list[Utterance]:
        self.pending = np.concatenate((self.pending, audio))
        completed = []
        while len(self.pending) >= FRAME:
            frame = self.pending[:FRAME].copy()
            self.pending = self.pending[FRAME:]
            speech = self.detector(normalize(frame) if self.gain else frame)
            if not self.active:
                if speech:
                    self.start = self.position - len(self.pre) * FRAME
                    self.active = list(self.pre)
                    self.pre.clear()
                else:
                    self.pre.append(frame)
            if self.active or speech:
                self.active.append(frame)
                self.speech_count += int(speech)
                self.quiet = 0 if speech else self.quiet + 1
            self.position += FRAME
            if self.active and (len(self.active) >= self.max_frames or self.quiet >= self.silence_frames):
                segment = self.flush()
                if segment is not None:
                    completed.append(segment)
        return completed

    def flush(self) -> Utterance | None:
        result = None
        if self.active and self.speech_count >= 3:
            audio = np.concatenate(self.active)
            result = Utterance(normalize(audio) if self.gain else audio, self.start / RATE, self.position / RATE, time.monotonic())
        self.active = []
        self.quiet = self.speech_count = 0
        self.pre.clear()
        return result


class LoopbackCapture:
    def __init__(self, device_name: str, stop: threading.Event, on_audio, on_level, on_error):
        self.device_name = device_name
        self.stop = stop
        self.on_audio = on_audio
        self.on_level = on_level
        self.on_error = on_error
        self.dropped = 0

    def run(self):
        import pyaudiowpatch as pa

        blocks: queue.Queue = queue.Queue(maxsize=30)

        def callback(data, frame_count, timing, status):
            try:
                blocks.put_nowait(data)
            except queue.Full:
                self.dropped += 1
            return (None, pa.paComplete if self.stop.is_set() else pa.paContinue)

        try:
            with pa.PyAudio() as p:
                available = list(p.get_loopback_device_info_generator())
                device = next((d for d in available if d["name"] == self.device_name), None)
                if device is None:
                    if self.device_name:
                        raise RuntimeError("所选声音设备已断开，请刷新并重新选择。")
                    device = p.get_default_wasapi_loopback()
                channels = min(2, int(device["maxInputChannels"]))
                rate = int(device["defaultSampleRate"])
                with p.open(format=pa.paFloat32, channels=channels, rate=rate, input=True,
                            input_device_index=device["index"], frames_per_buffer=rate // 10,
                            stream_callback=callback) as stream:
                    last = time.monotonic()
                    while not self.stop.is_set():
                        try:
                            data = blocks.get(timeout=0.15)
                            audio = to_mono_16k(data, channels, rate)
                            last = time.monotonic()
                        except queue.Empty:
                            if not stream.is_active():
                                raise RuntimeError("音频流已停止，可能是设备断开或输出设备切换。请重新开始监听。")
                            # Some WASAPI drivers emit no callbacks in silence.
                            if time.monotonic() - last < 0.15:
                                continue
                            audio = np.zeros(round((time.monotonic() - last) * RATE), np.float32)
                            last = time.monotonic()
                        self.on_level(dbfs(audio))
                        self.on_audio(audio)
        except Exception as exc:
            if not self.stop.is_set():
                self.on_error(f"声音捕获失败：{exc}")
                self.stop.set()
