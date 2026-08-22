@echo off
chcp 949 >nul
schtasks /create /tn "JinwooQuant_MarketBrief" /tr "\"%~dp0시장브리핑_자동.bat\"" /sc weekly /d MON,TUE,WED,THU,FRI /st 08:00 /f
echo.
echo 등록 완료: 평일(월~금) 오전 8시 자동 실행. 해제는 schtasks /delete /tn JinwooQuant_MarketBrief
pause
