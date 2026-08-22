@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  Supply/Demand EXPANSION collector (pykrx, KRX) - RESUMABLE
echo  foreign/inst net-buy + short-balance, full universe, 2002~.
echo  PC ONLY (cloud KRX blocked). may take HOURS.
echo  safe to Ctrl-C: re-run resumes where it stopped.
echo ================================================================
echo.

py -c "import pykrx" 2>nul
if errorlevel 1 (
  echo [install] pykrx pandas
  py -m pip install pykrx pandas
)

echo.
echo ---- KOSPI (2002~, full universe) ----
py fetch_수급확장_pykrx.py --market KOSPI --start 2002-01-02 --sleep 0.1

echo.
echo ---- KOSDAQ (2002~, full universe) ----
py fetch_수급확장_pykrx.py --market KOSDAQ --start 2002-01-02 --sleep 0.1

echo.
echo done. next: run 수급오버레이_정교화_실행.bat
pause