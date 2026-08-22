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
echo === jq_cards run === > jq_cards_log.txt
%PY% --version >> jq_cards_log.txt 2>&1
%PY% -m pip install -q pillow yfinance pandas certifi curl_cffi >> jq_cards_log.txt 2>&1
%PY% -X utf8 jq_cards.py >> jq_cards_log.txt 2>&1
echo --- deriv card --- >> jq_cards_log.txt
%PY% -X utf8 jq_deriv_card.py >> jq_cards_log.txt 2>&1
echo EXITCODE=%errorlevel% >> jq_cards_log.txt
echo --- kakao send --- >> jq_cards_log.txt
call jq_kakao_send.bat >> jq_cards_log.txt 2>&1
echo ===== DONE (6 cards + kakao). Log: jq_cards_log.txt =====
