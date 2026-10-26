@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
    echo 首次运行：正在准备 Python 环境…
    python -m venv .venv
    if errorlevel 1 goto fail
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto fail
)
".venv\Scripts\python.exe" -m app.main %*
if errorlevel 1 goto fail
exit /b 0
:fail
echo.
echo 启动失败，请保留此窗口中的错误信息。
pause
exit /b 1
