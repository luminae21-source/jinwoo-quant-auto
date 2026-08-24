@echo off
cd /d "%~dp0"
echo ============================================================
echo  Jinwoo Quant - FULL rebuild (DART depr + EV/FCF + overseas)
echo  one click. needs internet on this PC. takes ~10-15 min.
echo ============================================================
py -m pip install --quiet requests yfinance finance-datareader pandas numpy
echo.
echo [1/5] DART EBITDA rebuild (improved depreciation matching)...
py -W ignore dart_value_factors.py --rebuild
echo.
echo [2/5] EV/FCF factor re-test (new EBITDA coverage)...
py -W ignore ev_fcf_factor_test.py
echo.
echo [3/5] overseas correlation (US / HK peers)...
py -W ignore overseas_corr.py
echo.
echo [4/5] archive to history DB...
py -W ignore jq_history.py
echo.
echo [5/5] refresh hub...
py -W ignore jq_hub.py
echo.
echo === DONE. open the hub HTML in this folder. ===
pause
