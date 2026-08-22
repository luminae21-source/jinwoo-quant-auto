@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo === JQ_PostExpiryCheck %DATE% %TIME% === > 만기후_체크_log.txt
%PY% -m pip install -q yfinance pykrx pandas certifi >> 만기후_체크_log.txt 2>&1
%PY% "만기후_체크.py" >> 만기후_체크_log.txt 2>&1
echo EXITCODE=%errorlevel% >> 만기후_체크_log.txt
exit /b %errorlevel%
