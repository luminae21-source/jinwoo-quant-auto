@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo === jq_deriv run === > jq_deriv_log.txt
%PY% -m pip install -q pillow requests certifi >> jq_deriv_log.txt 2>&1
%PY% -X utf8 jq_deriv_card.py >> jq_deriv_log.txt 2>&1
echo EXITCODE=%errorlevel% >> jq_deriv_log.txt
type jq_deriv_log.txt
echo ===== DONE. dump=jq_deriv_dump.txt =====
pause
