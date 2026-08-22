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
echo  daily all-in-one : classify -^> double-bottom -^> value -^> views
echo ================================================================
echo [1/4] classification...
%PY% "오늘_상승종목_분류.py" || ( echo [FAIL] classify & pause & exit /b 1 )
echo [2/4] double-bottom scan...
%PY% "오늘_급등_이중바닥스캔.py" || ( echo [FAIL] scan & pause & exit /b 1 )
echo [3/4] 2-week trading value...
%PY% "거래대금_2주_수집.py" || ( echo [FAIL] value & pause & exit /b 1 )
echo [4/4] build views (app/mobile)...
%PY% "뷰생성.py" || ( echo [FAIL] views & pause & exit /b 1 )
echo.
echo result: 가상매매\검증\급등_이중바닥_거래대금_앱_YYYYMMDD.html + 모바일
pause
