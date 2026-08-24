@echo off
cd /d "%~dp0"
echo Jinwoo Quant - running all module self-tests...
py -m pip install --quiet pandas numpy
py -W ignore selftest_all.py
echo.
echo Done. Self-test dashboard opened in browser.
timeout /t 6 >nul
