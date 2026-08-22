@echo off
rem jq_kakao_send_merged.bat - merge today's 6 cards into ONE tall image and send it.
rem ASCII only, no chcp. Python handles Korean filenames + console encoding.
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo === jq_kakao_send_merged %DATE% %TIME% === > jq_kakao_merged_log.txt
%PY% -m pip install -q pillow certifi >> jq_kakao_merged_log.txt 2>&1
%PY% -X utf8 jq_kakao_send.py --merged >> jq_kakao_merged_log.txt 2>&1
echo EXITCODE=%errorlevel% >> jq_kakao_merged_log.txt
type jq_kakao_merged_log.txt
