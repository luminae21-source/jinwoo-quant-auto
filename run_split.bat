@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
echo ============================================================
echo  KOSPI/KOSDAQ market-relative split screen
echo  (builds market_map.csv via FDR on first run, then screens)
echo ============================================================
python -c "import FinanceDataReader" 2>nul
if errorlevel 1 goto fdr_fail
python kosdaq_relative_screen.py
echo.
echo ============================================================
echo  DONE. Copy ALL the output above and paste it into the chat.
echo ============================================================
goto end
:fdr_fail
echo [ERROR] FinanceDataReader import failed. Run: pip install --upgrade pyopenssl urllib3
:end
pause
