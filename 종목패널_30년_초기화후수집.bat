@echo off
cd /d "%~dp0"
echo ============================================================
echo  30년 패널 수집 - 초기화 후 처음부터
echo ============================================================
echo.
echo  삭제할 파일 (셀프테스트 오염분 + 부분 수집분):
echo    _fetch_30y_ckpt.json
echo    종목일봉_30년_KOSPI.csv
echo    종목일봉_30년_KOSDAQ.csv
echo    종목시총_30년.csv
echo.
set /p YN=정말 지우고 처음부터 받으시겠습니까? (Y/N):
if /i not "%YN%"=="Y" (echo 취소했습니다. & pause & exit /b)

del /q "_fetch_30y_ckpt.json"      2>nul
del /q "종목일봉_30년_KOSPI.csv"   2>nul
del /q "종목일봉_30년_KOSDAQ.csv"  2>nul
del /q "종목시총_30년.csv"         2>nul
echo   [삭제 완료]
echo.
call "%~dp0종목패널_30년_수집.bat"
