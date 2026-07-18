@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First-time setup is required. Running setup...
  call setup_windows.bat
  if errorlevel 1 exit /b 1
)
set PYTHONPATH=%CD%\src
".venv\Scripts\python.exe" main.py
if errorlevel 1 (
  echo.
  echo LeadDesk AI could not start. Review logs\leaddesk.log.
  pause
)
