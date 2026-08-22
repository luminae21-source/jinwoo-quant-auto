@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo KOSPI 지수 일봉 재수집 (1995~현재). kospi_index_daily.csv 전체 덮어쓰기.
echo 주의: --start 1995 필수. 인자를 빼면 스크립트 기본값이 2010이라 1995~2010 구간이 사라집니다.
%PY% -m pip install -q finance-datareader pandas certifi
copy /y "kospi_index_daily.csv" "kospi_index_daily_backup.csv" >nul 2>nul
%PY% "fetch_kospi_index_daily.py" --start 1995
echo.
echo ===== DONE. 행수/기간이 1995~오늘로 찍혔는지 위에서 확인하세요. =====
echo 이후: 가상매매\엔진\할로윈_검증_실행.bat 을 다시 돌려 재판정.
if errorlevel 1 (echo. & echo [오류] 위 메시지 확인 & pause) else (exit)
