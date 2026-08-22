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
echo === JQ_DoubleBottomScan %DATE% %TIME% === > 오늘급등_이중바닥_log.txt
%PY% -m pip install -q pykrx pandas openpyxl certifi >> 오늘급등_이중바닥_log.txt 2>&1
%PY% "오늘_급등_이중바닥스캔.py" >> 오늘급등_이중바닥_log.txt 2>&1
echo EXITCODE=%errorlevel% >> 오늘급등_이중바닥_log.txt
exit /b %errorlevel%
