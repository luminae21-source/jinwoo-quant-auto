@echo off
chcp 65001 >nul
cd /d "%~dp0"
py -m pip install --quiet requests certifi >nul 2>&1
py -W ignore kakao_send_recommend.py
echo.
pause
