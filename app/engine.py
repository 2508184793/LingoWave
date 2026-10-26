from __future__ import annotations

import queue
import threading
import time
from dataclasses import replace

from PySide6.QtCore import QObject, Signal

from .audio import LoopbackCapture, Segmenter, SileroDetector
from .config import Settings
from .history import Caption
from .providers import APIRecognizer, Cancelled, QwenRecognizer, Translator, WhisperRecognizer


def offer_latest(q: queue.Queue, item):
    dropped = None
    try:
        q.put_nowait(item)
    except queue.Full:
        try:
            dropped = q.get_nowait()
        except queue.Empty:
            pass
        q.put_nowait(item)
    return dropped


class Engine(QObject):
    status = Signal(str)
    level = Signal(float)
    caption = Signal(object)
    error = Signal(str)
    metrics = Signal(float, int)
    ready = Signal()
    finished = Signal()

    def __init__(self, settings: Settings, translation_key="", asr_key="", probe=False, parent=None):
        super().__init__(parent)
        self.s = replace(settings)
        self.translation_key = translation_key
        self.asr_key = asr_key
        self.probe = probe
        self.stop_event = threading.Event()
        self.thread = None
        self.dropped = 0

    def start(self):
        self.thread = threading.Thread(target=self._run, name="LingoWave-session", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.status.emit("正在停止，等待当前任务释放…")

    def _run(self):
        capture_thread = translation_thread = None
        translator = recognizer = None
        translations = queue.Queue(maxsize=4)
        utterances = queue.Queue(maxsize=4)
        try:
            if self.probe:
                self.status.emit("声音检测中 · 可以切换系统静音，观察电平是否仍在变化")
                capture = LoopbackCapture(self.s.device_name, self.stop_event, lambda _: None, self.level.emit, self.error.emit)
                self.ready.emit()
                capture.run()
                return
            translator = Translator(self.s, self.translation_key)
            if self.s.asr_engine == "qwen":
                recognizer = QwenRecognizer(self.s, self.status.emit)
            elif self.s.asr_engine == "api":
                recognizer = APIRecognizer(self.s, self.asr_key)
            else:
                recognizer = WhisperRecognizer(self.s, self.status.emit)
            translator.prepare(self.stop_event, self.status.emit)
            if self.stop_event.is_set():
                return
            segmenter = Segmenter(SileroDetector(), self.s.max_segment, self.s.silence_ms, self.s.auto_gain)

            def receive(audio):
                for utterance in segmenter.feed(audio):
                    if offer_latest(utterances, utterance) is not None:
                        self.dropped += 1
                        self.status.emit("识别暂时跟不上，已跳过较旧音频以保持实时")

            capture = LoopbackCapture(self.s.device_name, self.stop_event, receive, self.level.emit, self.error.emit)
            translation_thread = threading.Thread(target=self._translate, args=(translator, translations), daemon=True, name="LingoWave-translate")
            capture_thread = threading.Thread(target=capture.run, daemon=True, name="LingoWave-capture")
            translation_thread.start()
            capture_thread.start()
            self.ready.emit()
            self.status.emit("正在监听 · 等待电脑播放语音")
            counter = 0
            failures = 0
            while not self.stop_event.is_set():
                try:
                    utterance = utterances.get(timeout=0.2)
                except queue.Empty:
                    continue
                if time.monotonic() - utterance.created > 12:
                    self.dropped += 1
                    self.metrics.emit(time.monotonic() - utterance.created, self.dropped)
                    continue
                try:
                    text = recognizer.transcribe(utterance.audio)
                    failures = 0
                except Exception as exc:
                    failures += 1
                    self.error.emit(f"语音识别失败：{exc}")
                    if failures >= 3:
                        raise RuntimeError("连续三次识别失败，已停止监听。请检查模型配置。")
                    continue
                if self.stop_event.is_set() or not text:
                    continue
                counter += 1
                caption = Caption(counter, utterance.start, utterance.end, text,
                                  status="仅原文" if self.s.provider == "none" else "等待翻译")
                self.caption.emit(caption)
                self.metrics.emit(time.monotonic() - utterance.created, self.dropped + capture.dropped)
                if self.s.provider != "none":
                    dropped = offer_latest(translations, caption)
                    if dropped is not None:
                        self.dropped += 1
                        self.caption.emit(replace(dropped, status="已跳过：翻译队列积压"))
        except Cancelled:
            pass
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.stop_event.set()
            if capture_thread:
                capture_thread.join(timeout=3)
            # Provider reads time out, and streaming output checks cancellation.
            if translation_thread:
                translation_thread.join()
            for resource in (translator, recognizer):
                close = getattr(resource, "close", None)
                if close:
                    try:
                        close()
                    except Exception:
                        self.error.emit("模型资源释放失败，请关闭软件后重试。")
            self.finished.emit()

    def _translate(self, translator: Translator, pending: queue.Queue):
        context = []
        while not self.stop_event.is_set():
            try:
                caption = pending.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                last_update = [0.0]

                def partial(text):
                    now = time.monotonic()
                    if now - last_update[0] > 0.08 and not self.stop_event.is_set():
                        self.caption.emit(replace(caption, translation=text, status="翻译中"))
                        last_update[0] = now

                translated = translator.translate(caption.source, context, self.stop_event, partial)
                if self.stop_event.is_set():
                    break
                context.append((caption.source, translated))
                context = context[-3:]
                self.caption.emit(replace(caption, translation=translated, status="已完成"))
            except Cancelled:
                break
            except Exception as exc:
                self.caption.emit(replace(caption, status="翻译失败"))
                self.error.emit(str(exc))
