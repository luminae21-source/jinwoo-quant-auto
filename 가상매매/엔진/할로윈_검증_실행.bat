@echo off
setlocal
rem ==========================================================================
rem  할로윈 계절성 검증 (KOSPI 실데이터)
rem  * ANSI(cp949) 저장. chcp 금지 (한글 경로에서 실행 실패함)
rem  * 한글 사용자경로 -> SSL 인증서 경로 깨짐 -> cacert 를 공용 경로로 복사해 우회
rem ==========================================================================
cd /d "%~dp0"

rem --- Python 런처 폴백 ---
where python >nul 2>nul && (set PY=python) || (set PY=py)

rem --- 한글경로 SSL 우회: certifi 인증서를 ASCII 경로로 복사 ---
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
if exist "C:\Users\Public\jq_cacert.pem" (
    set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
    set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
    set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
)

rem --- 오래된 바이트코드 캐시가 새 코드를 가리는 문제 방지 ---
set PYTHONDONTWRITEBYTECODE=1

echo.
echo ==========================================================
echo  할로윈 계절성 검증 (KOSPI 실데이터)
echo ==========================================================
echo.

%PY% "할로윈_검증.py" %*


if errorlevel 1 goto FAIL
echo.
echo [완료] 산출물은 진우퀀트\가상매매\ 아래에 저장되었습니다.
echo        실행 로그: 가상매매\실행이력\
exit

:FAIL
echo.
echo [실패] 위 오류 메시지를 확인하세요. 로그: 가상매매\실행이력\
pause
