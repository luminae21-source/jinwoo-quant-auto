@echo off
setlocal
cd /d "%~dp0"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
where python >nul 2>nul && (set "PY=python") || (set "PY=py")
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set "SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem"
set "CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem"
set "REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem"

set "LOG=±Þµî½ºÄµ_log.txt"
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format \"yyyy-MM-dd HH:mm\""') do set "NOW=%%i"
echo.>> "%LOG%"
echo === %NOW% ===>> "%LOG%"

%PY% "±ÞµîÁ¾¸ñ½ºÄµ.py" --self-test >> "%LOG%" 2>&1
if errorlevel 1 (
  echo SELF-TEST FAILED - abort>> "%LOG%"
  echo EXITCODE=1>> "%LOG%"
  exit /b 1
)

%PY% "±ÞµîÁ¾¸ñ½ºÄµ.py" >> "%LOG%" 2>&1
set "RC=%errorlevel%"
echo EXITCODE=%RC%>> "%LOG%"
exit /b %RC%
