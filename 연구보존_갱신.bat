@echo off
chcp 949 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
py "%~dp0연구보존_갱신.py" %*
if errorlevel 1 python "%~dp0연구보존_갱신.py" %*
echo.
pause
