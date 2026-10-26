from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_MODEL_NAME = "Hy-MT2-1.8B-Q4_K_M.gguf"
DEFAULT_LOCAL_MODEL = f"models/translation/{LOCAL_MODEL_NAME}"
DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(ROOT / "data"))) / "LingoWave"
LANGUAGES = {
    "自动检测": ("auto", "auto"),
    "简体中文": ("zh", "Chinese"),
    "英语": ("en", "English"),
    "日语": ("ja", "Japanese"),
    "韩语": ("ko", "Korean"),
    "法语": ("fr", "French"),
    "德语": ("de", "German"),
    "西班牙语": ("es", "Spanish"),
    "俄语": ("ru", "Russian"),
}


@dataclass
class Settings:
    device_name: str = ""
    source: str = "自动检测"
    target: str = "简体中文"
    asr_engine: str = "faster-whisper"
    whisper_model: str = "small"
    whisper_device: str = "cpu"
    qwen_path: str = "Qwen/Qwen3-ASR-0.6B"
    asr_url: str = "http://127.0.0.1:8000/v1"
    asr_model: str = "whisper-1"
    provider: str = "embedded"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-mt-flash"
    local_model_path: str = DEFAULT_LOCAL_MODEL
    local_device: str = "auto"
    local_threads: int = 6
    max_segment: float = 6.0
    silence_ms: int = 320
    live_preview: bool = True
    preview_seconds: float = 1.2
    auto_gain: bool = True
    font_size: int = 28
    opacity: int = 72
    show_source: bool = True
    subtitle_seconds: int = 15
    remember_history: bool = False
    overlay_x: int = -1
    overlay_y: int = -1
    overlay_width: int = 960

    @classmethod
    def load(cls) -> "Settings":
        try:
            values = json.loads((DATA_DIR / "settings.json").read_text("utf-8"))
            allowed = {f.name for f in fields(cls)}
            result = cls(**{k: v for k, v in values.items() if k in allowed})
            if result.source not in LANGUAGES:
                result.source = "自动检测"
            if result.target not in LANGUAGES or result.target == "自动检测":
                result.target = "简体中文"
            result.font_size = max(16, min(60, int(result.font_size)))
            result.opacity = max(0, min(100, int(result.opacity)))
            result.max_segment = max(2.0, min(10.0, float(result.max_segment)))
            result.silence_ms = max(200, min(2000, int(result.silence_ms)))
            result.overlay_width = max(500, min(1800, int(result.overlay_width)))
            result.local_threads = max(1, min(32, int(result.local_threads)))
            result.preview_seconds = max(0.8, min(3.0, float(result.preview_seconds)))
            if result.local_device not in ("auto", "cpu", "gpu"):
                result.local_device = "auto"
            return result
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        dest = DATA_DIR / "settings.json"
        temp = dest.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), "utf-8")
        temp.replace(dest)


def secret_account(provider: str, url: str) -> str:
    return f"{provider}:{url.rstrip('/')}"


def get_secret(provider: str, url: str) -> str:
    import keyring

    return keyring.get_password("LingoWave", secret_account(provider, url)) or ""


def put_secret(provider: str, url: str, value: str) -> None:
    import keyring

    account = secret_account(provider, url)
    if value:
        keyring.set_password("LingoWave", account, value)
    else:
        try:
            keyring.delete_password("LingoWave", account)
        except keyring.errors.PasswordDeleteError:
            pass
