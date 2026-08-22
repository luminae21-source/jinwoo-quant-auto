@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
where python >nul 2>nul && (set PY=python) || (set PY=py)
echo ============================================
echo  JINWOO QUANT - theme lane full scan
echo ============================================
echo [1] checking python...
%PY% --version
if errorlevel 1 ( echo [ERROR] Python not found. Install from python.org with 'Add to PATH'. & pause & exit /b )
echo [2] installing libraries (first run only)...
%PY% -m pip install -q finance-datareader pandas pykrx requests
echo [3] fetching theme prices (1-2 min)...
%PY% fetch_kosdaq_daily_panel.py
echo [4] integrated scan (gate x catalyst x flow)...
%PY% kosdaq_lane_scan_v1.py
echo [5] market snapshot (feature log)...
%PY% snapshot_append.py
echo [6] market breadth/concentration...
%PY% jq_breadth.py
echo [7] decision board...
%PY% jq_board.py
echo.
echo DONE. Open the decision board .md and paste the result to Claude.
pause >nul
