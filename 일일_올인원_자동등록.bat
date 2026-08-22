@echo off
chcp 949 >nul
cd /d "%~dp0"
echo [JQ] Registering daily all-in-one (weekdays 18:40)...
schtasks /create /tn "JQ_DailyAllInOne" /tr "\"%~dp0일일_올인원_자동.bat\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 18:40 /f
if errorlevel 1 ( echo [FAIL] 등록 실패 - 관리자 권한 필요할 수 있음. & pause & exit /b 1 )
schtasks /delete /tn "JQ_DoubleBottomScan" /f >nul 2>&1
echo.
echo [OK] "JQ_DailyAllInOne" 평일 18:40 등록.
echo   포함: 분류 -^> 이중바닥 -^> 거래대금 -^> 뷰(앱/모바일) 자동 생성.
echo   (기존 JQ_DoubleBottomScan 은 여기에 포함되어 삭제했습니다.)
echo 확인: schtasks /query /tn "JQ_DailyAllInOne"   삭제: schtasks /delete /tn "JQ_DailyAllInOne" /f
pause
