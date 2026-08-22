@echo off
setlocal
cd /d "%~dp0"

set "PYTHONIOENCODING=utf-8"
set "SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem"
set "REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem"

echo ================================================================
echo  today's surge - double-bottom cycle scan (weekly -^> daily)
echo  universe = today rise ^>= 5%% + limit-up. fetches KRX. ~1-3 min.
echo ================================================================
echo.

py 오늘_급등_이중바닥스캔.py --self-test
if errorlevel 1 (
  echo.
  echo [FAIL] self-test failed. aborting.
  pause
  exit /b 1
)

echo.
echo ---- main run (weekly double-bottom first, then daily) ----
echo.
py 오늘_급등_이중바닥스캔.py %*
if errorlevel 1 (
  echo.
  echo [FAIL] runtime error. check pykrx / network / openpyxl.
  pause
  exit /b 1
)

echo.
echo result: 가상매매\검증\오늘_급등_이중바닥_YYYYMMDD.xlsx
pause
