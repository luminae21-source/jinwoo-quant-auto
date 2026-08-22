@echo off
chcp 949 >nul
cd /d "%~dp0"
set LOG=%~dp0monthly_log.txt
echo. >> "%LOG%"
echo ================= %date% %time% ================= >> "%LOG%"
echo [1/3] score_v37_2 (engine 02 multifactor) >> "%LOG%"
py score_v37_2.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] score_v37_2 >> "%LOG%") else (echo [OK] score_v37_2 >> "%LOG%")
echo [2/3] market regime >> "%LOG%"
py 시장국면.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] regime >> "%LOG%") else (echo [OK] regime >> "%LOG%")
echo [3/3] routine freshness >> "%LOG%"
py 루틴_신선도점검.py >> "%LOG%" 2>&1
echo ---- done ---- >> "%LOG%"
