# LingoWave · 桌面实时翻译

监听 Windows 正在播放的声音，进行语音识别和翻译，在透明置顶窗口显示双语字幕。

## 启动

双击项目根目录的 **`start.cmd`**。首次使用需要 Python 3.11 / 3.12；脚本会创建虚拟环境并安装依赖。

模型权重和虚拟环境不随仓库分发。首次运行请在「下载模型」中分别准备 Whisper small 和 Hy-MT2-1.8B Q4_K_M（约 1.1GB）。

1. 点击 **字幕演示** 查看预设字幕效果，不录音、不调用 API。
2. 点击 **声音检测 / 静音测试**，播放视频，观察声音电平。可将 Windows 任务栏的扬声器设为静音，再确认内部信号是否仍存在。
3. 默认使用 **内嵌本地模型**，不需要服务地址、API Key、Ollama 或 LM Studio。在 **模型与字幕 → 翻译模型** 中也可选择已有的 GGUF 文件。
4. 点击 **测试翻译**，通过后 **开始监听**。停止监听会卸载识别和翻译模型。

只想看语音识别原文，可以把翻译服务设为 **仅原文**。需要云端翻译时，再切换到 API 模式。

## 已实现

- WASAPI loopback 捕获选定输出设备的全部声音，不使用麦克风。
- 声音电平、低音量增益、Silero ONNX 语音检测、停顿断句、最长分段。
- faster-whisper 本地识别；可选 Qwen3-ASR 分句识别；兼容 `/audio/transcriptions` 的短音频识别 API。
- 内嵌 llama.cpp 直接运行本地 GGUF 翻译模型，无后台服务、不打开 HTTP 端口；流式输出、生成取消、停止时关闭模型。
- 可选 Qwen-MT 翻译专用 API、通用 `/chat/completions` 兼容服务、Ollama 原生流式接口。
- 透明置顶、拖动位置、鼠标穿透、双语或仅译文、字号及背景设置。
- 有界队列，过载时跳过旧任务；流式译文按句子编号更新，旧译文不会覆盖新字幕。
- 字幕历史、当前会话 TXT / SRT 导出、可选 SQLite 持久化；界面保留最近 300 条。
- Windows 全局快捷键；如果被占用则退回窗口内快捷键。
- 模型下载窗口；翻译权重来自腾讯官方仓库，支持断点续传、固定大小与 SHA-256 校验后原子保存。Whisper 支持 Hugging Face 和 ModelScope 社区转换仓库。

## 默认模型与参考硬件

参考测试环境：i7-14650HX、约 24GB 内存、RTX 4050 Laptop 6GB。

默认选择 **Whisper small / CPU INT8**，无需 CUDA，已在参考环境实测。可在设置切换 NVIDIA GPU；CTranslate2 需要兼容的 CUDA 12 / cuDNN 9 运行库，不能仅凭安装了显卡驱动就启用 GPU。

### Qwen-MT API

- 服务：Qwen-MT
- 中国内地根地址：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- 模型：`qwen-mt-flash`
- Key：填写与服务区域匹配的 DashScope API Key

这是翻译专用协议，单条 user 消息加 `translation_options`，不假设通用聊天参数均可使用。其他区域请依据账号控制台填写相应服务地址。

### 内嵌本地翻译（默认）

本地语音识别用 faster-whisper；本地翻译通过 `llama-cpp-python` 直接在软件进程内加载腾讯 Hy-MT2-1.8B Q4_K_M。不会启动 Ollama、llama-server 或独立推理软件，也不监听本地 API 端口。

模型下载后位于 `models/translation/Hy-MT2-1.8B-Q4_K_M.gguf`，也可在设置里选择其他兼容 GGUF。默认按 Hy-MT2 的单轮翻译指令使用模型自身聊天模板；其他模型需实测模板与翻译效果。

启动脚本会从 llama-cpp-python 项目官方 wheel 源安装固定版本 **0.3.19**，使用 CPU 组件。旧环境可运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-local.ps1
```

「自动」会检测内嵌组件是否支持 GPU，当前默认 CPU wheel 使用 CPU；仅选 GPU 但组件不支持时，会明确报错，不会悄悄切换到云端。GPU 组件属于可选配置，不需要为了使用本地翻译额外安装。

点击停止后，当前生成会取消，翻译权重与识别权重会卸载；软件不会退出后继续运行本地服务。关闭翻译测试时也会释放模型。

模型来源：[腾讯官方 GGUF](https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF)，推理组件：[llama-cpp-python](https://github.com/abetlen/llama-cpp-python)。首次安装与下载需要联网，准备好后可离线识别和翻译。

### Ollama 本地服务（可选）

先安装并启动 Ollama，在终端执行：

```powershell
ollama pull hf.co/tencent/Hy-MT2-1.8B-GGUF:Q4_K_M
```

然后在设置中选 **Ollama**，地址 `http://127.0.0.1:11434/v1`，模型 `hf.co/tencent/Hy-MT2-1.8B-GGUF:Q4_K_M`。程序实际调用原生 `/api/chat` 并设置 `think=false`。

