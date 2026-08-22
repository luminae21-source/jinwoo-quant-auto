@echo off
cd /d "%~dp0"
rem 로그보기.bat - UTF-8 로그를 콘솔에서 깨지지 않게 출력.
rem   type 은 cp949 로 읽어서 한글이 깨진다. 파일이 잘못된 게 아니라 표시 문제다.
rem 사용: 로그보기.bat            (로그 목록에서 고르기)
rem       로그보기.bat 익일예측_log.txt
rem       로그 파일을 이 배치 위로 드래그&드롭

if not "%~1"=="" goto SHOW

echo ============================================================
echo  로그 보기 (UTF-8)
echo ============================================================
echo.
echo  [1] 익일예측_log.txt          [2] 익일예측_kosdaq_log.txt
echo  [3] 만기후_체크_log.txt       [4] jq_cards_log.txt
echo  [5] jq_close_log.txt          [6] jq_tasks_log.txt
echo  [7] 익일예측_최신.md          [0] 직접 입력
echo.
set /p SEL=번호 선택:
if "%SEL%"=="1" set LOG=익일예측_log.txt
if "%SEL%"=="2" set LOG=익일예측_kosdaq_log.txt
if "%SEL%"=="3" set LOG=만기후_체크_log.txt
if "%SEL%"=="4" set LOG=jq_cards_log.txt
if "%SEL%"=="5" set LOG=jq_close_log.txt
if "%SEL%"=="6" set LOG=jq_tasks_log.txt
if "%SEL%"=="7" set LOG=익일예측_최신.md
if "%SEL%"=="0" set /p LOG=파일명 입력:
goto RUN

:SHOW
set LOG=%~1

:RUN
if not exist "%LOG%" (
  echo.
  echo [없음] "%LOG%" 파일이 없습니다.
  echo.
  pause
  exit /b 1
)
echo.
echo ------------------------------------------------------------
echo  %LOG%
echo ------------------------------------------------------------
powershell -NoProfile -Command "Get-Content -LiteralPath '%LOG%' -Encoding UTF8"
echo ------------------------------------------------------------
echo.
pause
