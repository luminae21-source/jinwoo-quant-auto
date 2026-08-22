@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo ================================================================
echo   JINWOO QUANT CONSOLE  (local app)
echo   picks Python 3.13/3.12/3.11 (not 3.14), installs, launches
echo ================================================================

set PY=
for %%V in (3.13 3.12 3.11) do (
  if not defined PY ( py -%%V --version >nul 2>nul && set "PY=py -%%V" )
)
if not defined PY (
  echo [ERROR] No Python 3.11-3.13 found. Install Python 3.13 from python.org first.
  pause & exit /b 1
)
echo [OK] using: %PY%

echo [1/2] installing app libraries (first run only, ~1-2 min)...
%PY% -m pip install -q streamlit pandas numpy

REM skip streamlit's one-time email prompt
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  echo [general]> "%USERPROFILE%\.streamlit\credentials.toml"
  echo email = "">> "%USERPROFILE%\.streamlit\credentials.toml"
)

echo [2/2] launching console... browser opens at http://localhost:8501
echo (close this window to stop the app)
%PY% -m streamlit run jq_console.py --theme.base light --theme.textColor "#2b2b2b" --theme.backgroundColor "#f7f6f3" --theme.secondaryBackgroundColor "#ffffff" --theme.primaryColor "#5b7fa6"

pause
