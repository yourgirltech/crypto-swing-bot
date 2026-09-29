@echo off
REM Stops backend, frontend and paper engine started by start.cmd. See scripts\stop.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop.ps1" %*
