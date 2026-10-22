@echo off
setlocal
cd /d "%~dp0"
set "VISION_AGENT_DEMO=true"
set "VISION_VAR_ROOT=%~dp0.artifacts\demo-data"
echo Agent demo: all runs, media, events and export results are MOCK.
echo This demo uses an isolated database. Normal var data is not used.
if "%~1"=="" (
  call start.cmd --port 8004
) else (
  call start.cmd %*
)
