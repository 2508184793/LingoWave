"""In-process GGUF inference: no executable, HTTP server, or model manager app."""
from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

from .config import LANGUAGES, ROOT, Settings


def translation_prompt(text: str, settings: Settings, context=()) -> str:
    previous = "\n".join(original for original, _ in context[-2:])[-400:]
    if settings.target == "简体中文":
        prompt = ("将以下对白翻译成自然、准确的简体中文字幕。保留原意、否定和语气，正确理解口语和习语。"
                  "只输出当前原文的译文，不要解释，不要补写尚未说出的内容。\n")
        if previous:
            prompt += f"前文（仅供理解指代和术语，不要重复翻译）：\n{previous}\n"
        return prompt + f"当前原文：\n{text}"
    target = LANGUAGES[settings.target][1]
    prompt = f"Translate only the current dialogue into natural {target}. Preserve meaning, negation and tone. Output only its translation.\n"
    if previous:
        prompt += f"Previous dialogue (context only; do not translate again):\n{previous}\n"
    return prompt + f"Current dialogue:\n{text}"


def model_path(settings: Settings) -> Path:
    path = Path(settings.local_model_path).expanduser()
    return path if path.is_absolute() else ROOT / path


def validate_model(settings: Settings) -> Path:
    path = model_path(settings)
    if path.suffix.lower() != ".gguf":
        raise ValueError("本地翻译请选择 .gguf 模型文件。")
    if not path.is_file():
        raise ValueError("本地翻译模型尚未下载。请点击「下载模型」选择「本地翻译」，或在设置中选择已有 GGUF 文件。")
    with path.open("rb") as handle:
        if handle.read(4) != b"GGUF":
            raise ValueError("模型不是有效的 GGUF 文件，请重新下载。")
    if importlib.util.find_spec("llama_cpp") is None:
        raise RuntimeError("内嵌翻译组件尚未安装，请运行 scripts\\install-local.ps1 后重启软件。")
    return path


class EmbeddedTranslator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.path = validate_model(settings)
        self.model = None
        self.backend = ""

    def prepare(self, stop: threading.Event, status=lambda _: None):
        from .providers import Cancelled

        if stop.is_set():
            raise Cancelled()
        if self.model is not None:
            return
        from llama_cpp import Llama, llama_supports_gpu_offload

        available = bool(llama_supports_gpu_offload())
        if self.settings.local_device == "gpu" and not available:
            raise RuntimeError("当前内嵌组件为 CPU 版，请选择「自动」或「CPU」。GPU 推理需安装支持 GPU 的 llama-cpp-python。")
        gpu = available and self.settings.local_device != "cpu"
        self.backend = "GPU" if gpu else "CPU"
        status(f"正在加载内嵌翻译模型 · {self.backend} · {self.path.name}…")
        self.model = Llama(model_path=str(self.path), n_ctx=2048, n_batch=128,
                           n_threads=self.settings.local_threads, n_threads_batch=self.settings.local_threads,
                           n_gpu_layers=-1 if gpu else 0, verbose=False)
        self.eos = self.model.token_eos()
        if self.eos < 0:
            self.close()
            raise RuntimeError("所选模型缺少结束标记，无法安全控制生成。")
        if stop.is_set():
            self.close()
            raise Cancelled()
        status(f"内嵌翻译已就绪 · {self.backend} · 不需要 Ollama 或 API Key")

    def translate(self, text: str, stop: threading.Event, on_partial=None, context=()) -> str:
        from .providers import Cancelled
        from llama_cpp import LogitsProcessorList

        self.prepare(stop)
        if stop.is_set():
            raise Cancelled()
        # Follow Hy-MT2's single-user-turn instruction format. The model's GGUF
        # metadata supplies its own chat template; do not force a ChatML template.
        prompt = translation_prompt(text, self.settings, context)

        def check_cancel(_tokens, logits):
            if stop.is_set():
                # The processor runs inside a ctypes sampler callback. Exceptions
                # raised there are swallowed by ctypes; force a clean EOS instead.
                logits[:] = float("-inf")
                logits[self.eos] = 0.0
            return logits

        stream = self.model.create_chat_completion(
            messages=[{"role": "user", "content": prompt}], stream=True,
            max_tokens=256, temperature=0.15, top_p=0.8, top_k=20, repeat_penalty=1.05, seed=42,
            logits_processor=LogitsProcessorList([check_cancel]))
        output = ""
        try:
            for chunk in stream:
                if stop.is_set():
                    raise Cancelled()
                choices = chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {}).get("content", "") or ""
                    output += delta
                    if delta and on_partial:
                        on_partial(output)
        finally:
            close = getattr(stream, "close", None)
            if close:
                close()
        if stop.is_set():
            raise Cancelled()
        if not output.strip():
            raise RuntimeError("本地模型没有返回译文，请检查模型文件与目标语言。")
        return output.strip()

    def close(self):
        model, self.model = self.model, None
        if model is not None:
            model.close()
