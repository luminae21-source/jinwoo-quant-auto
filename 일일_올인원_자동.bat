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
set LOG=ÀÏÀÏ_¿ÃÀÎ¿ø_log.txt
echo === JQ_DailyAllInOne %DATE% %TIME% === > %LOG%
%PY% -m pip install -q pykrx pandas openpyxl certifi >> %LOG% 2>&1
echo [1/4] ¿À´Ã »ó½ÂÁ¾¸ñ ºÐ·ù >> %LOG%
%PY% "¿À´Ã_»ó½ÂÁ¾¸ñ_ºÐ·ù.py" >> %LOG% 2>&1
echo [2/4] ±Þµî ÀÌÁß¹Ù´Ú ½ºÄµ >> %LOG%
%PY% "¿À´Ã_±Þµî_ÀÌÁß¹Ù´Ú½ºÄµ.py" >> %LOG% 2>&1
echo [3/4] 2ÁÖ °Å·¡´ë±Ý ¼öÁý >> %LOG%
%PY% "°Å·¡´ë±Ý_2ÁÖ_¼öÁý.py" >> %LOG% 2>&1
echo [4/4] ºä »ý¼º (¾Û/¸ð¹ÙÀÏ) >> %LOG%
%PY% "ºä»ý¼º.py" >> %LOG% 2>&1
echo EXITCODE=%errorlevel% >> %LOG%
exit /b %errorlevel%
