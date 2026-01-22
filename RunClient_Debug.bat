@echo off
set ROOT=C:\Users\RSS\Desktop\tempo-tracker
set CONDA=C:\Users\RSS\miniconda3\condabin\conda.bat

cd /d %ROOT%
%CONDA% run -n tempo_client python -u %ROOT%\client\main.py > %ROOT%\client_debug.log 2>&1

type %ROOT%\client_debug.log
pause
