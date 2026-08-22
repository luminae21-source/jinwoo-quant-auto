@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
where python >nul 2>nul && (set PY=python) || (set PY=py)
set LOG=jq_daily_update_console.txt
echo JINWOO QUANT - KOSPI daily update + verify > "%LOG%"
echo start %DATE% %TIME% >> "%LOG%"
echo [1] python check...
%PY% --version >> "%LOG%" 2>&1
if errorlevel 1 ( echo [ERROR] Python not found - install from python.org + Add to PATH & echo [ERROR] python not found >> "%LOG%" & goto end )
echo [2] libs (first run only)...
%PY% -m pip install -q finance-datareader pandas pyopenssl cryptography >> "%LOG%" 2>&1
echo [3] fetch KOSPI daily (584 stocks, a few min)...
%PY% fetch_kospi_daily_full.py >> "%LOG%" 2>&1
echo [4] verify reconcile gate (kospi)...
%PY% verify_weekly_reconcile.py --market kospi >> "%LOG%" 2>&1
echo finished %DATE% %TIME% >> "%LOG%"
echo.
echo ---- result ----
findstr /C:"status =" "%LOG%"
findstr /C:"status = PASS" "%LOG%" >nul && (echo [OK] PASS - weekly / entry / trend will use fresh data.) || (echo [WARN] NOT PASS - check %LOG% before trusting weekly charts.)
echo (full log: %LOG%)
:end
