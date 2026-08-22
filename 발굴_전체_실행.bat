@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
echo ================================================================
echo  discovery all-in-one : state table + stable + breakout
echo ================================================================

echo.
echo ################## 1) my watchlist state ##################
py 관심종목_상태.py
echo.
echo ################## 2) STABLE mode (calm / value) ##################
py jq_discover.py %*
echo.
echo ################## 3) BREAKOUT mode (jinwu high-vol style) ##################
py jq_discover.py --breakout %*
echo.
echo ---- done. reminder: discovery is NOT a buy signal. ----
pause
