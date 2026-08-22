@echo off
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
  echo [권한] 예약작업 수정에는 관리자 권한이 필요합니다. 상승해서 다시 실행합니다...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
echo [JQ] Registering post-expiry check (Fri 16:00)...
schtasks /create /tn "JQ_PostExpiryCheck" /tr "\"%~dp0만기후_체크_자동.bat\"" /sc WEEKLY /d FRI /st 16:00 /f
if errorlevel 1 (
  echo.
  echo [실패] "JQ_PostExpiryCheck" 등록 실패.
  echo   1) 이 창이 관리자 권한인지 확인하세요.
  echo   2) 그래도 안 되면 먼저 삭제 후 재시도:
  echo        schtasks /delete /tn "JQ_PostExpiryCheck" /f
  echo   3) 한 번에 처리하려면: 예약작업_재등록_전체.bat
  echo.
  pause
  exit /b 1
)
echo [성공] "JQ_PostExpiryCheck" 등록됨.
echo 확인: jq_verify_tasks.bat   ·   삭제: schtasks /delete /tn "JQ_PostExpiryCheck" /f
timeout /t 3 >nul
exit /b 0
