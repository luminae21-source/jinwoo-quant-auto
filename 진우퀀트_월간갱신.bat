@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo.
echo ============================================================
echo   Jinwoo Quant - Monthly Refresh
echo   (KRX login window may pop up - approve it)
echo ============================================================
python monthly_refresh.py
echo.
echo Done. Press any key to close.
pause >nul
