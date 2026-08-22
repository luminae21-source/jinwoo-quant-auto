@echo off
chcp 949 >nul
cd /d "%~dp0"
if not exist ".kis_key" (echo %date% %time% no .kis_key >> "4시간봉_수집로그.txt" & exit /b)
echo ===== run %date% %time% ===== >> "4시간봉_수집로그.txt"
python "fetch_4시간봉_KIS.py" >> "4시간봉_수집로그.txt" 2>&1
