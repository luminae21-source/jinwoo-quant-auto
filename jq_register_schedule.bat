@echo off
chcp 65001 >nul
cd /d "%~dp0"
schtasks /Create /SC MONTHLY /D 1 /TN "JinwooQuant_LaneScan" /TR "\"%~dp0jq_autoscan.bat\"" /ST 08:30 /F
if errorlevel 1 ( echo [FAIL] need to run as administrator? try right-click Run as admin. & pause & exit /b )
echo [OK] Monthly auto-scan registered: day 1 of each month, 08:30.
echo Remove later: schtasks /Delete /TN "JinwooQuant_LaneScan" /F
pause >nul
