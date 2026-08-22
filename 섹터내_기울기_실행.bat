@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  (2) sector-internal tilt (jinwu tech-manufacturing universe)
echo  do cheaper/calmer stocks win WITHIN the sector? ~3-8 min.
echo ================================================================
echo.

py 검정_섹터내_기울기_30년.py --self-test
if errorlevel 1 (
  echo.
  echo [FAIL] self-test failed. aborting.
  pause
  exit /b 1
)

echo.
echo ---- main run ----
echo.
py 검정_섹터내_기울기_30년.py %*
if errorlevel 1 (
  echo.
  echo [FAIL] runtime error.
  pause
  exit /b 1
)

echo.
echo result: 가상매매\검증\섹터내_기울기_결과.md
pause
