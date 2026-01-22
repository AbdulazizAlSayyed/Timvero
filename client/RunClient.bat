@echo off
cd /d C:\Users\RSS\Desktop\tempo-tracker\client

REM Run using conda env without needing PowerShell activation
C:\Users\RSS\miniconda3\condabin\conda.bat run -n tempo_client python main.py

pause
