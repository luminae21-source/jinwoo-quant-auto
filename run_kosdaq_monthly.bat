@echo off
chcp 949 >nul
cd /d "%~dp0"
echo ============================================
echo   KOSDAQ 월간 발굴 루틴 (2소스) - 매수신호 아님
echo ============================================
echo.
echo [1/2] 가격.수급.펀더 스캔 (kosdaq_monthly_scan)
python kosdaq_monthly_scan.py
echo.
echo [2/2] 공시 카탈리스트 스캔 (DART, 최근 30일)
python dart_disclosure_scanner.py --codes watch_codes.txt --days 30 --only_catalyst
echo.
echo ============================================
echo 완료 → kosdaq_monthly_scan_YYYYMM.csv + catalyst_feed.csv
echo 다음: (1) 2+ 점등 교집합 확인  (2) 전입후보 초안 검토
echo       (3) active 워치리스트 전입(진우, 무효화 먼저)  (4) 월말 Track W 기입
echo ============================================
pause
