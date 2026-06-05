@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================================
echo  Jinwoo-Quant D+E : KOSDAQ combined revalidation + C1 backtest
echo  Folder: %CD%
echo  (KOSPI originals backed up once as *_KOSPI.bak ; rollback OK)
echo ============================================================
echo.

echo [0/6] Installing/checking python packages...
python -m pip install -q finance-datareader requests pandas numpy scipy statsmodels
python -c "import FinanceDataReader" 2>nul
if errorlevel 1 goto fdr_fail

echo [1/6] Backup KOSPI originals (first run only)...
if not exist fundamentals_pit_KOSPI.bak copy fundamentals_pit.csv fundamentals_pit_KOSPI.bak >nul
if not exist kospi_monthly_prices_KOSPI.bak copy kospi_monthly_prices.csv kospi_monthly_prices_KOSPI.bak >nul
if not exist korea_factors_monthly_KOSPI.bak copy korea_factors_monthly.csv korea_factors_monthly_KOSPI.bak >nul
if not exist liquidity_sector_KOSPI.bak copy liquidity_sector.csv liquidity_sector_KOSPI.bak >nul

echo [2/6] Fetch combined fundamentals (KOSPI+KOSDAQ top-600, several minutes)...
python fetch_dart_fundamentals_pit.py --market KOSPI,KOSDAQ --top-n 600 --start-year 2019 --end-year 2025
if errorlevel 1 goto fetch_fail

echo [3/6] Fetch combined monthly prices + factors...
python build_korea_factors.py --market KOSPI,KOSDAQ --top-n 600 --no-cache
if errorlevel 1 goto fetch_fail

echo [4/6] Refresh liquidity / sector...
python fetch_liquidity_sector.py

echo.
echo ===== D result: universe revalidation (check 196170 / 095340 no longer 'no data') =====
python universe_screen.py --top-n 18
python universe_rules.py
python sweep_universe_size.py --ks 18,30,50,100

echo.
echo ===== E result: C1 regime full backtest (gate: annual +1pp AND MDD worsening less than 0.5pp) =====
python backtest_c1.py --echo-on 1.5 --bab-on 0.0

echo.
echo ============================================================
echo  DONE. Copy ALL the text above and paste it back into the chat.
echo  Rollback: copy *_KOSPI.bak back to original names.
echo ============================================================
goto end

:fdr_fail
echo.
echo [ERROR] FinanceDataReader import failed.
echo Fix: pip install --upgrade pyopenssl urllib3
echo Then double-click run_DE.bat again.
goto end

:fetch_fail
echo.
echo [ERROR] Data fetch failed (network / DART key / FDR). See message above.
echo Your KOSPI originals are safe as *_KOSPI.bak (if step 1 ran).
goto end

:end
pause