此选项供已有 Ollama 用户使用，不是默认本地模式，也不会自动启动或安装 Ollama。

### Qwen3-ASR（可选）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install-qwen.ps1
```

设置中选 Qwen3-ASR。CPU 可以使用；GPU 还需要 CUDA 版 PyTorch。首次使用下载模型，亦可填写本地权重路径。

Windows 本地使用 **Transformers 按短句推理**。官方流式状态接口依赖 vLLM，本项目没有将其标为原生流式识别。可选 Qwen 依赖和模型未在本次默认环境中安装验证。

### 其他识别 API

填写以 `/v1` 结尾的服务根地址、模型和可选 Key；服务需接受 WAV multipart 上传到 `/audio/transcriptions`，返回 `{"text":"..."}`。本版是分句上传，不是厂商原生 WebSocket 流式协议。

## 快捷键

| 快捷键 | 动作 |
|---|---|
| Ctrl + Alt + F8 | 开始 / 停止监听 |
| Ctrl + Alt + F9 | 显示 / 隐藏字幕 |
| Ctrl + Alt + F10 | 开关鼠标穿透 |

关闭鼠标穿透后可直接拖动字幕。切换耳机或默认输出设备后，停止监听并重新开始；也可以刷新后指定设备。

## 系统静音

已在参考环境的 Realtek 输出设备上验证：将 Windows 系统输出静音，仍可通过 loopback 捕获并识别正在播放的测试语音；测试前后的静音状态已恢复。可运行下方验证脚本，在本机生成 `artifacts/audio-verification.json`，测试录音和结果不随仓库上传。

这不代表所有设备与驱动都相同。播放器内部静音可能直接不再产生有效音频。无信号时自动增益无法恢复声音。本版没有自动配置虚拟声卡，也没有指定进程捕获。

## 数据

- 设置、日志和可选字幕库：`%LOCALAPPDATA%\LingoWave\`。
- API Key：Windows 凭据管理器，不写入配置文件或仓库。
- 默认不保存音频、不持久化字幕；开启历史后存储识别文字和译文。关闭持久化不会删除先前保存的记录，使用「清空」可删除。
- 云端翻译会发送识别文字；云端识别会上传音频；全本地模式不需要发送语音到云端，首次下载模型仍需联网。
- HTTP 错误只显示状态和固定说明，不回显服务响应正文或 Key。没有自动重试收费请求。

## 验证与开发

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m app.main --smoke-test
.\.venv\Scripts\python.exe -m app.download --model small --source modelscope
.\.venv\Scripts\python.exe -m app.download --kind translation --source modelscope
```

真实静音捕获验证需要可选 `pycaw`，使用本机合成的测试语音，测试期间临时静音并在 finally 中恢复：

```powershell
.\.venv\Scripts\python.exe -m pip install pycaw
powershell -ExecutionPolicy Bypass -File scripts\make-speech.ps1
.\.venv\Scripts\python.exe -X utf8 scripts\verify_audio.py artifacts\test-speech.wav
.\.venv\Scripts\python.exe -X utf8 scripts\verify_local.py
```

`verify_local.py` 会使用真实 Whisper 和 Hy-MT2 模型，禁止 HTTP 客户端调用，验证测试音频识别、真实翻译、生成取消及取消后再次翻译、模型关闭，报告写入 `artifacts/local-verification.json`。如已安装可选 psutil，报告也会记录进程内存变化。

内嵌 CPU 路径已在参考环境验证。云端 API 的实际效果和计费，以及 Ollama / Qwen / GPU 可选路径，需要配置后验证；接口自动测试使用本地模拟服务，不代表已连接商业 API。

当前交付是可运行的 Python 桌面版，非独立 EXE。采用短句识别，没有承诺固定延迟；纯音乐、多人同时说话、嘈杂音轨会影响效果。独占全屏游戏中的覆盖显示需要另行适配。
