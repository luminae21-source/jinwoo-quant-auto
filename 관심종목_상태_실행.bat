@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
py 관심종목_상태.py --self-test
if errorlevel 1 ( echo. & echo [FAIL] self-test failed. & pause & exit /b 1 )
echo.
py 관심종목_상태.py %*
pause
