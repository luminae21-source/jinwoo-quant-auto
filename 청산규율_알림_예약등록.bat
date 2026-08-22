@echo off
chcp 949 >nul
cd /d "%~dp0"
set TASKNAME=JinwooQuant_ExitDiscipline
set TARGET=%~dp0청산규율_알림.bat

echo ================================================================
echo  register scheduled task : %TASKNAME%
echo  target : %TARGET%
echo ================================================================

schtasks /Query /TN "%TASKNAME%" >nul 2>nul
if not errorlevel 1 (
  echo existing task found - deleting first
  schtasks /Delete /TN "%TASKNAME%" /F >nul
)

schtasks /Create /TN "%TASKNAME%" /TR "\"%TARGET%\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 16:10 /F
if errorlevel 1 (
  echo.
  echo [FAIL] registration failed
  echo   - run this file as Administrator ^(right click - Run as administrator^)
  pause
  exit /b 1
)

echo.
echo [OK] registered - weekdays 16:10
echo   check  : schtasks /Query  /TN "%TASKNAME%"
echo   run now: schtasks /Run    /TN "%TASKNAME%"
echo   remove : schtasks /Delete /TN "%TASKNAME%" /F
pause
