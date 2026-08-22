@echo off
chcp 949 >nul
cd /d "%~dp0"
set LOG=%~dp0krx_log.txt
echo. >> "%LOG%"
echo ========== %date% %time% ========== >> "%LOG%"
py 진우퀀트_KRX수집.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] krx collect >> "%LOG%") else (echo [OK] krx collect >> "%LOG%")
