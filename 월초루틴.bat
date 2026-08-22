@echo off
chcp 949 >nul
cd /d "%~dp0"
set LOG=%~dp0월초루틴_로그.txt
echo. >> "%LOG%"
echo ================= %date% %time% ================= >> "%LOG%"
echo [1/2] score_v37_2 (production - engine 02 multifactor) >> "%LOG%"
py score_v37_2.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] score_v37_2 >> "%LOG%") else (echo [OK] score_v37_2 >> "%LOG%")
echo [2/2] regime snapshot >> "%LOG%"
py 시장국면.py >> "%LOG%" 2>&1
if errorlevel 1 (echo [FAIL] regime >> "%LOG%") else (echo [OK] regime >> "%LOG%")
echo ---- done ---- >> "%LOG%"
