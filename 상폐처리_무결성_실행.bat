@echo off
setlocal
cd /d "%~dp0"

set "PYTHONIOENCODING=utf-8"
set "SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem"
set "REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem"

echo ================================================================
echo  (A) sangpye + integrity check
echo  reading 14.7M rows. may take 2-5 minutes.
echo ================================================================
echo.

py 검정_상폐처리_무결성.py --self-test
if errorlevel 1 (
  echo.
  echo [FAIL] self-test failed. aborting.
  pause
  exit /b 1
)

echo.
echo ---- main run ----
echo.
py 검정_상폐처리_무결성.py
if errorlevel 1 (
  echo.
  echo [FAIL] runtime error.
  pause
  exit /b 1
)

echo.
echo result: 가상매매\검증\상폐처리_무결성_결과.md
pause
