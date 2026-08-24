#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""broker_adj_smoke.py — 증권사 API로 **2014년 이전 수정주가**에 닿는지만 확인하는 스모크

왜 이게 필요한가
  KRX 백엔드(pykrx · FinanceDataReader 0.9.x)의 조정 데이터는 **2014-04-30부터**다(실측).
  그래서 지금 크기 백테 창이 2015~2026으로 잘려 있고, 2008·2011 하락장이 창에 없다.
  → MDD가 구조적으로 낙관. 이걸 고치려면 2014년 이전 조정 시계열이 필요하다.
  유료 벤더(DataGuide/FnGuide)로 가기 **전에**, 이미 계좌가 있는 증권사 API가
  다른 백엔드로 더 과거까지 주는지 공짜로 확인한다. 그게 이 스크립트의 전부다.

이 스크립트가 하는 일 / 안 하는 일
  한다   : 조회(시세)만. 연도 사다리로 "몇 년까지 응답이 오나"를 찍는다.
           수정주가 플래그가 실제로 작동하는지 액면분할 종목으로 교차검증한다.
  안 한다: 주문·잔고·자금이동 일절 없음. 대량 수집도 없음(그건 통과 후 별도 스크립트).
           키를 화면에 찍지 않고, 증권사 자기 엔드포인트 외 **어디에도** 보내지 않는다.

실행 (진우 PC · PowerShell)
  cd C:\Users\긍정적인_삶의자세\Desktop\진우퀀트
  py 데이터수리\broker_adj_smoke.py --selftest        # 네트워크 0 · 조립/판정 로직만 검증
  py 데이터수리\broker_adj_smoke.py                   # 사용 가능한 채널 전부 스모크
  py 데이터수리\broker_adj_smoke.py --only kis         # KIS만
  py 데이터수리\broker_adj_smoke.py --only kiwoom      # 키움만(32bit + OpenAPI+ 로그인 필요)

