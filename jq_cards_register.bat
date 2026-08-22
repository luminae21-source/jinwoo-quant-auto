@echo off
chcp 949 >nul
cd /d "%~dp0"
echo [JQ] Registering daily cardnews (weekdays 08:15)...
schtasks /create /tn "JQ_Cards" /tr "\"%~dp0jq_cards_run.bat\"" /sc WEEKLY /d MON,TUE,WED,THU,FRI /st 08:15 /f
echo done. delete: schtasks /delete /tn JQ_Cards /f
pause
