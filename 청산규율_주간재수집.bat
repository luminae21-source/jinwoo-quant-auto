@echo off
chcp 949 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem

echo ================================================================
echo  weekly : rebuild adjusted daily bars (CA re-anchor)
echo  daily alert splices raw bars in between - run this once a week
echo ================================================================

%PY% "데이터수리\collect_adjusted_daily.py" --market KOSPI
if errorlevel 1 echo   [WARN] KOSPI failed
%PY% "데이터수리\collect_adjusted_daily.py" --market KOSDAQ
if errorlevel 1 echo   [WARN] KOSDAQ failed
echo done.
pause
