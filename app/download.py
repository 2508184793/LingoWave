"""Explicit model preparation, also used by the desktop model-download dialog."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import httpx

from .config import LOCAL_MODEL_NAME, ROOT

TRANSLATION_SIZE = 1133080448
TRANSLATION_SHA256 = "dc5f44fcf1fa496ee7ad725982c0c8c553a4de00259b53af84c4b89fb0c06699"
TRANSLATION_REVISION = "a0c709d9fac510f2c807aa3af52872340dc37a4a"


def checked_download(url: str, destination: Path, size: int, sha256: str, progress=print) -> Path:
    """Resume an owned .part file and publish only after exact size/hash validation."""
    destination.parent.mkdir(parents=True, exist_ok=True)

    def valid(path):
        if not path.is_file() or path.stat().st_size != size:
            return False
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest() == sha256

    if destination.exists():
        progress("正在校验已有模型…")
        if valid(destination):
            progress(f"模型已就绪：{destination}")
            return destination
        raise RuntimeError("已有模型校验失败，请移走该文件后重新下载。")
    partial = destination.with_suffix(destination.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > size:
        partial.unlink()
        offset = 0
    if offset < size:
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        with httpx.Client(timeout=httpx.Timeout(60, connect=15), follow_redirects=True) as client:
            with client.stream("GET", url, headers=headers) as response:
                response.raise_for_status()
                if response.status_code == 206:
                    content_range = response.headers.get("content-range", "")
                    if not content_range.startswith(f"bytes {offset}-") or not content_range.endswith(f"/{size}"):
                        raise RuntimeError("下载源返回了不匹配的文件区间，请切换下载源。")
                elif response.status_code == 200:
                    offset = 0  # The server ignored Range: restart, never append.
                else:
                    raise RuntimeError("下载源返回异常状态，请切换下载源。")
                received = offset
                last_mb = -1
                with partial.open("ab" if offset else "wb") as output:
                    for block in response.iter_bytes(1024 * 1024):
                        received += len(block)
                        if received > size:
                            raise RuntimeError("下载源返回的数据超出预期大小，已停止下载。")
                        output.write(block)
                        mb = received // (10 * 1024 * 1024)
                        if mb != last_mb:
                            progress(f"翻译模型：{received / 1024**2:.1f} / {size / 1024**2:.1f} MB（{received * 100 / size:.0f}%）")
                            last_mb = mb
    progress("下载结束，正在校验模型 SHA-256…")
    if not valid(partial):
        if partial.exists() and partial.stat().st_size == size:
            partial.unlink()  # Discard only our corrupt temporary download.
        raise RuntimeError("模型下载不完整或校验失败，请重试；未完成的有效分片会继续下载。")
    partial.replace(destination)
    progress(f"模型就绪：{destination}")
    return destination


def download_translation(source="huggingface", progress=print) -> Path:
    if source == "modelscope":
        base = "https://modelscope.cn/models/Tencent-Hunyuan/Hy-MT2-1.8B-GGUF/resolve/master"
    else:
        base = f"https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/{TRANSLATION_REVISION}"
    return checked_download(f"{base}/{LOCAL_MODEL_NAME}", ROOT / "models" / "translation" / LOCAL_MODEL_NAME,
                            TRANSLATION_SIZE, TRANSLATION_SHA256, progress)

WHISPER_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt", "preprocessor_config.json")
WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo")


def download_whisper(model: str, source="huggingface", progress=print) -> Path:
    if model not in WHISPER_MODELS:
        raise ValueError("请选择支持的 Whisper 型号，或在设置中填写已有模型路径。")
    destination = ROOT / "models" / f"whisper-{model}"
    destination.mkdir(parents=True, exist_ok=True)
    if source == "modelscope":
        base = f"https://modelscope.cn/models/pengzhendong/faster-whisper-{model}/resolve/master"
    elif model == "large-v3-turbo":
        base = "https://huggingface.co/mobiuslabsgmbh/faster-whisper-large-v3-turbo/resolve/main"
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
    parser.add_argument("--kind", choices=("whisper", "translation"), default="whisper")
    parser.add_argument("--source", choices=("huggingface", "modelscope"), default="huggingface")
    args = parser.parse_args()
    progress = lambda value: print(value, flush=True)
    if args.kind == "translation":
        download_translation(args.source, progress)
    else:
        download_whisper(args.model, args.source, progress)


if __name__ == "__main__":
    main()
