@echo off
cd /d "%~dp0"
> jq_tasks_log.txt (
  echo === JQ_DailyPredict ===
  schtasks /query /tn "JQ_DailyPredict" /fo LIST /v
  echo.
  echo === JQ_DailyPredictKQ ===
  schtasks /query /tn "JQ_DailyPredictKQ" /fo LIST /v
  echo.
  echo === JQ_PostExpiryCheck ===
  schtasks /query /tn "JQ_PostExpiryCheck" /fo LIST /v
  echo.
  echo === JQ_WeeklyChart ===
  schtasks /query /tn "JQ_WeeklyChart" /fo LIST /v
  echo.
  echo === JinwooQuant_MarketBrief ===
  schtasks /query /tn "JinwooQuant_MarketBrief" /fo LIST /v
  echo.
  echo === JQ_Cards ===
  schtasks /query /tn "JQ_Cards" /fo LIST /v
  echo.
  echo === JQ_SurgeScan ===
  schtasks /query /tn "JQ_SurgeScan" /fo LIST /v
  echo.
)
echo.
echo ===== 예약작업 점검 =====
echo 전체 결과: jq_tasks_log.txt
echo.
echo [핵심] 아래 두 줄만 보면 됩니다:
echo   "마지막 실행 결과" 가 0(0x0) 이 아니면 그 작업은 실패한 것입니다.
echo   "상태" 가 "실행 중" 인데 몇 시간째 그대로면 pause 로 멈춰 있는 것입니다.
echo.
findstr /i /c:"===" /c:"마지막 실행 결과" /c:"Last Result" /c:"상태" /c:"Status" /c:"다음 실행" /c:"Next Run" jq_tasks_log.txt
echo.
echo ----- 실패(0 아님) 후보 -----
findstr /i /c:"마지막 실행 결과" /c:"Last Result" jq_tasks_log.txt | findstr /v /c:"0 (0x0)" | findstr /v /c:"267011"
echo (위가 비어 있으면 실패 없음. 267011 = 아직 한 번도 실행 안 됨)
echo.
pause
