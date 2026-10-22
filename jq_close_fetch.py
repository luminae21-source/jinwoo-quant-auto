# -*- coding: utf-8 -*-
"""jq_close_fetch.py — 장 마감 데이터 자동 수집 (Claude 웹검색 대체 · 토큰 0).

pykrx(KRX 확정치)로 아래 3개 JSON을 오늘자로 채운다 → jq_close_card/stocks/watch_card.py가 그린다.
  jq_close_data.json   지수·투자자 수급·동인(데이터로 만든 1줄)
  jq_close_stocks.json 급등 상위·거래대금 상위·업종 상승률·시장 폭·추세 관심종목 등락
  jq_watchlist.json    종목 목록·상태는 그대로, updated·note(오늘 등락)만 갱신
오늘 데이터가 아직 없으면 3분 간격 재시도(최대 30분). 끝내 없으면 exit 1, 파일은 안 건드림.
사용: py -3 jq_close_fetch.py            (jq_close_auto.bat가 카드 렌더 전에 호출)
      py -3 jq_close_fetch.py --self-test
"""
import os, sys, json, time, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

TRIES, WAIT_SEC = 11, 180
LIMIT_UP = 29.5  # 가격제한 ±30% → 29.5% 이상을 상한가로 표기


def eok(won):
    return int(round(float(won) / 1e8))


def fmt_value(won):
    won = float(won)
    return f"{won/1e12:.1f}조" if won >= 1e12 else f"{won/1e8:,.0f}억"


def index_close(stock, d, code):
    """(종가, 등락률%) — 마지막 행이 d가 아니면 None(아직 미발표)."""
    s = (datetime.datetime.strptime(d, "%Y%m%d") - datetime.timedelta(days=12)).strftime("%Y%m%d")
    df = stock.get_index_ohlcv(s, d, code)
    if df is None or len(df) < 2 or df.index[-1].strftime("%Y%m%d") != d:
        return None
    c, p = float(df["종가"].iloc[-1]), float(df["종가"].iloc[-2])
    return round(c, 2), round((c / p - 1) * 100, 2)


def flows(stock, d, market):
    """{'기관','외국인','개인'} 억원 — 비어 있으면 None. 행 이름은 시장브리핑_생성.krx_flow와 동일 규칙."""
    df = stock.get_market_trading_value_by_investor(d, d, market)
    if df is None or not len(df) or "순매수" not in df.columns:
        return None
    def g(names):
        for n in names:
            if n in df.index:
                return eok(df.loc[n, "순매수"])
        return None
    out = {"기관": g(["기관합계", "기관계", "기관"]), "외국인": g(["외국인", "외국인합계"]), "개인": g(["개인"])}
    if all(v in (None, 0) for v in out.values()):
        return None
    return out


def market_ohlcv(stock, d):
    """코스피+코스닥 전 종목(종가·거래대금·등락률·name·mkt). 거래량 합 0이면 None."""
    import pandas as pd
    parts = []
    for mkt in ("KOSPI", "KOSDAQ"):
        df = stock.get_market_ohlcv(d, market=mkt)
        if df is None or not len(df) or float(df["거래량"].sum()) == 0:
            return None
        df = df.copy(); df["mkt"] = mkt
        df["name"] = [str(stock.get_market_ticker_name(t)) for t in df.index]
        parts.append(df)
    return pd.concat(parts)


def sectors(stock, d, kospi_chg):
    """코스피 업종 등락률 [(이름, %)] 내림차순. 같은 날 '코스피' 행이 지수 등락률과 안 맞으면 [] (계산 기준 불일치 방지)."""
    try:
        df = stock.get_index_price_change(d, d, "KOSPI")
        if "코스피" not in df.index or abs(float(df.loc["코스피", "등락률"]) - kospi_chg) > 0.05:
            print("  [업종] 등락률 검증 불일치 → 업종 칸 생략")
            return []
        rows = [(str(n), round(float(r["등락률"]), 2)) for n, r in df.iterrows() if "코스피" not in str(n)]
        return sorted(rows, key=lambda x: -x[1])
    except Exception as e:
        print("  [업종] 수집 실패 → 업종 칸 생략:", e)
        return []


def fetch(stock, d):
    """오늘(d) 데이터가 다 나왔으면 dict, 아니면 None."""
    k, q = index_close(stock, d, "1001"), index_close(stock, d, "2001")
    fk, fq = flows(stock, d, "KOSPI"), flows(stock, d, "KOSDAQ")
    if not (k and q and fk):
        return None
    ohlcv = market_ohlcv(stock, d)
    if ohlcv is None:
        return None
    return {"kospi": k, "kosdaq": q, "fk": fk, "fq": fq, "ohlcv": ohlcv, "sectors": sectors(stock, d, k[1])}


