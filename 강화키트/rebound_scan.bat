@echo off
cd /d "%~dp0"
echo Running...
py -W ignore rebound_scan.py
if errorlevel 1 (
  echo.
  echo [ERROR] Python failed. Try:  py -m pip install pandas numpy finance-datareader
  rem 스케줄러에서 pause 는 무한 대기 → timeout 으로 대체
  timeout /t 20 >nul 2>&1
  exit /b 1
)
echo.
echo [DONE] Rebound scan saved (see the .csv and .html).
rem 스케줄러에서 pause 는 무한 대기 → timeout 으로 대체
timeout /t 20 >nul 2>&1
