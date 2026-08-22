@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  Factor-combo test: LowVol x LowPBR intersection - 30yr panel
echo  reads 14.7M rows + monthly double-sort. may take 5-15 min.
echo ================================================================
echo.

py 검정_팩터결합_저변동성_저PBR.py --self-test
if errorlevel 1 (
  echo [FAIL] self-test failed. aborting.
  pause
  exit /b 1
)

echo.
echo ---- main run: LowVol x LowPBR, IN 2002-2012 / OOS 2013-2026 ----
echo.
py 검정_팩터결합_저변동성_저PBR.py %*
if errorlevel 1 (
  echo [FAIL] runtime error.
  pause
  exit /b 1
)

echo.
echo result: 가상매매\검증\팩터결합_저변동성_저PBR_결과_base.md (민감도는 _결과_conservative.md)
echo tip: preview with  --sample 1500   . sensitivity with  --delisting conservative
pause
