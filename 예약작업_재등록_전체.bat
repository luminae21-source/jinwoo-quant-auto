@echo off
cd /d "%~dp0"
set FAILED=0

net session >nul 2>&1
if errorlevel 1 (
  echo [권한] 예약작업 수정에는 관리자 권한이 필요합니다. 상승해서 다시 실행합니다...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo ============================================================
echo  예약작업 재등록 (익일예측 KOSPI / KOSDAQ / 만기후체크)
echo  기존 작업 삭제 -^> pause 없는 _자동.bat 으로 재등록 -^> 점검
echo ============================================================
echo.

echo [1/3] 멈춰 있을 수 있는 인스턴스 종료
schtasks /end /tn "JQ_DailyPredict" >nul 2>&1
schtasks /end /tn "JQ_DailyPredictKQ" >nul 2>&1
schtasks /end /tn "JQ_PostExpiryCheck" >nul 2>&1
echo   종료 시도 완료 (실행 중 아니면 무시됨)
echo.

echo [2/3] 기존 작업 삭제
schtasks /delete /tn "JQ_DailyPredict" /f >nul 2>&1
if errorlevel 1 (echo   - "JQ_DailyPredict" : 없거나 이미 삭제됨) else (echo   - "JQ_DailyPredict" : 삭제됨)
schtasks /delete /tn "JQ_DailyPredictKQ" /f >nul 2>&1
if errorlevel 1 (echo   - "JQ_DailyPredictKQ" : 없거나 이미 삭제됨) else (echo   - "JQ_DailyPredictKQ" : 삭제됨)
schtasks /delete /tn "JQ_PostExpiryCheck" /f >nul 2>&1
if errorlevel 1 (echo   - "JQ_PostExpiryCheck" : 없거나 이미 삭제됨) else (echo   - "JQ_PostExpiryCheck" : 삭제됨)

echo.
echo [3/3] 재등록
schtasks /create /tn "JQ_DailyPredict" /tr "\"%~dp0익일예측_자동.bat\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 07:30 /f >nul 2>&1
if errorlevel 1 (
  echo   [실패] "JQ_DailyPredict"
  set FAILED=1
) else (
  echo   [성공] "JQ_DailyPredict"  -^> 익일예측_자동.bat
)
schtasks /create /tn "JQ_DailyPredictKQ" /tr "\"%~dp0익일예측_kosdaq_자동.bat\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 07:35 /f >nul 2>&1
if errorlevel 1 (
  echo   [실패] "JQ_DailyPredictKQ"
  set FAILED=1
) else (
  echo   [성공] "JQ_DailyPredictKQ"  -^> 익일예측_kosdaq_자동.bat
)
schtasks /create /tn "JQ_PostExpiryCheck" /tr "\"%~dp0만기후_체크_자동.bat\"" /sc WEEKLY /d FRI /st 16:00 /f >nul 2>&1
if errorlevel 1 (
  echo   [실패] "JQ_PostExpiryCheck"
  set FAILED=1
) else (
  echo   [성공] "JQ_PostExpiryCheck"  -^> 만기후_체크_자동.bat
)

echo.
echo ============================================================
if "%FAILED%"=="1" (
  echo  [결과] 일부 실패. 아래를 확인하세요.
  echo    - 이 창이 관리자 권한인지
  echo    - 다른 프로그램이 해당 작업을 잠그고 있는지
  echo    - 작업 스케줄러를 열어 수동 삭제 후 재시도
  echo ============================================================
  pause
  exit /b 1
)
echo  [결과] 3개 모두 재등록 성공.
echo ============================================================
echo.
echo 점검 실행 (jq_verify_tasks.bat)...
echo.
call "%~dp0jq_verify_tasks.bat"
exit /b 0
