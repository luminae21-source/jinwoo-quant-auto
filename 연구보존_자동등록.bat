@echo off
chcp 949 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0연구보존_자동등록.ps1" %*
pause
