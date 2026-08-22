@echo off
chcp 949 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
echo [뷰생성] 최신 분류표/거래대금 기준으로 앱/모바일 HTML 재생성...
%PY% "뷰생성.py" %*
if errorlevel 1 ( echo [FAIL] 뷰생성 실패. 먼저 분류/거래대금 배치가 실행됐는지 확인. & pause & exit /b 1 )
echo.
echo 완료. 가상매매\검증\ 의 급등_이중바닥_거래대금_앱_*.html / 모바일 확인.
pause
