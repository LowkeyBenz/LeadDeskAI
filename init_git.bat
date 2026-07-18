@echo off
cd /d "%~dp0"
where git >nul 2>nul
if errorlevel 1 (
  echo Git is not installed. Install Git for Windows first.
  pause
  exit /b 1
)
git init
git add .
git commit -m "LeadDesk AI 3.0 professional foundation"
echo Git repository created.
pause
