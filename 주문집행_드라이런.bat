@echo off
cd /d "%~dp0"
py jq_execute.py --dry-run --yes
echo.
echo [DRY-RUN] No real orders were sent.
pause
