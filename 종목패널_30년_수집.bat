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
echo  개별종목 일봉 30년 패널 수집 (생존편향 차단)
echo ============================================================
echo.
echo  * 상폐된 종목까지 포함합니다 (과거 시점의 상장 리스트를 그때 기준으로 수집)
echo  * 종목 수천 개 x 1회 호출 -^> 1~3시간 예상. PC 켜두고 주무셔도 됩니다.
echo  * 중간에 끊겨도 다시 실행하면 이어받습니다 (_fetch_30y_ckpt.json)
echo.
%PY% -m pip install -q pykrx pandas certifi
%PY% "fetch_stock_panel_30y.py" --start 1995 %*
echo.
echo ===== DONE =====
echo  산출: 종목일봉_30년_KOSPI.csv / 종목일봉_30년_KOSDAQ.csv / 종목시총_30년.csv
if errorlevel 1 (echo. & echo [중단/오류] 다시 실행하면 이어받습니다 & pause) else (pause)
