@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo === JQ_CloseCards %DATE% %TIME% === > jq_close_log.txt
%PY% -m pip install -q pillow >> jq_close_log.txt 2>&1
%PY% -X utf8 jq_close_card.py >> jq_close_log.txt 2>&1
%PY% -X utf8 jq_close_stocks.py >> jq_close_log.txt 2>&1
%PY% -X utf8 jq_watch_card.py >> jq_close_log.txt 2>&1
echo --- kakao send --- >> jq_close_log.txt
call jq_kakao_send.bat >> jq_close_log.txt 2>&1
echo EXITCODE=%errorlevel% >> jq_close_log.txt
exit /b %errorlevel%
