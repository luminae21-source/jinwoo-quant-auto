@echo off
chcp 949 >nul
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  Jinwoo Quant  (screener+guide+theme+dashboard+chart)
echo ================================================================
echo.

echo [1/7] self-test...
py 진우사냥터_스크리너.py --self-test
if errorlevel 1 ( echo [FAIL] self-test. & pause & exit /b 1 )

echo.
echo [2/7] screener (value hunting-ground CSV) ... first run loads full daily
py 진우사냥터_스크리너.py --top 30
if errorlevel 1 ( echo [FAIL] screener. & pause & exit /b 1 )

echo.
echo [3/7] trading-style guide ...
py 진우_매매방식_가이드.py --top 30

echo.
echo [4/7] theme radar (7 themes) ...
py 진우_테마발굴.py

echo.
echo [5/7] hunting-ground dashboard + cards ...
py 진우사냥터_현황판.py
py 진우사냥터_카드.py

echo.
echo [6/7] integrated graphic dashboard ...
py 진우_통합대시보드.py

echo.
echo [7/7] interactive chart view ...
py 진우_차트뷰.py --days 180

echo.
echo [+] entry-point discovery (buy/sell tactics) ...
py 진우_타점발굴.py --top 40
py 진우_진입신호.py
py 진우_타점발굴_표.py
py 진우_타점발굴_표.py --chart

echo.
echo ================================================================
echo  done. open in browser:
echo    진우_통합대시보드.html   (monitor: watchlist + theme radar)
echo    진우_차트뷰.html         (interactive chart: candle/MA/volume + draw)
echo  data: 진우사냥터_후보.csv / 진우_매매방식_가이드.csv / cards PNG
echo ================================================================
pause
