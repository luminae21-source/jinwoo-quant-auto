@echo off
chcp 949 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -m pip install -q pandas numpy 2>nul

rem --- self-test 먼저 (실패 시 pause 없이 종료) ---
%PY% 진입엣지_스크리너.py --self-test 1> 진입엣지_스크리너_자동.log 2>&1
if errorlevel 1 (
  echo [FAIL] self-test aborted %date% %time% >> 진입엣지_스크리너_자동.log
  exit /b 1
)

rem --- 본 실행: 후보 CSV 생성 (하순이면 스크립트가 보류 문구 표시) ---
echo ===== run %date% %time% ===== >> 진입엣지_스크리너_자동.log
%PY% 진입엣지_스크리너.py --top 20 1>> 진입엣지_스크리너_자동.log 2>&1
exit /b 0