키 파일 (PC 로컬에만 · 절대 업로드 금지) — **이미 있는 걸 그대로 읽는다. 새로 만들지 말 것.**
  ① .kis_key            2줄 평문(1행 APP KEY · 2행 APP SECRET · #주석 무시)  ← 진우 PC 현재 방식
  ② .kis_key.json       {"app_key":"...","app_secret":"..."}    (실행키트/broker/kis.py 포맷)
  ③ 진우_KIS키.json      {"appkey":"...","appsecret":"..."}      (jq_broker_kis.py 포맷)
  ④ 환경변수            KIS_APPKEY / KIS_APPSECRET
  탐색 경로: 데이터수리 · 진우퀀트 루트 · 실행키트 · 실행키트/broker · 현재폴더
  토큰은 .kis_token.json 에 캐시한다(KIS는 토큰 발급이 분당 1회로 제한됨).

결과 해석
  · 2010년 이전 행이 나오고 수정주가 플래그가 먹으면 → **문 열림**. 유료 벤더 없이 30년 조정본 가능.
  · 2014년 근처에서 막히면 → KRX와 같은 벤더 뒤에 있는 것. 유료 벤더 검토로 넘어간다.
  · 행은 나오는데 액면분할 교차검증이 실패하면 → 원주가만 주는 것. 조정은 우리가 해야 함(비추천).

⚠️ 정보·검증용 · 투자자문 아님. 실집행/실계좌 작업은 이 스크립트 범위 밖.
"""
import os, sys, json, time, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 연도 사다리 — "언제까지 닿나"만 보면 되므로 촘촘할 필요 없다
YEAR_LADDER = [1996, 2000, 2005, 2008, 2010, 2012, 2014]
# 교차검증용 액면분할 사건: 삼성전자 2018-05-04 50:1 (수정주가면 분할 전 가격이 1/50로 눌려 있어야 함)
SPLIT_CASE = {"code": "005930", "ym": "2018-04", "ratio": 50, "y0": 2018, "y1": 2018}
# 대형주 1 + 소형주 2 (소형주는 과거 도달이 더 자주 막힌다)
TEST_CODES = ["005930", "000480", "004410"]


# ────────────────────────────── 공용 유틸 ──────────────────────────────
# 셀프테스트가 탐색 경로를 임시폴더로 가둘 때만 채운다(None이면 실제 경로 사용).
# 이렇게 분리한 이유: 초판 셀프테스트는 HERE만 임시폴더로 바꿨는데 ROOT에 있던
# **실제** .kis_key 를 주워 읽어서, 진우 PC에서만 ②③이 FAIL 했다(샌드박스는 통과).
# 환경에 따라 결과가 달라지는 검사는 검사가 아니다.
SEARCH_DIRS = None


def find_file(name):
    """키/토큰 파일 탐색. 코드에 키를 두지 않기 위한 유일 경로."""
    dirs = SEARCH_DIRS if SEARCH_DIRS is not None else (
        HERE, ROOT, os.path.join(ROOT, "실행키트"),
        os.path.join(ROOT, "실행키트", "broker"), os.getcwd())
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def mask(s):
    """키가 로그에 남지 않게. 존재 여부만 알려준다."""
    s = str(s or "")
    return f"<{len(s)}자·{s[:2]}…{s[-2:]}>" if len(s) >= 6 else "<짧음>"


def verdict(oldest, adj_ok):
    """스모크 판정을 한 줄로. 여기가 이 스크립트의 결론."""
    if oldest is None:
        return "닫힘 — 응답 없음(권한/환경 문제일 수도 있으니 에러 메시지 확인)"
    if oldest > 2013:
        return f"KRX와 동급 — {oldest}년까지만. 2014년 이전은 이 채널로 못 감 → 유료 벤더 검토"
    if not adj_ok:
        return f"{oldest}년까지 닿지만 **원주가 의심**(분할 교차검증 실패) → 조정은 우리 몫, 비추천"
    return f"★문 열림 — {oldest}년까지 수정주가 확인. 유료 벤더 없이 장기 조정본 가능"


# ────────────────────────────── KIS (REST · 조회 전용) ──────────────────────────────
KIS_PAPER = "https://openapivts.koreainvestment.com:29443"
KIS_LIVE = "https://openapi.koreainvestment.com:9443"
KIS_CHART = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
KIS_TRID = "FHKST03010100"          # 국내주식 기간별시세(일/주/월/년)


def kis_token(host, keys, timeout=10):
    """토큰 캐시 재사용 — KIS는 토큰 발급이 분당 1회 제한이라 캐시가 필수."""
    import requests
    cache = find_file(".kis_token.json") or os.path.join(HERE, ".kis_token.json")
    if os.path.exists(cache):
        try:
            j = json.load(open(cache, encoding="utf-8"))
            if j.get("host") == host and j.get("exp", 0) > time.time() + 300:
                return j["access_token"], "캐시"
        except Exception:
            pass
    r = requests.post(f"{host}/oauth2/tokenP", timeout=timeout,
                      json={"grant_type": "client_credentials",
                            "appkey": keys["app_key"], "appsecret": keys["app_secret"]})
    r.raise_for_status()
    j = r.json()
    tok = j["access_token"]
    try:
        json.dump({"host": host, "access_token": tok,
                   "exp": time.time() + int(j.get("expires_in", 86400)) - 600},
                  open(cache, "w", encoding="utf-8"))
        if os.name != "nt":
            os.chmod(cache, 0o600)
    except Exception:
        pass
    return tok, "신규발급"


def kis_chart(host, tok, keys, code, y0, y1, period="M", adj="0", timeout=10):
    """기간별시세 1콜. adj='0' 수정주가 / '1' 원주가 (문서 기준 — 실제로 먹는지는 아래서 검증한다)."""
    import requests
    r = requests.get(host + KIS_CHART, timeout=timeout,
                     headers={"content-type": "application/json; charset=utf-8",
                              "authorization": f"Bearer {tok}",
                              "appkey": keys["app_key"], "appsecret": keys["app_secret"],
                              "tr_id": KIS_TRID, "custtype": "P"},
                     params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": code,
                             "FID_INPUT_DATE_1": f"{y0}0101", "FID_INPUT_DATE_2": f"{y1}1231",
                             "FID_PERIOD_DIV_CODE": period, "FID_ORG_ADJ_PRC": adj})
    if r.status_code != 200:
        return None, f"HTTP {r.status_code} {r.text[:120]}"
    j = r.json()
    if j.get("rt_cd") not in (None, "0"):
        return None, f"rt_cd={j.get('rt_cd')} {j.get('msg1', '')[:80]}"
    rows = [x for x in (j.get("output2") or []) if x.get("stck_bsop_date")]
    return rows, None


def load_kis_keys():
    """진우 PC에 실제로 존재하는 **3가지 키 포맷을 모두** 받는다.

    2026-07-27 정정: 초판은 `.kis_key.json`만 찾아서, 이미 `.kis_key`(2줄 평문)를
    쓰고 있던 PC에서 "키 없음"으로 스킵됐다. 키를 새 파일로 복사하게 만드는 것은
    **비밀을 늘리는 나쁜 해법**이므로, 스크립트가 기존 파일을 읽도록 고친다.
      ① .kis_key           2줄 평문(#주석 무시) — app key / app secret 순
      ② .kis_key.json      {"app_key","app_secret"}      (실행키트/broker/kis.py)
      ③ 진우_KIS키.json     {"appkey","appsecret",...}     (jq_broker_kis.py)
      ④ 환경변수 KIS_APPKEY / KIS_APPSECRET
    반환: (keys|None, 출처설명). 값은 절대 출력하지 않는다.
    """
    # ① 평문 2줄
    p = find_file(".kis_key")
    if p:
        try:
            lines = [ln.strip() for ln in open(p, encoding="utf-8-sig").read().splitlines()]
            vals = [ln for ln in lines if ln and not ln.startswith("#")]
            if len(vals) >= 2 and not vals[0].startswith("여기에"):
                return {"app_key": vals[0], "app_secret": vals[1]}, os.path.basename(p) + " (2줄 평문)"
            if vals and vals[0].startswith("여기에"):
                print("  .kis_key 가 예시값 그대로임(여기에_APP_KEY…) — 실제 키로 교체 필요")
        except Exception as e:
            print(f"  .kis_key 읽기 실패: {type(e).__name__}")
    # ②③ JSON 두 종류
    for name, ka, ks in ((".kis_key.json", "app_key", "app_secret"),
                         ("진우_KIS키.json", "appkey", "appsecret")):
        p = find_file(name)
        if not p:
            continue
        try:
            j = json.load(open(p, encoding="utf-8-sig"))
            if j.get(ka) and j.get(ks) and not str(j[ka]).startswith("여기에"):
                return {"app_key": j[ka], "app_secret": j[ks]}, os.path.basename(p)
        except Exception as e:
            print(f"  {name} 파싱 실패: {type(e).__name__}")
    # ④ 환경변수
    ek, es = os.environ.get("KIS_APPKEY"), os.environ.get("KIS_APPSECRET")
    if ek and es:
        return {"app_key": ek, "app_secret": es}, "환경변수 KIS_APPKEY/KIS_APPSECRET"
    return None, None


def smoke_kis(args):
    print("\n" + "=" * 72 + "\n[KIS] 한국투자증권 REST · 국내주식 기간별시세(조회 전용)")
    keys, src = load_kis_keys()
    if not keys:
        print("  KIS 키 못 찾음 — 아래 중 하나만 있으면 됨(새로 만들 필요 없음):")
        print("    .kis_key(2줄 평문) · .kis_key.json{app_key,app_secret} · 진우_KIS키.json{appkey,appsecret}")
        print("    또는 환경변수 KIS_APPKEY / KIS_APPSECRET.  탐색 경로: 데이터수리 · 진우퀀트 루트 · 실행키트 · 실행키트/broker · 현재폴더")
        return None
    print(f"  키 로드: {src} · app_key {mask(keys['app_key'])} (값은 찍지 않음)")

    hosts = [("모의", KIS_PAPER), ("실전", KIS_LIVE)] if args.host == "auto" \
        else ([("모의", KIS_PAPER)] if args.host == "paper" else [("실전", KIS_LIVE)])

    for label, host in hosts:
        try:
            tok, how = kis_token(host, keys)
        except Exception as e:
            print(f"  [{label}] 토큰 실패: {e}"); continue
        print(f"  [{label}] 토큰 OK({how}) · 도메인 {host.split('//')[1].split(':')[0]}")

        # ① 최근 창이 먹는지 먼저 (여기서 막히면 권한 문제 — 연도 사다리는 의미 없음)
        rows, err = kis_chart(host, tok, keys, "005930", 2024, 2024)
        if err or not rows:
            print(f"     최근(2024) 조회 실패 → {err or '빈 응답'}")
            if label == "모의":
                print("     (모의 도메인은 기간별시세를 막는 경우가 있음 → 실전 도메인으로 재시도)")
            continue

        # ② 연도 사다리 — 종목별 최고(oldest) 도달 연도
        oldest_all = {}
        for code in TEST_CODES:
            hit = None
            for y in YEAR_LADDER:
                rs, e = kis_chart(host, tok, keys, code, y, y)
                time.sleep(args.sleep)
                if rs:
                    hit = y; break
            oldest_all[code] = hit
            print(f"     {code}: 최고 도달 {hit if hit else '없음(2014 이후만)'}")
        cand = [v for v in oldest_all.values() if v]
        oldest = min(cand) if cand else None

        # ③ 수정주가 플래그 교차검증 — 삼성전자 2018-05 50:1 분할
        adj_ok, note = None, ""
        c = SPLIT_CASE
        a0, _ = kis_chart(host, tok, keys, c["code"], c["y0"], c["y1"], adj="0")
        time.sleep(args.sleep)
        a1, _ = kis_chart(host, tok, keys, c["code"], c["y0"], c["y1"], adj="1")
        def close_at(rows, ym):
            for x in rows or []:
                if str(x["stck_bsop_date"])[:6] == ym.replace("-", ""):
                    return float(x.get("stck_clpr", 0) or 0)
            return None
        p0, p1 = close_at(a0, c["ym"]), close_at(a1, c["ym"])
        if p0 and p1:
            r = max(p0, p1) / min(p0, p1)
            adj_ok = abs(r - c["ratio"]) / c["ratio"] < 0.2
            note = (f"adj=0 {p0:,.0f} vs adj=1 {p1:,.0f} → 배율 {r:.1f} "
                    f"(기대 {c['ratio']}) {'일치' if adj_ok else '불일치'}")
        elif p0:
            adj_ok = None
            note = f"adj=0 만 응답({p0:,.0f}) — 플래그 무시되는 듯. 분할 전후 레벨을 눈으로 확인 필요"
        else:
            note = "2018년 응답 없음 — 교차검증 불가"
        print(f"     수정주가 플래그 검증: {note}")
        print(f"  ▶ 판정: {verdict(oldest, adj_ok is not False)}")
        return {"channel": f"KIS({label})", "oldest": oldest, "adj_ok": adj_ok}
    return {"channel": "KIS", "oldest": None, "adj_ok": None}


# ────────────────────── 키움 OpenAPI+ (OCX · 32bit 파이썬 필요) ──────────────────────
def smoke_kiwoom(args):
    print("\n" + "=" * 72 + "\n[키움] OpenAPI+ opt10081(일봉 · 수정주가구분)")
    bits = 64 if sys.maxsize > 2 ** 32 else 32
    if os.name != "nt":
        print("  윈도우 아님 — 이 채널은 진우 PC에서만 확인 가능. 스킵"); return None
    if bits != 32:
        print(f"  현재 파이썬 {bits}bit — 키움 OpenAPI+는 **32bit 전용**이다. 문 자체가 안 열린다.")
        print("  32bit 파이썬을 따로 깔아야 함:")
        print("    1) python.org 에서 Windows installer (32-bit) 설치 → 예: C:\\Py32\\python.exe")
        print("    2) C:\\Py32\\python.exe -m pip install PyQt5")
        print("    3) 영웅문 실행 후 로그인 상태에서: C:\\Py32\\python.exe 데이터수리\\broker_adj_smoke.py --only kiwoom")
        return {"channel": "키움", "oldest": None, "adj_ok": None, "skip": "64bit"}
    try:
        from PyQt5.QAxContainer import QAxWidget
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtCore import QEventLoop
    except Exception as e:
        print(f"  PyQt5 없음({e}) → 32bit 파이썬에 pip install PyQt5. 스킵")
        return {"channel": "키움", "oldest": None, "adj_ok": None, "skip": "PyQt5"}

    app = QApplication.instance() or QApplication(sys.argv)
    ax = QAxWidget("KHOPENAPI.KHOpenAPICtrl.1")
    loop = QEventLoop()
    state = {"connected": False, "rows": [], "done": False}

    def on_connect(err):
        state["connected"] = (err == 0)
        if not loop.isRunning(): return
        loop.quit()
    ax.OnEventConnect.connect(on_connect)
    if ax.dynamicCall("GetConnectState()") != 1:
        ax.dynamicCall("CommConnect()")
        loop.exec_()
    if ax.dynamicCall("GetConnectState()") != 1:
        print("  로그인 안 됨 — 영웅문(또는 OpenAPI 로그인창)에서 로그인 후 재실행. 스킵")
        return {"channel": "키움", "oldest": None, "adj_ok": None, "skip": "로그인"}
    print("  로그인 OK")

    def on_data(scr, rq, tr, rec, prev, *a):
        try:
            n = ax.dynamicCall("GetRepeatCnt(QString, QString)", tr, rq)
            for i in range(n):
                d = ax.dynamicCall("GetCommData(QString, QString, int, QString)",
                                   tr, rq, i, "일자").strip()
                c = ax.dynamicCall("GetCommData(QString, QString, int, QString)",
                                   tr, rq, i, "현재가").strip()
                if d:
                    state["rows"].append((d, abs(float(c or 0))))
        finally:
            state["done"] = True
            if loop2.isRunning(): loop2.quit()
    loop2 = QEventLoop()
    ax.OnReceiveTrData.connect(on_data)

    def ask(code, base_date, adj="1"):
        """opt10081: 기준일자 이전 600건. 수정주가구분 1=수정주가 0=원주가."""
        state["rows"], state["done"] = [], False
        ax.dynamicCall("SetInputValue(QString, QString)", "종목코드", code)
        ax.dynamicCall("SetInputValue(QString, QString)", "기준일자", base_date)
        ax.dynamicCall("SetInputValue(QString, QString)", "수정주가구분", adj)
        ax.dynamicCall("CommRqData(QString, QString, int, QString)",
                       "smoke", "opt10081", 0, "0101")
        loop2.exec_()
        time.sleep(max(args.sleep, 0.25))          # 키움 조회 제한(초당 5회 미만) 준수
        return list(state["rows"])

    # 연도 사다리 — 각 연도 12/31 기준으로 이전 데이터가 있는지
    oldest = None
    for code in TEST_CODES:
        hit = None
        for y in YEAR_LADDER:
            rs = ask(code, f"{y}1231")
            if rs:
                hit = y; break
        print(f"  {code}: 최고 도달 {hit if hit else '없음'}")
        if hit and (oldest is None or hit < oldest):
            oldest = hit
    # 수정주가 플래그 교차검증(삼성전자 분할)
    adj_ok, note = None, "교차검증 불가"
    r_adj = {d: p for d, p in ask(SPLIT_CASE["code"], "20180430", adj="1")}
    r_raw = {d: p for d, p in ask(SPLIT_CASE["code"], "20180430", adj="0")}
    common = sorted(set(r_adj) & set(r_raw))
    if common:
        d = common[0]
        r = max(r_adj[d], r_raw[d]) / max(min(r_adj[d], r_raw[d]), 1)
        adj_ok = abs(r - SPLIT_CASE["ratio"]) / SPLIT_CASE["ratio"] < 0.2
        note = (f"{d}: 수정 {r_adj[d]:,.0f} vs 원주 {r_raw[d]:,.0f} → 배율 {r:.1f} "
                f"(기대 {SPLIT_CASE['ratio']}) {'일치' if adj_ok else '불일치'}")
    print(f"  수정주가 플래그 검증: {note}")
    print(f"  ▶ 판정: {verdict(oldest, adj_ok is not False)}")
    return {"channel": "키움", "oldest": oldest, "adj_ok": adj_ok}


# ────────────────────── 대신 CREON Plus (win32com · 32bit) ──────────────────────
def smoke_creon(args):
    print("\n" + "=" * 72 + "\n[대신] CREON Plus CpSysDib.StockChart")
    if os.name != "nt":
        print("  윈도우 아님 — 스킵"); return None
    if sys.maxsize > 2 ** 32:
        print("  CREON Plus도 32bit 파이썬 필요 — 스킵"); return {"channel": "대신", "oldest": None, "skip": "64bit"}
    try:
        import win32com.client as wc
    except Exception:
        print("  pywin32 없음 → pip install pywin32. 스킵"); return {"channel": "대신", "oldest": None, "skip": "pywin32"}
    try:
        if wc.Dispatch("CpUtil.CpCybos").IsConnect != 1:
            print("  CREON Plus 미접속 — 크레온을 **관리자 권한**으로 실행/로그인 후 재시도. 스킵")
            return {"channel": "대신", "oldest": None, "skip": "미접속"}
        ch = wc.Dispatch("CpSysDib.StockChart")
    except Exception as e:
        print(f"  COM 객체 실패({e}) — 스킵"); return {"channel": "대신", "oldest": None, "skip": "COM"}

    def ask(code, y0, y1, adj=1):
        ch.SetInputValue(0, "A" + code)
        ch.SetInputValue(1, ord('1'))                 # 1: 기간으로 요청
        ch.SetInputValue(2, int(f"{y1}1231"))         # to
        ch.SetInputValue(3, int(f"{y0}0101"))         # from
        ch.SetInputValue(5, [0, 5])                   # 0 날짜, 5 종가
        ch.SetInputValue(6, ord('M'))                 # 월봉
        ch.SetInputValue(9, ord('1') if adj else ord('0'))   # 수정주가 반영 여부
        ch.BlockRequest()
        n = ch.GetHeaderValue(3)
        return [(ch.GetDataValue(0, i), ch.GetDataValue(1, i)) for i in range(n)]

    oldest = None
    for code in TEST_CODES:
        hit = None
        for y in YEAR_LADDER:
            try:
                if ask(code, y, y):
                    hit = y; break
            except Exception:
                pass
            time.sleep(args.sleep)
        print(f"  {code}: 최고 도달 {hit if hit else '없음'}")
        if hit and (oldest is None or hit < oldest):
            oldest = hit
    adj_ok, note = None, "교차검증 불가"
    try:
        a = {d: p for d, p in ask(SPLIT_CASE["code"], 2018, 2018, adj=1)}
        b = {d: p for d, p in ask(SPLIT_CASE["code"], 2018, 2018, adj=0)}
        k = [d for d in sorted(set(a) & set(b)) if str(d)[:6] <= "201804"]
        if k:
            d = k[-1]; r = max(a[d], b[d]) / max(min(a[d], b[d]), 1)
            adj_ok = abs(r - SPLIT_CASE["ratio"]) / SPLIT_CASE["ratio"] < 0.2
            note = f"{d}: 수정 {a[d]:,.0f} vs 원주 {b[d]:,.0f} → 배율 {r:.1f} {'일치' if adj_ok else '불일치'}"
    except Exception as e:
        note = f"실패({e})"
    print(f"  수정주가 플래그 검증: {note}")
    print(f"  ▶ 판정: {verdict(oldest, adj_ok is not False)}")
    return {"channel": "대신", "oldest": oldest, "adj_ok": adj_ok}


# ────────────────────────────── 셀프테스트 (네트워크 0) ──────────────────────────────
def _selftest():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("판정: 응답없음 → 닫힘", "닫힘" in verdict(None, True))
    chk("판정: 2014만 → KRX 동급", "KRX와 동급" in verdict(2014, True))
    chk("판정: 2000 + 조정OK → 문 열림", "문 열림" in verdict(2000, True))
    chk("판정: 2000 + 조정실패 → 원주가 의심", "원주가 의심" in verdict(2000, False))
    chk("마스킹: 원문 노출 없음", "SECRETKEY123" not in mask("SECRETKEY123"))
    chk("마스킹: 길이만 노출", mask("SECRETKEY123").startswith("<12자"))
    chk("사다리 오름차순(최고 도달 최소값 탐색 전제)", YEAR_LADDER == sorted(YEAR_LADDER))
    chk("사다리가 2014 경계를 포함", 2014 in YEAR_LADDER and min(YEAR_LADDER) < 2014)
    chk("테스트 종목에 대형+소형 혼합", len(TEST_CODES) >= 3 and "005930" in TEST_CODES)
    chk("분할 교차검증 사건 정의", SPLIT_CASE["ratio"] == 50 and SPLIT_CASE["ym"] == "2018-04")
    # 키 로더 3포맷 — 초판이 .kis_key(2줄 평문)를 못 읽어 "키 없음"으로 스킵된 버그의 회귀검사.
    # 임시폴더에 **가짜 키**를 써서 파서만 검증한다(실제 키는 건드리지 않는다).
    import tempfile, shutil
    global SEARCH_DIRS
    _tmp = tempfile.mkdtemp(prefix="kis_fmt_")
    try:
        SEARCH_DIRS = (_tmp,)          # 실제 키 파일을 절대 주워 읽지 않도록 격리
        open(os.path.join(_tmp, ".kis_key"), "w", encoding="utf-8").write(
            "# 주석줄\nFAKEKEY_AAAA\nFAKESECRET_BBBB\n")
        k, s = load_kis_keys()
        chk("키 포맷 ① .kis_key 2줄 평문 파싱", bool(k) and k["app_key"] == "FAKEKEY_AAAA"
            and k["app_secret"] == "FAKESECRET_BBBB")
        chk("키 출처 표기에 값 미포함", bool(s) and "FAKEKEY_AAAA" not in str(s))
        os.remove(os.path.join(_tmp, ".kis_key"))
        json.dump({"app_key": "JK", "app_secret": "JS"},
                  open(os.path.join(_tmp, ".kis_key.json"), "w", encoding="utf-8"))
        k2, _ = load_kis_keys()
        chk("키 포맷 ② .kis_key.json 파싱", bool(k2) and k2["app_key"] == "JK")
        os.remove(os.path.join(_tmp, ".kis_key.json"))
        json.dump({"appkey": "TK", "appsecret": "TS"},
                  open(os.path.join(_tmp, "진우_KIS키.json"), "w", encoding="utf-8"))
        k3, _ = load_kis_keys()
        chk("키 포맷 ③ 진우_KIS키.json 파싱", bool(k3) and k3["app_key"] == "TK")
        os.remove(os.path.join(_tmp, "진우_KIS키.json"))
        open(os.path.join(_tmp, ".kis_key"), "w", encoding="utf-8").write(
            "여기에_APP_KEY_붙여넣기\n여기에_APP_SECRET_붙여넣기\n")
        k4, _ = load_kis_keys()
        chk("예시값 그대로면 키로 인정하지 않음", k4 is None or k4["app_key"] != "여기에_APP_KEY_붙여넣기")
    finally:
        SEARCH_DIRS = None
        shutil.rmtree(_tmp, ignore_errors=True)
    # 주문 API가 섞여 들어오지 않았는지 감시. 바늘 문자열을 쪼개 둔 이유: 이 검사 자체가
    # 파일에 리터럴을 남기면 영원히 FAIL 한다(초판에서 실제로 그렇게 됐다).
    src = open(os.path.abspath(__file__), encoding="utf-8").read()
    needles = ["order" + "-cash", "Send" + "Order", "Cp" + "Trade", "TTTC" + "0802U"]
    hits = [n for n in needles if src.count(n) > 1]   # 1회는 이 검사 자신의 조립분
    chk(f"주문 관련 코드 부재(조회 전용){' 위반:' + str(hits) if hits else ''}", not hits)
    print(f"\n셀프테스트: {ok}/{tot} — 네트워크·키·주문 없이 판정 로직만 검증")
    print("실제 스모크는 진우 PC에서: py 데이터수리\\broker_adj_smoke.py")
    return ok == tot


def main():
    ap = argparse.ArgumentParser(description="증권사 API 2014년 이전 수정주가 도달 스모크(조회 전용)")
    ap.add_argument("--only", choices=["kis", "kiwoom", "creon"], help="한 채널만")
    ap.add_argument("--host", choices=["auto", "paper", "live"], default="auto",
                    help="KIS 도메인. auto=모의 먼저 실패 시 실전(둘 다 조회 전용)")
    ap.add_argument("--sleep", type=float, default=0.35, help="호출 간 대기(초)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return 0 if _selftest() else 1

    print("증권사 수정주가 스모크 — '2014년 이전에 닿는가'만 본다 (주문 없음·조회 전용)")
    print(f"파이썬 {sys.version.split()[0]} {'64' if sys.maxsize > 2**32 else '32'}bit · OS {os.name}")
    plan = [a.only] if a.only else ["kis", "kiwoom", "creon"]
    fn = {"kis": smoke_kis, "kiwoom": smoke_kiwoom, "creon": smoke_creon}
    res = []
    for k in plan:
        try:
            r = fn[k](a)
            if r: res.append(r)
        except Exception as e:
            print(f"  [{k}] 예외: {type(e).__name__}: {e}")
    print("\n" + "=" * 72 + "\n요약")
    if not res:
        print("  확인된 채널 없음 — 키/로그인/32bit 조건을 먼저 갖춰야 함")
    for r in res:
        print(f"  {r['channel']:<12s} 최고 도달 {str(r.get('oldest') or '-'):>6s} · "
              f"수정주가 {'OK' if r.get('adj_ok') else ('미확인' if r.get('adj_ok') is None else '실패')}")
    best = [r for r in res if r.get("oldest") and r["oldest"] < 2014]
    tested = [r for r in res if r.get("oldest") is not None or not r.get("skip")]
    if best:
        con = "★2014년 이전 조정 시계열 확보 가능 → 30년 창 복원 착수 (유료 벤더 불필요)"
    elif tested:
        con = "실제로 두드려 본 채널은 모두 2014년 벽 → MDD 낙관 편향을 '한계'로 명기하고, 유료 벤더는 비용 대비 효익 판단 후"
    else:
        con = ("**아직 아무것도 판정되지 않았다**(키·로그인·32bit 미충족으로 두드려 보지 못함) — "
               "'2014년 벽'이라고 결론 내리면 안 된다. 조건을 갖추고 재실행할 것")
    print("\n결론: " + con)
    print("⚠️ 이 결과를 나에게 그대로 붙여주면 다음 단계(대량 수집 or 한계 명기)를 결정한다.")
    print("⚠️ 붙일 때 키 파일 내용은 절대 포함하지 말 것 — 이 스크립트는 키를 찍지 않는다.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
