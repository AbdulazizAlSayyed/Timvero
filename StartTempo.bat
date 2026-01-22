@echo off
setlocal
cd /d "%~dp0"

echo ======================================
echo Starting TEMPO Server...
echo ======================================
start "Tempo Server" cmd /k "cd server && call .\.venv\Scripts\activate && python -m uvicorn app.main:app --host 127.0.0.1 --port 8001"

timeout /t 2 >nul

echo ======================================
echo Starting TEMPO Client...
echo ======================================
\
start "Tempo Client" cmd /k "cd client && call .\.venv\Scripts\activate && python main.py"

echo Done.
exit /b 0
