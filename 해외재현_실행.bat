@echo off
chcp 949 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ================================================================
echo   #1 Japan/HK Deep-Value Reproduction  (PC only)
echo   auto-picks Python 3.13/3.12/3.11 (NOT 3.14)
echo ================================================================

REM --- find a compatible Python (avoid 3.14) ---
set PY=
for %%V in (3.13 3.12 3.11) do (
  if not defined PY (
    py -%%V --version >nul 2>nul && set "PY=py -%%V"
  )
)
if not defined PY (
  echo [ERROR] No Python 3.11-3.13 found. Install Python 3.13 from python.org first.
  pause & exit /b 1
)
echo [OK] using: %PY%
%PY% --version

echo.
echo [1/4] installing libraries (first run only)...
%PY% -m pip install -q finance-datareader yfinance pandas numpy

echo.
echo [2/4] smoke test (1 ticker, checks internet/yahoo)...
%PY% "백테_해외_딥밸류_재현_PC실행.py" --market TSE --smoke
if errorlevel 1 (
  echo [STOP] smoke failed - yahoo unreachable. check internet/firewall, then re-run.
  pause & exit /b 1
)

set "OUT=해외재현_결과.txt"
echo Japan/HK deep-value reproduction result > "%OUT%"
echo.
echo [3/4] running JAPAN (TSE)... this takes a few minutes
%PY% "백테_해외_딥밸류_재현_PC실행.py" --market TSE --n 800 >> "%OUT%" 2>&1

echo [4/4] running HONG KONG (HKEX)...
%PY% "백테_해외_딥밸류_재현_PC실행.py" --market HKEX --n 800 >> "%OUT%" 2>&1

echo.
echo ================== RESULT (해외재현_결과.txt) ==================
type "%OUT%"
echo ==============================================================
echo Saved to 해외재현_결과.txt  -- paste this file's content back to me.
pause
