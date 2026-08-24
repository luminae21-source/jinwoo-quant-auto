@echo off
chcp 949 >nul
cd /d "%~dp0"
echo ============================================
echo  GitHub push - jinwoo-quant-auto
echo ============================================
del .git\*.lock 2>nul
git push origin main
if errorlevel 1 (
  echo.
  echo [!] push 실패 - 원격에 새 커밋이 있으면 먼저 병합이 필요합니다.
  echo     Claude에게 "push가 거부됐어"라고 알려주세요.
) else (
  echo.
  echo [OK] push 완료
)
pause
