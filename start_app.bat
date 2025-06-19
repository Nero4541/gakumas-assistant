@echo off
cd /d %~dp0
:: ����Ƿ��й���ԱȨ��
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process '%~f0' -Verb RunAs -WorkingDirectory '%~dp0'"
    exit /b
)

.\.venv\Scripts\python.exe -m uvicorn app:app --log-level critical
pause
