@echo off
set PYTHONPATH=%PYTHONPATH%;%~dp0
python server/app.py
pause
