@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Registering weekly KOSPI daily update (Sat 07:30, before entry scan)...
schtasks /Create /SC WEEKLY /D SAT /TN "JinwooQuant_DailyUpdate" /TR "\"%~dp0jq_daily_update.bat\"" /ST 07:30 /F
if errorlevel 1 ( echo [FAIL] Need admin rights - right-click this file - Run as administrator. & pause & exit /b )
echo [OK] Registered: every Saturday 07:30 runs jq_daily_update.bat
echo   - fetch_kospi_daily_full + verify --market kospi
echo   - result log: jq_daily_update_console.txt
echo Remove later: schtasks /Delete /TN "JinwooQuant_DailyUpdate" /F
echo Test now:     schtasks /Run /TN "JinwooQuant_DailyUpdate"
pause >nul
