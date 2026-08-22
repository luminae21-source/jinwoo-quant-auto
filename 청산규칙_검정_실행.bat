@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  B: exit-rule test (30yr panel, delisting built-in)
echo  reading 14.7M rows + per-stock trade sim. may take 5-15 min.
echo ================================================================
echo.

py 검정_청산규칙_30년.py --self-test
if errorlevel 1 (
  echo.
  echo [FAIL] self-test failed. aborting.
  pause
  exit /b 1
)

echo.
echo ---- main run (entry=monthly, delisting=base) ----
echo.
py 검정_청산규칙_30년.py %*
if errorlevel 1 (
  echo.
  echo [FAIL] runtime error.
  pause
  exit /b 1
)

echo.
echo result: 가상매매\검증\청산규칙_검정_결과.md
echo.
echo tip: 2nd entry scenario:  청산규칙_검정_실행.bat --entry momentum
echo      sensitivity:          청산규칙_검정_실행.bat --delisting conservative
pause
