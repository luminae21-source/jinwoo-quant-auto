@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
echo === guide run === > jq_guide_log.txt
%PY% --version >> jq_guide_log.txt 2>&1
%PY% -m pip install -q Pillow >> jq_guide_log.txt 2>&1
%PY% -X utf8 jq_trade_guide.py >> jq_guide_log.txt 2>&1
echo EXITCODE=%errorlevel% >> jq_guide_log.txt
echo.
echo ===== DONE. Log: jq_guide_log.txt =====
pause
