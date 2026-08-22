@echo off
chcp 949 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo ================================================================
echo  2-week trading value + recent OHLC collector (fetches KRX)
echo ================================================================
%PY% -m pip install -q pykrx pandas certifi >nul 2>&1
py 거래대금_2주_수집.py --self-test
if errorlevel 1 ( echo [FAIL] self-test failed. & pause & exit /b 1 )
echo.
echo ---- main run (last 12 trading days) ----
py 거래대금_2주_수집.py %*
if errorlevel 1 ( echo [FAIL] runtime error. check pykrx/network. & pause & exit /b 1 )
echo.
echo result: 가상매매\검증\_거래대금2주_YYYYMMDD.csv  +  _recent_ohlc_YYYYMMDD.csv
pause
