@echo off
chcp 949 >nul
cd /d "%~dp0"
echo [JQ] Registering weekly-chart analysis (weekdays 18:00)...
schtasks /create /tn "JQ_WeeklyChart" /tr "\"%~dp0주봉분석_자동.bat\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 18:00 /f
echo.
echo 등록되면 평일 18시 자동: 주봉 md + 카드뉴스 png 생성 + OneDrive 복사.
echo 삭제: schtasks /delete /tn "JQ_WeeklyChart" /f
pause
