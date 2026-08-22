@echo off
chcp 949 >nul
cd /d "%~dp0"
set LOG=%~dp0monthly_log.txt
echo. >> "%LOG%"
echo ================= %date% %time% ================= >> "%LOG%"
echo [1/5] score_v37_2 (engine 02 multifactor) >> "%LOG%"
py score_v37_2.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] score_v37_2 >> "%LOG%") else (echo [OK] score_v37_2 >> "%LOG%")
echo [2/5] market regime >> "%LOG%"
py 시장국면.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] regime >> "%LOG%") else (echo [OK] regime >> "%LOG%")
echo [3/5] routine freshness >> "%LOG%"
py 루틴_신선도점검.py >> "%LOG%" 2>&1
echo [4/5] style panel (DART) >> "%LOG%"
py 스타일패널_DART.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] style panel >> "%LOG%") else (echo [OK] style panel >> "%LOG%")
echo [5/5] engine02 forward signal >> "%LOG%"
py 실전준비\forward_signal.py --panel "%~dp0스타일패널_DART.csv" >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] forward signal >> "%LOG%") else (echo [OK] forward signal >> "%LOG%")
echo ---- done ---- >> "%LOG%"
