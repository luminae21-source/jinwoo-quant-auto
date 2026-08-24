@echo off
chcp 949 >nul
REM 진우퀀트 - 월초 규칙 유니버스 생성
cd /d "%~dp0"
echo [실행] 유니버스 규칙 리스트 생성...
py 유니버스_규칙화_실행.py --now
if errorlevel 1 (
  echo.
  echo [오류] 파이썬 실행 실패. py 및 pandas 설치를 확인하세요.
  echo   설치: py -m pip install pandas numpy
  pause
  exit /b 1
)
echo.
echo [완료] 유니버스_규칙화_현재.csv 갱신됨 (강화키트 폴더)
echo   * MA200 이격이 큰 과열 국면이면 분할 매수, 비중 축소.
echo   * 투자자문 아님, 책임 본인.
pause
