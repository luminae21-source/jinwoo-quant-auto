@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  Entry-edge screener (30yr panel, small/mid cap ranking)
echo  small=LowVol / mid=LowVol x LowPBR / large=excluded
echo  reads 14.7M rows. ~2-5 min.
echo ================================================================
echo.

py 진입엣지_스크리너.py --self-test
if errorlevel 1 (
  echo [FAIL] self-test
  pause
  exit /b 1
)

echo.
echo ---- screening (backtest filters: price>=1000, adv20>=0.5B) ----
echo.
py 진입엣지_스크리너.py %*
if errorlevel 1 (
  echo [FAIL] runtime
  pause
  exit /b 1
)

echo.
echo result: 진입엣지_후보.csv
echo tip: py 진입엣지_스크리너.py --top 20   /   --asof 2026-07-13
pause
