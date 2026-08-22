@echo off
chcp 949 >nul
cd /d "%~dp0"
echo 진우퀀트 자동갱신을 평일 07:30 자동 실행으로 등록합니다.
schtasks /Create /TN "진우퀀트_자동갱신" /TR "\"%~dp0진우_자동갱신_파이프라인.bat\"" /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 07:30 /F
if errorlevel 1 (
  echo [실패] 관리자 권한으로 다시 실행하거나, 작업 스케줄러에서 수동 등록하세요.
) else (
  echo [완료] 평일 07:30 자동 실행 등록됨.
  echo 해제:  schtasks /Delete /TN "진우퀀트_자동갱신" /F
  echo 지금 테스트:  schtasks /Run /TN "진우퀀트_자동갱신"
)
pause
