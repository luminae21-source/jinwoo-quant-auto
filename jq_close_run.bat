@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
where python >nul 2>nul && (set PY=python) || (set PY=py)
%PY% -c "import certifi,shutil;shutil.copyfile(certifi.where(),r'C:\Users\Public\jq_cacert.pem')" 2>nul
set SSL_CERT_FILE=C:\Users\Public\jq_cacert.pem
set CURL_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
set REQUESTS_CA_BUNDLE=C:\Users\Public\jq_cacert.pem
echo === jq_close run %DATE% %TIME% === > jq_close_log.txt
%PY% -m pip install -q pillow >> jq_close_log.txt 2>&1

rem --- 입력 json 신선도 검사: 오래된 날짜면 낡은 카드가 나오므로 경고 ---
%PY% -X utf8 -c "import json,datetime,sys,os;h=os.path.dirname(os.path.abspath(sys.argv[0])) if False else '.';t=datetime.date.today().isoformat();bad=[];[bad.append((f,json.load(open(f,encoding='utf-8')).get('date') or json.load(open(f,encoding='utf-8')).get('updated'))) for f in ['jq_close_data.json','jq_close_stocks.json','jq_watchlist.json'] if os.path.exists(f)];stale=[(f,d) for f,d in bad if d!=t];print('[신선도] 오늘=%s'%t);[print('  [낡음] %s -> %s (세션이 갱신해야 함)'%(f,d)) for f,d in stale];print('  [OK] 입력 json 3종 모두 오늘자' if not stale else '  ** 낡은 입력으로 카드를 만들면 기준일이 과거로 찍힙니다 **')" >> jq_close_log.txt 2>&1

echo --- close card --- >> jq_close_log.txt
%PY% -X utf8 jq_close_card.py >> jq_close_log.txt 2>&1
echo --- close stocks --- >> jq_close_log.txt
%PY% -X utf8 jq_close_stocks.py >> jq_close_log.txt 2>&1
echo --- watch card --- >> jq_close_log.txt
%PY% -X utf8 jq_watch_card.py >> jq_close_log.txt 2>&1
echo --- kakao send --- >> jq_close_log.txt
call jq_kakao_send.bat >> jq_close_log.txt 2>&1
echo EXITCODE=%errorlevel% >> jq_close_log.txt
type jq_close_log.txt
echo.
echo ===== DONE (3 cards). Log: jq_close_log.txt =====
if errorlevel 1 (echo. & echo [오류] 위 메시지 확인 & pause) else (exit)
