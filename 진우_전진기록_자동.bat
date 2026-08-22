@echo off
chcp 949 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo ============================================>>"%~dp0진우_전진기록_로그.txt"
echo [START] %DATE% %TIME%>>"%~dp0진우_전진기록_로그.txt"
py "%~dp0진우_전진기록.py" --snapshot --include-bounce >>"%~dp0진우_전진기록_로그.txt" 2>&1
echo [END] %DATE% %TIME% (exit %ERRORLEVEL%)>>"%~dp0진우_전진기록_로그.txt"
exit /b %ERRORLEVEL%
