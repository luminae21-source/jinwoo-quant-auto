@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -m pip install -q finance-datareader pandas pykrx requests
%PY% fetch_kosdaq_daily_panel.py  > jq_scan_console.txt 2>&1
%PY% kosdaq_lane_scan_v1.py       >> jq_scan_console.txt 2>&1
%PY% snapshot_append.py           >> jq_scan_console.txt 2>&1
%PY% jq_breadth.py                >> jq_scan_console.txt 2>&1
%PY% jq_board.py                  >> jq_scan_console.txt 2>&1
