@echo off
chcp 949 >nul
cd /d "%~dp0"
schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 15:35 /TN "Jinwoo_4H_Collect" /TR "\"%~dp0fetch_4½Ã°£ºÀ_ÀÚµ¿.bat\"" /F
if %errorlevel%==0 (echo [OK] Registered: weekdays 15:35 - Jinwoo_4H_Collect) else (echo [!] Failed - try running as admin)
echo To remove:  schtasks /Delete /TN "Jinwoo_4H_Collect" /F
pause
