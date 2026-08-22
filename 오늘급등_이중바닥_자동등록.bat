@echo off
chcp 949 >nul
cd /d "%~dp0"
echo [JQ] Registering daily double-bottom surge scan (weekdays 18:30)...
schtasks /create /tn "JQ_DoubleBottomScan" /tr "\"%~dp0오늘급등_이중바닥_자동.bat\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 18:30 /f
if errorlevel 1 (
  echo.
  echo [FAIL] 등록 실패 - 관리자 권한으로 재시도하거나 먼저 삭제 후 재시도:
  echo     schtasks /delete /tn "JQ_DoubleBottomScan" /f
  pause
  exit /b 1
)
echo.
echo [OK] "JQ_DoubleBottomScan" 등록됨: 평일(월~금) 18:30 자동 실행.
echo 확인: schtasks /query /tn "JQ_DoubleBottomScan"
echo 삭제: schtasks /delete /tn "JQ_DoubleBottomScan" /f
pause
