@echo off
rem Start test-platform backend. Safe to launch from any directory:
rem %~dp0 is this script's own folder, so we always cd into backend/ first.
rem Add --reload to the uvicorn line during development if you want auto-restart.
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv not found under %~dp0
    echo Create it first:
    echo     py -3.12 -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting backend at http://127.0.0.1:8000  (API docs: http://127.0.0.1:8000/docs)
rem --host 0.0.0.0: CI 测试容器经 host.docker.internal 打平台登录接口需可达本机所有地址
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

pause
