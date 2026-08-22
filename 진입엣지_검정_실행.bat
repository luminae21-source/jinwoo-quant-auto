@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  C: entry-edge factor test (30yr, delisting+cost built-in)
echo  5 factors x quintile x IN/OOS. full run ~5-15 min.
echo ================================================================
echo.

py 검정_진입엣지_30년.py --self-test
if errorlevel 1 (
  echo.
  echo [FAIL] self-test failed. aborting.
  pause
  exit /b 1
)

echo.
echo ---- main run ----
echo.
py 검정_진입엣지_30년.py %*
if errorlevel 1 (
  echo.
  echo [FAIL] runtime error.
  pause
  exit /b 1
)

echo.
echo result: 가상매매\검증\진입엣지_검정_결과_base.md
echo tip: preview first -  진입엣지_검정_실행.bat --sample 800
echo      sensitivity    -  진입엣지_검정_실행.bat --cost 0.70 --delisting conservative
pause
