$ErrorActionPreference = 'Stop'
$projectDir = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectDir '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run start.cmd first to create the Python environment.' }
& $pythonPath -m pip install 'llama-cpp-python==0.3.19' --only-binary llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'Embedded translation runtime installation failed.' }
Write-Host 'Embedded CPU translation is ready. No Ollama or local server is needed.'
