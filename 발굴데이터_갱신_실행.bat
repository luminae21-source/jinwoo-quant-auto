@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
echo ================================================================
echo  refresh discovery daily data from 30yr panel (KOSDAQ fix)
echo ================================================================
echo.
py 발굴데이터_갱신.py --self-test
if errorlevel 1 ( echo. & echo [FAIL] self-test failed. & pause & exit /b 1 )
echo.
echo ---- regenerating pit_daily ----
echo.
py 발굴데이터_갱신.py
if errorlevel 1 ( echo. & echo [FAIL] runtime error. & pause & exit /b 1 )
echo.
echo done. next: py jq_discover.py --breakout
pause
