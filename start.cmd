@echo off
REM One-command start: Postgres + backend :8010 + frontend :3000 + paper engine. See scripts\start.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" %*
