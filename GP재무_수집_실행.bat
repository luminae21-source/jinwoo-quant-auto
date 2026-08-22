@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  GP financials collector (DART, FY2015-2025) - RESUMABLE
echo  full universe ~3193 stocks x 11yr. may take 1-3 HOURS.
echo  safe to Ctrl-C: re-run resumes where it stopped.
echo ================================================================
echo.

py 수집_GP재무_DART.py --selftest
if errorlevel 1 (
  echo [FAIL] selftest
  pause
  exit /b 1
)

echo.
echo ---- collecting (resumable, appends to fundamentals_gp_2015_2025.csv) ----
echo tip: FIRST test the key with preview: GP재무_수집_실행.bat --codes _gp_codes_preview.csv
echo.
py 수집_GP재무_DART.py --codes _gp_codes.csv --start-year 2015 --end-year 2025 %*

echo.
echo result: fundamentals_gp_2015_2025.csv
echo next:   GP검정_실행.bat
pause
