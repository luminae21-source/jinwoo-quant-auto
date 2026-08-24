@echo off
chcp 949 >nul
REM 진우퀀트 - 월초 유니버스 자동생성을 Windows 작업 스케줄러에 등록
REM 매월 1일 08:30에 유니버스_월초생성.bat 실행 (한 번만 실행하면 등록됨)
set "TASKBAT=%~dp0유니버스_월초생성.bat"
schtasks /Create /TN "JinwooQuant_Universe_Monthly" /TR "\"%TASKBAT%\"" /SC MONTHLY /D 1 /ST 08:30 /F
if errorlevel 1 (
  echo.
  echo [오류] 등록 실패. 그래도 유니버스_월초생성.bat 를 직접 실행하면 리스트는 생성됩니다.
  echo   또는 작업 스케줄러 GUI에서 위 배치를 매월 1일로 등록하세요.
  pause
  exit /b 1
)
echo.
echo [등록 완료] "JinwooQuant_Universe_Monthly" - 매월 1일 08:30 자동 실행.
echo   확인:  schtasks /Query /TN "JinwooQuant_Universe_Monthly"
echo   해제:  schtasks /Delete /TN "JinwooQuant_Universe_Monthly" /F
pause
