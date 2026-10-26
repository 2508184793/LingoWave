@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
    echo Preparing the Python environment. Please wait...
    python -m venv .venv
    if errorlevel 1 goto fail
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt --only-binary llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -c "import llama_cpp" >nul 2>&1
if errorlevel 1 (
    echo Installing the embedded translation runtime. Please wait...
    ".venv\Scripts\python.exe" -m pip install llama-cpp-python==0.3.19 --only-binary llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m app.main %*
if errorlevel 1 goto fail
exit /b 0
:fail
echo.
echo LingoWave could not start. Please keep the error message above.
pause
exit /b 1