def _flow_txt(f):
    return "·".join(f"{w} {'순매수' if v > 0 else '순매도'}" for w, v in (("외국인", f["외국인"]), ("기관", f["기관"])) if v)


def build(today, r, wl):
    """수집 결과 r → (data, stocks, wl). 숫자는 전부 r에서만 — 지어내는 값 없음."""
    iso = f"{today[:4]}-{today[4:6]}-{today[6:]}"
    mmdd = f"{today[4:6]}/{today[6:]}"
    o, sec = r["ohlcv"], r["sectors"]
    src = f"KRX 확정치(pykrx) {iso} 마감 · 자동수집"
    drv = [f"코스피 {r['kospi'][1]:+.2f}%", _flow_txt(r["fk"])]
    if sec:
        drv.append(f"강세 {sec[0][0]} {sec[0][1]:+.2f}% / 약세 {sec[-1][0]} {sec[-1][1]:+.2f}%")
    data = {"date": iso, "kospi": r["kospi"][0], "kospi_chg": r["kospi"][1],
            "kosdaq": r["kosdaq"][0], "kosdaq_chg": r["kosdaq"][1], "inv": r["fk"],
            "driver": " · ".join(x for x in drv if x), "sources": src}
    if r["fq"]:
        fq = r["fq"]
        data["insight"] = f"수급=코스피 기준. 코스닥: 개인 {fq['개인']:+,} 외국인 {fq['외국인']:+,} 기관 {fq['기관']:+,}"

    def br(m):
        x = o[o["mkt"] == m]["등락률"]
        return f"상승 {int((x > 0).sum()):,} / 하락 {int((x < 0).sum()):,}"
    n_up = int((o["등락률"] >= LIMIT_UP).sum())
    top = o.sort_values("등락률", ascending=False).head(5)
    val = o.sort_values("거래대금", ascending=False).head(5)
    kv = float(o[o["mkt"] == "KOSPI"]["거래대금"].sum())
    stocks = {"date": iso,
              "driver": f"코스피 거래대금 {fmt_value(kv)} · 거래대금 1위 {val.iloc[0]['name']} · {_flow_txt(r['fk'])}",
              "breadth": f"코스피 {br('KOSPI')} · 코스닥 {br('KOSDAQ')} (상한가 {n_up})",
              "gainers": [[n, round(float(p), 2), "상한가" if p >= LIMIT_UP else ""] for n, p in zip(top["name"], top["등락률"])],
              "value_top": [[n, fmt_value(v)] for n, v in zip(val["name"], val["거래대금"])],
              "sector_top": [[n, p] for n, p in sec[:6]],
              "trend_watch": [],
              "note": "추세 관심종목=조정에도 추세 살아있는 주도 섹터 대표주. 지지 재확인 후 관심·손절 동시설정. 추천 아님·본인 책임.",
              "sources": src}
    if wl:
        chg = dict(zip(o["name"], o["등락률"]))
        for it in wl.get("items", []):
            c = chg.get(it.get("name"))
            it["note"] = f"{mmdd} {c:+.2f}%" if c is not None else f"{mmdd} 등락 미확인(종목명 불일치)"
            if c is not None and it.get("status") != "이탈·제외후보" and len(stocks["trend_watch"]) < 5:
                stocks["trend_watch"].append([it["name"], it.get("theme", ""), f"{c:+.2f}%"])
        wl["updated"] = iso
        wl["sources"] = src + " · 목록·상태는 수동 관리(자동 변경 안 함)"
    return data, stocks, wl


