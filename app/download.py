"""Explicit model preparation, also used by the desktop model-download dialog."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

from .config import ROOT

WHISPER_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "preprocessor_config.json")


def download_whisper(model: str, source="huggingface", progress=print) -> Path:
    if model not in ("tiny", "base", "small", "medium", "large-v3"):
        raise ValueError("下载仅支持 tiny、base、small、medium、large-v3；自定义模型请填写本地路径。")
    destination = ROOT / "models" / f"whisper-{model}"
    destination.mkdir(parents=True, exist_ok=True)
    if source == "modelscope":
        base = f"https://modelscope.cn/models/pengzhendong/faster-whisper-{model}/resolve/master"
    else:
        base = f"https://huggingface.co/Systran/faster-whisper-{model}/resolve/main"
    with httpx.Client(timeout=httpx.Timeout(60, connect=15), follow_redirects=True) as client:
        # Download model.bin last; its presence indicates that metadata is ready.
        for filename in sorted(WHISPER_FILES, key=lambda name: name == "model.bin"):
            path = destination / filename
            if path.exists() and path.stat().st_size > 0:
                progress(f"已存在 {filename}")
                continue
            progress(f"下载 {filename}…")
            with client.stream("GET", f"{base}/{filename}") as response:
                if response.status_code == 404 and filename in ("preprocessor_config.json", "vocabulary.txt"):
                    continue
                response.raise_for_status()
                temporary = path.with_suffix(path.suffix + ".part")
                length = int(response.headers.get("content-length", 0))
                received = 0
                last_mb = -1
                with temporary.open("wb") as output:
                    for chunk in response.iter_bytes(1024 * 1024):
                        output.write(chunk)
                        received += len(chunk)
                        mb = received // (10 * 1024 * 1024)
                        if mb != last_mb:
                            progress(f"{filename}: {received / 1024**2:.1f} MB" + (f" / {length / 1024**2:.1f} MB" if length else ""))
                            last_mb = mb
                if length and received != length:
                    raise RuntimeError("下载文件不完整，请重试。")
                temporary.replace(path)
    json.loads((destination / "config.json").read_text("utf-8"))
    progress(f"模型就绪：{destination}")
    return destination


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="small")
    parser.add_argument("--source", choices=("huggingface", "modelscope"), default="huggingface")
    args = parser.parse_args()
    download_whisper(args.model, args.source, lambda value: print(value, flush=True))


if __name__ == "__main__":
    main()
