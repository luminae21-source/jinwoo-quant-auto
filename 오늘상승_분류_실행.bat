@echo off
setlocal
cd /d "%~dp0"

set "PYTHONIOENCODING=utf-8"
set "SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem"
set "REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem"

echo ================================================================
echo  today's gainers - classification table
echo  fetches KRX (market close). ~1-3 min.
echo ================================================================
echo.

py 오늘_상승종목_분류.py --self-test
if errorlevel 1 (
  echo.
  echo [FAIL] self-test failed. aborting.
  pause
  exit /b 1
)

echo.
echo ---- main run (today, rise ^>= 5%% + limit-up) ----
echo.
py 오늘_상승종목_분류.py %*
if errorlevel 1 (
  echo.
  echo [FAIL] runtime error. check pykrx / network.
  pause
  exit /b 1
)

echo.
echo result: 가상매매\검증\오늘_상승종목_분류_YYYYMMDD.xlsx
pause
