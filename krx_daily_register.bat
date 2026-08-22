@echo off
chcp 949 >nul
cd /d "%~dp0"
schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 18:20 /TN "Jinwoo_KRX_Daily" /TR "%~dp0krx_daily_run.bat" /F
if %errorlevel%==0 (echo [OK] Registered: weekdays 18:20 - Jinwoo_KRX_Daily) else (echo [!] Failed - run as administrator)
echo.
echo Test now:  schtasks /Run /TN "Jinwoo_KRX_Daily"
echo Remove  :  schtasks /Delete /TN "Jinwoo_KRX_Daily" /F
pause
