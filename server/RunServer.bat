@echo off
cd /d C:\Users\RSS\Desktop\tempo-tracker\server
call .venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
