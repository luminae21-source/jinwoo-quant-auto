@echo off
cd /d "%~dp0"
schtasks /Create /TN "JinwooQuant_Recommend_Weekly" /TR "\"%~dp0recommend_auto.bat\"" /SC WEEKLY /D MON /ST 08:25 /F
echo.
echo Registered: JinwooQuant_Recommend_Weekly - every Monday 08:25
echo   Check:  schtasks /Query /TN "JinwooQuant_Recommend_Weekly"
echo   Remove: schtasks /Delete /TN "JinwooQuant_Recommend_Weekly" /F
pause
