@echo off
cd /d "%~dp0"
py -m pip install --quiet pandas numpy
echo ============================================================
echo  Jinwoo Quant - re-verification suite
echo  (run after new monthly financials arrive)
echo ============================================================
echo [1/6] factor efficacy...
py -W ignore factor_efficacy.py
echo [2/6] style-conditional factors (all splits)...
py -W ignore style_conditional_factor.py --split all
echo [3/6] entry timing...
py -W ignore entry_timing_test.py
echo [4/6] exit routing...
py -W ignore exit_routing_backtest.py
echo [5/6] EV/FCF factors...
py -W ignore ev_fcf_factor_test.py
echo [6/6] multifactor screen...
py -W ignore multifactor_screen.py
echo.
echo [+] archiving to history DB and refreshing hub...
py -W ignore jq_history.py
py -W ignore jq_hub.py
echo.
echo Done - reports regenerated, history archived, hub refreshed.
timeout /t 6 >nul
