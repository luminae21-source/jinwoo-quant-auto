@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo ============================================================
echo  KOSDAQ 지수 30년 수집 + 게이트 시장분리 확정 판정 (한 번에)
echo  1) kosdaq_index_daily.csv 수집 (FDR KQ11, 1996~)
echo  2) 휩쏘_게이트감사_검정.py 재실행 → [검정4] 확정 판정 출력
echo ============================================================
%PY% -m pip install -q finance-datareader pandas certifi
copy /y "kosdaq_index_daily.csv" "kosdaq_index_daily_backup.csv" >nul 2>nul
%PY% "fetch_kosdaq_index_daily.py" --start 1996
if not exist "kosdaq_index_daily.csv" (echo. & echo [에러] 수집 실패 - 위 메시지 확인 & pause & exit /b 1)
echo.
echo ----- 게이트 감사 재실행 ([검정4] 확정 판정) -----
%PY% "휩쏘_게이트감사_검정.py"
echo.
echo ===== DONE. 위 [검정4] "확정 판정" 줄이 결론입니다. =====
pause
