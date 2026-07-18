@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup_windows.bat
set PYTHONPATH=%CD%\src
".venv\Scripts\python.exe" -m pytest -q
pause
