@echo off
rem 월간리밸.bat - 매달 1회. 사슬 4단계를 순서대로 돌린다.
rem 앞 단계가 실패하면 멈춘다 (뒤 단계는 옛 달을 다시 만들 뿐이므로).
rem
rem 2026-08-20 수정: 버전 번호가 아니라 **패키지가 있는 파이썬**을 고른다.
rem   pykrx 는 3.14 에 깔려 있는데 3.13 을 골라서 1단계가 죽었었다.
cd /d %~dp0

rem --- pykrx + pandas 둘 다 있는 파이썬 (1단계용) ---
set PYK=
for %%V in (3.13 3.12 3.11 3.14) do (
  if not defined PYK ( py -%%V -c "import pykrx,pandas" >nul 2>nul && set "PYK=py -%%V" )
)
if not defined PYK ( py -c "import pykrx,pandas" >nul 2>nul && set "PYK=py" )

rem --- pandas 있는 파이썬 (2~4단계용) ---
set PY=
for %%V in (3.13 3.12 3.11 3.14) do (
  if not defined PY ( py -%%V -c "import pandas" >nul 2>nul && set "PY=py -%%V" )
)
if not defined PY ( py -c "import pandas" >nul 2>nul && set "PY=py" )
if not defined PY (
  echo [ERROR] pandas 가 있는 Python 을 못 찾았습니다.
  echo         pip install pandas
  pause
  exit /b 1
)

echo ==========================================
echo   JINWOO QUANT - MONTHLY REBALANCE
echo   step1 : %PYK%
echo   step2~: %PY%
echo ==========================================
echo.
echo [0/4] chain status BEFORE
%PY% 강화키트\운용사슬.py
echo.

if not defined PYK (
  echo [1/4] SKIP - pykrx 가 어느 Python 에도 없습니다.
  echo       설치: py -3.13 -m pip install pykrx
  echo       재무를 못 받으면 그 아래 단계는 옛 달을 다시 만들 뿐이라 여기서 멈춥니다.
  goto FAIL
)
echo [1/4] fundamentals (network, may take minutes)
%PYK% fetch_fundamental_panel.py
if errorlevel 1 goto FAIL
echo.

echo [2/4] style panel
%PY% build_style_panel.py
if errorlevel 1 goto FAIL
echo.

echo [3/4] forward signal + ledger
%PY% 실전준비\forward_signal.py
if errorlevel 1 goto FAIL
echo.

echo [4/4] rebuild hub
%PY% 강화키트\연구뷰_생성.py
%PY% 강화키트\jq_hub.py
echo.

echo ==========================================
echo   chain status AFTER
echo ==========================================
%PY% 강화키트\운용사슬.py
echo.
echo   DONE. open: 강화키트\진우퀀트_허브.html
goto END

:FAIL
echo.
echo   [STOPPED] a step failed. later steps would only
echo   regenerate the OLD month, so we stop here.
echo   fix the failing step above, then run again.

:END
echo.
pause
