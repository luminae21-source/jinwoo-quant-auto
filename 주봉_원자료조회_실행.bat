@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo 주봉 원자료(OHLC) 조회 중... 조회 전용, 무수정.
%PY% -m pip install -q pykrx pandas certifi
%PY% "주봉_원자료조회.py" > "주봉_원자료조회_결과.md" 2>&1
type "주봉_원자료조회_결과.md"
echo.
echo ===== DONE. 결과: 주봉_원자료조회_결과.md =====
if errorlevel 1 (echo. & echo [오류] 위 메시지 확인 & pause) else (exit)
