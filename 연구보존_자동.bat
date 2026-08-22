@echo off
setlocal
chcp 949 >nul
cd /d "%~dp0"
rem === scheduled-task launcher: index/hub/whitepaper refresh + vault backup ===
rem force UTF-8 so python does not die on Korean output when redirected
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set "LOG=%~dp0연구보존_자동_log.txt"
>>"%LOG%" echo.
>>"%LOG%" echo ============================================
>>"%LOG%" echo [START] %DATE% %TIME%
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0금고_백업.ps1" -Force >>"%LOG%" 2>&1
set RC=%ERRORLEVEL%
>>"%LOG%" echo [END] %DATE% %TIME% (exit %RC%)
rem trim log when it grows past 1MB
for %%A in ("%LOG%") do if %%~zA GTR 1000000 powershell -NoProfile -Command "Get-Content -LiteralPath $env:LOG -Tail 400 | Set-Content -LiteralPath ($env:LOG + '.tmp'); Move-Item -LiteralPath ($env:LOG + '.tmp') -Destination $env:LOG -Force"
endlocal & exit /b %RC%
