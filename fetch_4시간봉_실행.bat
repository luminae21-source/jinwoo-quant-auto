@echo off
chcp 949 >nul
cd /d "%~dp0"
echo ===== KIS 4H Bar Collector =====
if not exist ".kis_key" (
  echo [!] .kis_key not found. Copy .kis_key.example to .kis_key and paste APP Key/Secret.
  pause
  exit /b
)
pip install requests pandas --quiet 2>nul
python "fetch_4½Ã°£ºÀ_KIS.py" %*
echo.
pause
