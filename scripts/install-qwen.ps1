$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw '请先运行 start.cmd 创建环境。' }
& $pythonPath -m pip install 'qwen-asr' 'accelerate'
if ($LASTEXITCODE -ne 0) { throw 'Qwen 依赖安装失败。' }
Write-Host 'Qwen 依赖已安装。CPU 可直接使用；GPU 还需要 CUDA 版 PyTorch。'
Write-Host '然后在应用设置中选择 Qwen3-ASR，首次加载将下载模型权重。'
