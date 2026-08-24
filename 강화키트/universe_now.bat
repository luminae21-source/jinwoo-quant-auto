@echo off
cd /d "%~dp0"
echo Running...
py -W ignore universe_now.py --now
if errorlevel 1 (
  echo.
  echo [ERROR] Python failed. Try:  py -m pip install pandas numpy finance-datareader
  pause
  exit /b 1
)
echo.
echo [DONE] Universe list saved in this folder.
pause
