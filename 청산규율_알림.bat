@echo off
chcp 949 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem

echo ================================================================
echo  cheongsan-gyuyul : daily distribution alert
echo ================================================================

echo [1/2] daily bars incremental update...
if exist "진우_일봉_증분수집.py" (
  %PY% "진우_일봉_증분수집.py"
  if errorlevel 1 echo   [WARN] fetch failed - using existing data
) else (
  echo   [SKIP] no incremental fetcher
)

echo [2/2] distribution check + kakao...
%PY% "청산규율_알림.py" %*
if errorlevel 2 (
  echo [FAIL] alert error
  exit /b 1
)
echo done.
