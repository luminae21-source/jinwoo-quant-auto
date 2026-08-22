@echo off
chcp 949 >nul
cd /d "%~dp0"
echo ===== JQ today code re-verify (selftest) =====
echo.
echo --- 시장브리핑_생성.py ---
py "시장브리핑_생성.py" --selftest
echo.
echo --- decision_view.py ---
py "decision_view.py" --selftest
echo.
echo --- 보유점검.py ---
py "보유점검.py" --selftest
echo.
echo --- holdings_concentration.py ---
py "holdings_concentration.py" --selftest
echo.
echo --- 만기후_체크.py ---
py "만기후_체크.py" --selftest
echo.
echo --- 만기효과_백테스트.py ---
py "만기효과_백테스트.py" --selftest
echo.
echo --- 시장영향_검증.py ---
py "시장영향_검증.py" --selftest
echo.
echo --- 익일예측_모델.py ---
py "익일예측_모델.py" --selftest
echo.
echo --- krx_openapi.py ---
py "krx_openapi.py" --selftest
echo.
echo ===== DONE =====
pause
