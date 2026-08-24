@echo off
cd /d "%~dp0"
schtasks /Create /TN "JinwooQuant_Reverify_Monthly" /TR "\"%~dp0recommend_verify.bat\"" /SC MONTHLY /D 6 /ST 09:00 /F
echo.
echo Registered: JinwooQuant_Reverify_Monthly - day 6 of each month, 09:00
echo   Check:  schtasks /Query /TN "JinwooQuant_Reverify_Monthly"
echo   Remove: schtasks /Delete /TN "JinwooQuant_Reverify_Monthly" /F
pause
