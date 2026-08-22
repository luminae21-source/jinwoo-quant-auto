@echo off
chcp 949 >nul
cd /d "%~dp0"
echo 진우 전진기록 일일 스냅샷을 평일 08:00 자동 실행으로 등록합니다.
echo (자동갱신 07:30 이후 - 그날 주문 제안을 진우_제안기록.csv 에 적재)
echo.
schtasks /Create /TN "진우퀀트_전진기록스냅샷" /TR "\"%~dp0진우_전진기록_자동.bat\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 08:00 /F
if errorlevel 1 (
  echo.
  echo [FAIL] 등록 실패. 위 오류를 확인하세요.
  pause
  exit /b 1
)
echo.
echo [OK] 평일 08:00 자동 스냅샷 등록됨. 로그: 진우_전진기록_로그.txt
echo 해제  : schtasks /Delete /TN "진우퀀트_전진기록스냅샷" /F
echo 테스트: schtasks /Run    /TN "진우퀀트_전진기록스냅샷"
pause
