@echo off
chcp 949 >nul
cd /d "%~dp0"
echo ===== Jinwoo Monthly Automation =====
python "%~dp0진우_월간자동화.py"
echo.
pause
