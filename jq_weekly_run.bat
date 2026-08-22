@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
echo ==== JQ WEEKLY RUN ==== > jq_weekly_log.txt
echo PY=%PY% >> jq_weekly_log.txt
%PY% --version >> jq_weekly_log.txt 2>&1
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo ---- pip install ---- >> jq_weekly_log.txt
%PY% -m pip install -q pykrx pandas Pillow certifi >> jq_weekly_log.txt 2>&1
echo ---- run script ---- >> jq_weekly_log.txt
%PY% -X utf8 -c "import glob,runpy,os; c=[x for x in glob.glob('*.py') if not os.path.basename(x).startswith('_') and 'def to_weekly' in open(x,encoding='utf-8',errors='ignore').read()]; print('CANDIDATES',c); runpy.run_path(sorted(c,key=os.path.getsize)[-1], run_name='__main__')" >> jq_weekly_log.txt 2>&1
echo EXITCODE=%errorlevel% >> jq_weekly_log.txt
echo.
echo ===== DONE. Log: jq_weekly_log.txt =====
pause
