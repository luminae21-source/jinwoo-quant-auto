@echo off
chcp 949 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
set LOG=%~dp0monthly_log.txt
echo. >> "%LOG%"
echo ================= %date% %time% ================= >> "%LOG%"
echo [1/5] score_v37_2 (engine 02 quality) >> "%LOG%"
py score_v37_2.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] score_v37_2 >> "%LOG%") else (echo [OK] score_v37_2 >> "%LOG%")
echo [2/5] market regime >> "%LOG%"
py 시장국면.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] regime >> "%LOG%") else (echo [OK] regime >> "%LOG%")
echo [3/5] style panel (DART) >> "%LOG%"
py 스타일패널_DART.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] style panel >> "%LOG%") else (echo [OK] style panel >> "%LOG%")
echo [4/5] engine02 forward signal >> "%LOG%"
py 엔진02_신호.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] forward signal >> "%LOG%") else (echo [OK] forward signal >> "%LOG%")
echo [5/5] routine freshness >> "%LOG%"
py 루틴_신선도점검.py >> "%LOG%" 2>&1
echo ---- done ---- >> "%LOG%"
