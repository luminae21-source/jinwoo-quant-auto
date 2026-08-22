@echo off
chcp 949 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo Weekly technical analysis...
%PY% -m pip install -q pykrx pandas certifi
%PY% "주봉분석.py"
echo.
echo ===== DONE. Check the md file in this folder. =====
if errorlevel 1 (echo. & echo [오류] 위 메시지 확인 & pause) else (exit)
