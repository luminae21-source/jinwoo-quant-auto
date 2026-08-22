@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"
set "SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem"
set "REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem"

echo ================================================================
echo  D-prep: KRX fundamental (PBR/PER) monthly backfill
echo  survivorship-safe by-date. month-ends only. resumable.
echo  availability: KOSPI 2002+, KOSDAQ 2006+ (probed 2026-07-16)
echo ================================================================
echo.

py fetch_fundamental_panel.py --self-test
if errorlevel 1 (
  echo.
  echo [FAIL] self-test failed. aborting.
  pause
  exit /b 1
)

echo.
echo ---- collect ----
echo  (probe separately with:  fetch_fundamental_panel.py --probe )
echo.
py fetch_fundamental_panel.py %*
if errorlevel 1 (
  echo.
  echo [FAIL] runtime error.
  pause
  exit /b 1
)

echo.
echo result: 辆格犁公_KRX_KOSPI.csv / 辆格犁公_KRX_KOSDAQ.csv
pause
