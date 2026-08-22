@echo off
chcp 949 >nul
cd /d "%~dp0"
echo [JQ] Registering MONTHLY entry-edge screener (day 1, 09:00)...
schtasks /create /tn "JQ_EntryScreener" /tr "\"%~dp0진입엣지_스크리너_자동.bat\"" /sc MONTHLY /d 1 /st 09:00 /f
echo.
echo 등록되면 매달 1일 09시 자동: 진입엣지_후보.csv 갱신 (하순 지난 시점).
echo   결과: 진입엣지_후보.csv  ·  로그: 진입엣지_스크리너_자동.log
echo   ※ 하순 끝 직후(월말)에 받고 싶으면 위 /d 1 을 /d 26 으로 바꿔 재등록.
echo 삭제: schtasks /delete /tn "JQ_EntryScreener" /f
pause
