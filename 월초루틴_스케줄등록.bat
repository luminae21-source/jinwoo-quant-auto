@echo off
chcp 949 >nul
cd /d "%~dp0"
schtasks /Create /SC MONTHLY /D 1 /ST 09:10 /TN "Jinwoo_Monthly_Rebalance" /TR "\"%~dp0월초루틴.bat\"" /F
if %errorlevel%==0 (echo [OK] Registered: day 1 of every month 09:10 - Jinwoo_Monthly_Rebalance) else (echo [!] Failed - run as administrator)
echo Run now to test:  schtasks /Run /TN "Jinwoo_Monthly_Rebalance"
echo To remove:        schtasks /Delete /TN "Jinwoo_Monthly_Rebalance" /F
pause
