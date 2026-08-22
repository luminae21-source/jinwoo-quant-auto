@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  (1) high-vol x exit-rule interaction (30yr, delisting+cost)
echo  can a hard stop rescue high-vol trading? full ~10-25 min.
echo ================================================================
echo.

py 검정_고변동성_청산_30년.py --self-test
if errorlevel 1 (
  echo.
  echo [FAIL] self-test failed. aborting.
  pause
  exit /b 1
)

echo.
echo ---- main run ----
echo.
py 검정_고변동성_청산_30년.py %*
if errorlevel 1 (
  echo.
  echo [FAIL] runtime error.
  pause
  exit /b 1
)

echo.
echo result: 가상매매\검증\고변동성_청산_결과_base.md
echo tip: preview -  고변동성_청산_실행.bat --sample 800
pause
