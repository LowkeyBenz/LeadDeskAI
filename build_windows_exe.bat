@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup_windows.bat
".venv\Scripts\python.exe" -m pip install pyinstaller
set PYTHONPATH=%CD%\src
".venv\Scripts\pyinstaller.exe" --noconfirm --windowed --name LeadDeskAI --paths src main.py
pause
