@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" (
  echo Please run setup.cmd first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" deploy\scripts\simulated_cameras.py --register %*
if errorlevel 1 pause
