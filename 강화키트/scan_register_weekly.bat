@echo off
REM Register weekly auto-run for full_scan and rebound_scan (Monday mornings).
set "DIR=%~dp0"
schtasks /Create /TN "JinwooQuant_FullScan_Weekly" /TR "\"%DIR%full_scan.bat\"" /SC WEEKLY /D MON /ST 08:00 /F
schtasks /Create /TN "JinwooQuant_Rebound_Weekly" /TR "\"%DIR%rebound_scan.bat\"" /SC WEEKLY /D MON /ST 08:10 /F
if errorlevel 1 (
  echo.
  echo [ERROR] Register failed. You can still run full_scan.bat / rebound_scan.bat manually.
  pause
  exit /b 1
)
echo.
echo [DONE] Weekly tasks registered - every Monday: FullScan 08:00, Rebound 08:10.
echo   Check:  schtasks /Query /TN "JinwooQuant_FullScan_Weekly"
echo   Daily instead? edit this file: change  /SC WEEKLY /D MON  to  /SC DAILY
echo   Remove: schtasks /Delete /TN "JinwooQuant_FullScan_Weekly" /F   (and _Rebound_Weekly)
pause
