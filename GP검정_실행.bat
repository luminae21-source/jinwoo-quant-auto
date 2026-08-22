@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  GP profitability factor test (short window IN2015-19/OOS2020-26)
echo  reads 14.7M rows. run AFTER collection. ~5-15 min.
echo ================================================================
echo.

py 검정_GP수익성_단기창.py --self-test
if errorlevel 1 (
  echo [FAIL] selftest
  pause
  exit /b 1
)

echo.
echo ---- main run (GP quintiles, delisting+cost built-in) ----
echo.
py 검정_GP수익성_단기창.py --fund fundamentals_gp_2015_2025.csv,fundamentals_pit.csv,fundamentals_kosdaq.csv %*
if errorlevel 1 (
  echo [FAIL] runtime
  pause
  exit /b 1
)

echo.
echo result: 가상매매\검증\GP수익성_검정_결과_base.md
echo tip: preview -  GP검정_실행.bat --sample 1500
pause
