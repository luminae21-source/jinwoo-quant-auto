@echo off
chcp 949 >nul
cd /d "%~dp0"
schtasks /Create /SC MONTHLY /D 1 /ST 09:10 /TN "Jinwoo_Monthly_Rebalance" /TR "%~dp0monthly_run.bat" /F
if %errorlevel%==0 (echo [OK] Registered: day 1 every month 09:10) else (echo [!] Failed - run as administrator)
echo.
echo Test now:  schtasks /Run /TN "Jinwoo_Monthly_Rebalance"
echo Remove  :  schtasks /Delete /TN "Jinwoo_Monthly_Rebalance" /F
pause
