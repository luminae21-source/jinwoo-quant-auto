@echo off
cd /d "%~dp0"
py -m pip install --quiet pandas numpy
py -W ignore recommend_dashboard.py
echo.
echo Done. Dashboard HTML opened in browser.
timeout /t 3 >nul
