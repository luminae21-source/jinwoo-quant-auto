@echo off
chcp 949 >nul
cd /d "%~dp0"
title Jinwoo Quant Launcher
:menu
cls
echo ================================================================
echo   진우퀀트 통합 실행 메뉴  (기존 bat들을 한곳에서 호출)
echo ================================================================
echo.
echo   [일간]
echo    1. 일일 올인원        (분류-이중바닥-거래대금-뷰생성)
echo    2. 자동갱신 파이프라인 (증분수집-발굴 전체)
echo    3. 일봉 데이터 갱신+검증 (KOSPI daily + reconcile)
echo    4. 시장 브리핑
echo.
echo   [대시보드/허브]
echo    5. 추천 대시보드 갱신  (강화키트)
echo    6. 허브 갱신          (강화키트)
echo.
echo   [주간/월간]
echo    7. 주간 실행          (jq_weekly_run)
echo    8. 유니버스 월초생성   (강화키트)
echo    9. 월간 갱신          (monthly_refresh)
echo   10. 전체갱신 풀 리빌드  (강화키트, 10-15분)
echo.
echo   [기타]
echo   11. 로그 보기
echo    0. 종료
echo.
set /p sel=번호 입력 후 Enter:
if "%sel%"=="1"  call "일일_올인원_실행.bat" & goto back
if "%sel%"=="2"  call "진우_자동갱신_파이프라인.bat" & goto back
if "%sel%"=="3"  call "jq_daily_update.bat" & goto back
if "%sel%"=="4"  call "시장브리핑_실행.bat" & goto back
if "%sel%"=="5"  call "강화키트\추천_실행.bat" & goto back
if "%sel%"=="6"  call "강화키트\허브_실행.bat" & goto back
if "%sel%"=="7"  call "jq_weekly_run.bat" & goto back
if "%sel%"=="8"  call "강화키트\유니버스_월초생성.bat" & goto back
if "%sel%"=="9"  call "진우퀀트_월간갱신.bat" & goto back
if "%sel%"=="10" call "강화키트\전체갱신_실행.bat" & goto back
if "%sel%"=="11" call "로그보기.bat" & goto back
if "%sel%"=="0"  exit /b 0
goto menu
:back
echo.
pause
goto menu
