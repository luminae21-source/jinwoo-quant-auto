@echo off
setlocal
cd /d "%~dp0"

set "PYTHONIOENCODING=utf-8"
set "SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem"
set "REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem"

REM --- cacert bundle: create from certifi if missing ---
if not exist "C:\Users\Public\jq_cacert.pem" (
  python -c "import certifi,shutil;shutil.copy(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul || py -c "import certifi,shutil;shutil.copy(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
)

REM --- detect python launcher (where python || py) ---
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py"
if not defined PY (
  echo [FAIL] Python not found. Install Python or add to PATH.
  pause
  exit /b 1
)

echo ================================================================
echo  KRX surge/rise scan (pykrx) - last trading day
echo  fetches KRX after market close. takes ~1-3 min.
echo ================================================================
echo.

echo ---- self-test (no network) ----
%PY% "급등종목스캔.py" --self-test
if errorlevel 1 (
  echo.
  echo [FAIL] self-test failed. aborting.
  pause
  exit /b 1
)

echo.
echo ---- main run ^(last trading day: rise^>0 all + surge^>=15%%^) ----
%PY% "급등종목스캔.py" %*
if errorlevel 1 (
  echo.
  echo [FAIL] runtime error. check pykrx / network / date.
  pause
  exit /b 1
)

echo.
echo [OK] done. output CSVs saved in this folder ^(sangseung_/geupdeung_YYYYMMDD^).
exit /b 0