def _save(name, obj):
    with open(os.path.join(HERE, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def main():
    from pykrx import stock
    today = datetime.date.today().strftime("%Y%m%d")
    for i in range(1, TRIES + 1):
        try:
            r = fetch(stock, today)
        except Exception as e:
            print(f"  [오류] {e}"); r = None
        if r:
            break
        if i < TRIES:
            print(f"[대기] {today} 마감 데이터 아직 없음 — {WAIT_SEC//60}분 후 재시도 ({i}/{TRIES-1})"); sys.stdout.flush()
            time.sleep(WAIT_SEC)
    else:
        print(f"[중단] {today} 마감 데이터 미발표(휴장·지연) — JSON 그대로 둠"); return 1
    wp = os.path.join(HERE, "jq_watchlist.json")
    wl = json.load(open(wp, encoding="utf-8")) if os.path.exists(wp) else None
    data, stocks, wl = build(today, r, wl)
    _save("jq_close_data.json", data); _save("jq_close_stocks.json", stocks)
    if wl: _save("jq_watchlist.json", wl)
    print(f"[수집] {data['date']} 코스피 {data['kospi']:,} ({data['kospi_chg']:+.2f}%) · 코스닥 {data['kosdaq']:,} ({data['kosdaq_chg']:+.2f}%)")
    print(f"[수집] 급등 {len(stocks['gainers'])} · 거래대금 {len(stocks['value_top'])} · 업종 {len(stocks['sector_top'])} · 워치 {len(stocks['trend_watch'])}")
    return 0


def self_test():
    import pandas as pd
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += bool(c); print(("  OK  " if c else "  FAIL") + " " + n)
    D = "20261023"
    class S:  # 가짜 pykrx — 열 이름·인덱스 모양은 실제와 동일
        ready = True
        def get_index_ohlcv(self, s, e, code):
            days = pd.to_datetime(["2026-10-22", "2026-10-23" if self.ready else "2026-10-22"])
            c = [5000.0, 5100.0] if code == "1001" else [800.0, 792.0]
            return pd.DataFrame({"종가": c}, index=days)
        def get_market_trading_value_by_investor(self, s, e, m):
            return pd.DataFrame({"순매수": [-6834e8, -3991e8, 10364e8]}, index=["기관합계", "외국인", "개인"])
        def get_market_ohlcv(self, d, market):
            if market == "KOSPI":
                return pd.DataFrame({"종가": [1, 2, 3], "거래량": [10, 10, 10], "거래대금": [3e12, 5e11, 1e9],
                                     "등락률": [2.0, -1.0, 30.0]}, index=["005930", "000660", "123456"])
            return pd.DataFrame({"종가": [1, 2], "거래량": [5, 5], "거래대금": [2e11, 1e10],
                                 "등락률": [-3.0, 0.0]}, index=["247540", "999999"])
        def get_market_ticker_name(self, t):
            return {"005930": "삼성전자", "000660": "SK하이닉스", "123456": "급등주", "247540": "에코프로비엠", "999999": "보합주"}[t]
        def get_index_price_change(self, s, e, m):
            return pd.DataFrame({"등락률": [2.0, 1.5, 3.1, -2.2]}, index=["코스피", "코스피 200", "전기·전자", "화학"])
    st = S()
    r = fetch(st, D)
    chk("데이터 준비 시 수집됨", r is not None)
    chk("코스피 등락률 = +2.0%", r["kospi"] == (5100.0, 2.0))
    chk("업종: '코스피' 계열 제외·내림차순", r["sectors"] == [("전기·전자", 3.1), ("화학", -2.2)])
    wl = {"updated": "2026-10-22", "items": [
        {"name": "삼성전자", "theme": "반도체", "status": "추세 유효", "note": "x"},
        {"name": "없는종목", "theme": "?", "status": "추세 유효", "note": "x"},
        {"name": "에코프로비엠", "theme": "2차전지", "status": "이탈·제외후보", "note": "x"}]}
    data, stocks, wl2 = build(D, r, wl)
    chk("수급 억원 변환", data["inv"] == {"기관": -6834, "외국인": -3991, "개인": 10364})
    chk("동인에 수급·업종 포함", "외국인 순매도·기관 순매도" in data["driver"] and "강세 전기·전자" in data["driver"])
    chk("급등 1위 상한가 표기", stocks["gainers"][0] == ["급등주", 30.0, "상한가"])
    chk("거래대금 1위 3.0조", stocks["value_top"][0] == ["삼성전자", "3.0조"])
    chk("시장폭 코스피 상승2/하락1", "코스피 상승 2 / 하락 1" in stocks["breadth"])
    chk("워치: 상태 유지·note만 등락", wl2["items"][0]["status"] == "추세 유효" and wl2["items"][0]["note"] == "10/23 +2.00%")
    chk("워치: 이름 불일치 표기", "미확인" in wl2["items"][1]["note"])
    chk("추세관심: 제외후보 빠짐", [x[0] for x in stocks["trend_watch"]] == ["삼성전자"])
    chk("워치 updated=오늘", wl2["updated"] == "2026-10-23")
    st.ready = False
    chk("미발표면 None(재시도 대상)", fetch(st, D) is None)
    st.ready = True
    st.get_index_price_change = lambda s, e, m: pd.DataFrame({"등락률": [9.9]}, index=["코스피"])
    chk("업종 검증 불일치면 생략", sectors(st, D, 2.0) == [])
    print("self-test: %d/%d" % (ok, tot)); return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
