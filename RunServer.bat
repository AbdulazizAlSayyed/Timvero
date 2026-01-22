@echo off
cd /d C:\Users\RSS\Desktop\Timvero\server
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
pause