@echo off
setlocal
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

echo ================================================================
echo  Deep-value + INST refinement (short-cover split) + re-verify S3
echo  run AFTER 수급확장_수집_실행.bat has finished collecting.
echo ================================================================
echo.

py 검증_수급오버레이_정교화.py --self-test
if errorlevel 1 (
  echo [FAIL] selftest
  pause
  exit /b 1
)

echo.
echo ---- main run (first run reduces daily bars, then caches) ----
py 검증_수급오버레이_정교화.py %*

echo.
echo done. promote to hard filter only if S3 passes (not automatic).
pause