@echo off
set "TASKBAT=%~dp0universe_now.bat"
schtasks /Create /TN "JinwooQuant_Universe_Monthly" /TR "\"%TASKBAT%\"" /SC MONTHLY /D 1 /ST 08:30 /F
if errorlevel 1 (
  echo.
  echo [ERROR] Register failed. You can still run universe_now.bat manually each month.
  pause
  exit /b 1
)
echo.
echo [DONE] Task JinwooQuant_Universe_Monthly registered - monthly, day 1, 08:30.
echo   Check:  schtasks /Query /TN "JinwooQuant_Universe_Monthly"
echo   Remove: schtasks /Delete /TN "JinwooQuant_Universe_Monthly" /F
pause
