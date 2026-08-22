@echo off
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  echo [권한] 예약작업 등록에는 관리자 권한이 필요합니다. 관리자로 다시 실행합니다...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo ============================================================
echo  JQ_SurgeScan 등록 - 평일(월~금) 16:10, 급등종목스캔_자동.bat
echo ============================================================
echo.

REM 실행 중 인스턴스가 있으면 종료
schtasks /end /tn "JQ_SurgeScan" >nul 2>&1

schtasks /create /tn "JQ_SurgeScan" /tr "\"%~dp0급등종목스캔_자동.bat\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 16:10 /f
if errorlevel 1 (
  echo.
  echo  [실패] JQ_SurgeScan 등록 실패.
  echo    - 이 창이 관리자 권한인지 확인 ^(제목표시줄에 관리자^)
  echo    - 작업 스케줄러에서 해당 작업 잠금 여부 확인
  echo    - 잠시 후 다시 실행
  echo.
  pause
  exit /b 1
)

echo.
echo  [성공] JQ_SurgeScan -^> 급등종목스캔_자동.bat  ^(평일 16:10^)
echo.
echo  등록 상태 확인 ^(jq_verify_tasks.bat^)...
echo.
call "%~dp0jq_verify_tasks.bat"
exit /b 0
