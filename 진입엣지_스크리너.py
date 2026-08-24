#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진입엣지_스크리너.py — 채택 규칙을 실제 종목 선택에 쓰는 스크리너 (STANDALONE)

목적: 검정에서 채택된 진입 엣지를 **오늘 시점의 후보 리스트**로.
  · 소형 = 저변동성 (60일 변동성 낮은 쪽) — 결합이 단독 못이김
  · 중형 = 저변동성 × 저PBR 교집합 (싸고 안정적 둘 다) — OOS 증분 +1%p
  · 대형 = 규칙 없음(소>대 5번 반복) → 제외
필터는 **백테스트와 동일**: 종가≥1000 · 20일 평균거래대금≥5억. (jq_discover의 30억·자금유입과 달리
느슨해서 조용한 소·중형이 살아남는다.) 데이터는 **30년 패널(5,057종목, 소형 포함)**.

⚠️ 발굴 ≠ 매수신호. 하순이면 신규진입 보류. 진입 시 손절(트레일−15/고정−8) 동시 설정. 결정·책임 본인.

사용:
  py 진입엣지_스크리너.py --self-test
  py 진입엣지_스크리너.py --top 15
  py 진입엣지_스크리너.py --top 15 --asof 2026-07-13
"""
import os, sys, argparse, warnings
from datetime import date, datetime
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MIN_PRICE = 1000
MIN_ADV = 5e8          # 20일 평균 거래대금 5억 (백테스트 동일)
VOL_N = 60             # 저변동성 창
TRAIL = 0.15           # 트레일−15 참고 손절
MIN_VOL60 = 0.008      # 최소 변동성(일간 0.8%). 그 아래 = 스팩·휴면 껍데기(안 움직여서 저변동) → 제외


def load_daily():
    fs = []
    for f in ("종목일봉_30년_KOSPI.csv", "종목일봉_30년_KOSDAQ.csv"):
        p = os.path.join(HERE, f)
        if not os.path.exists(p):
            print(f"  [없음] {f}"); return None
        d = pd.read_csv(p, usecols=["date", "code", "close", "volume"],
                        dtype={"code": str}, encoding="utf-8-sig", on_bad_lines="skip")
        fs.append(d)
    d = pd.concat(fs, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d["volume"] = pd.to_numeric(d["volume"], errors="coerce")
    d = d.dropna(subset=["date", "close"])
    return d[d["close"] > 0].sort_values(["code", "date"])


def load_pbr():
    out = {}
    for f in ("종목재무_KRX_KOSPI.csv", "종목재무_KRX_KOSDAQ.csv"):
        p = os.path.join(HERE, f)
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p, dtype={"code": str}, usecols=["date", "code", "PBR"], encoding="utf-8-sig")
        d["PBR"] = pd.to_numeric(d["PBR"], errors="coerce")
        d = d[d["PBR"] > 0].dropna(subset=["PBR"]).sort_values("date").groupby("code").tail(1)
        for _, r in d.iterrows():
            out[str(r["code"]).zfill(6)] = float(r["PBR"])
    return out


def load_mcap():
    p = os.path.join(HERE, "종목시총_30년.csv")
    if not os.path.exists(p):
        return {}, None
    d = pd.read_csv(p, dtype={"code": str}, usecols=["date", "code", "mcap"], encoding="utf-8-sig")
    d["mcap"] = pd.to_numeric(d["mcap"], errors="coerce")
    d = d.dropna(subset=["mcap"]).sort_values("date").groupby("code").tail(1)
    mp = {str(r["code"]).zfill(6): float(r["mcap"]) for _, r in d.iterrows()}
    return mp, None   # cuts는 스냅샷 유니버스에서 계산(build_snapshot)


def load_names():
    out = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            try:
                d = pd.read_csv(p, dtype={"code": str})
            except Exception:
                continue
            for _, r in d.iterrows():
                c = str(r["code"]).zfill(6)
                out.setdefault(c, r.get("name"))
    return out


def build_snapshot(daily, pbr_map, mcap_map, names=None, asof=None, min_vol=MIN_VOL60):
    """as-of 시점 스냅샷: 종목별 vol60·adv20·close + PBR·mcap·tier.
    스팩·우선주·초저변동(휴면) 제외 → 저변동 꼬리 왜곡 방지."""
    names = names or {}
    d = daily
    if asof is not None:
        d = d[d["date"] <= pd.Timestamp(asof)]
    d = d.sort_values(["code", "date"])
    g = d.groupby("code", sort=False)
    close = g["close"].last()
    ret = g["close"].pct_change()
    d = d.assign(ret=ret, val=d["close"] * d["volume"])
    vol60 = d.groupby("code")["ret"].apply(lambda s: s.tail(VOL_N).std())
    adv20 = d.groupby("code")["val"].apply(lambda s: s.tail(20).mean())
    n = g["close"].count()
    T = pd.DataFrame({"close": close, "vol60": vol60, "adv20": adv20, "n": n}).reset_index()
    T = T[T["n"] >= VOL_N]                                  # 이력 충분
    T = T[(T["close"] >= MIN_PRICE) & (T["adv20"] >= MIN_ADV)]   # 백테스트 거래필터
    T["PBR"] = T["code"].map(pbr_map)
    T["mcap"] = T["code"].map(mcap_map)
    T["name"] = T["code"].map(names)
    # ★ 스팩·우선주·휴면(초저변동) 제외 — 저변동 랭킹이 껍데기로 오염되는 것 방지
    nm = T["name"].fillna("")
    is_spac = nm.str.contains("스팩")
    is_pref = nm.str.rstrip().apply(lambda s: s.endswith(("우", "우B", "우C")))
    T = T[~(is_spac | is_pref)]
    T = T[T["vol60"] >= min_vol]                            # 초저변동(스팩·휴면) 하한
    # 시총 tier: 거래가능 유니버스 내 tercile
    v = T["mcap"].dropna()
    if len(v) >= 6:
        q1, q2 = np.quantile(v, [1/3, 2/3])
        T["tier"] = np.where(T["mcap"] < q1, "소", np.where(T["mcap"] < q2, "중", "대"))
        T.loc[T["mcap"].isna(), "tier"] = "중"    # 모르면 중립
    else:
        T["tier"] = "중"
    return T


def rank_candidates(T, top):
    """소형=저변동성 / 중형=저변동×저PBR 교집합 / 대형=제외."""
    out = {}
    # 소형: 저변동성 오름차순
    so = T[T["tier"] == "소"].copy()
    so = so.sort_values("vol60").head(top)
    so["규칙"] = "소형·저변동성"
    so["손절_트레일15"] = (so["close"] * (1 - TRAIL)).round().astype("Int64")
    out["소"] = so

    # 중형: 저변동·저PBR 둘 다 하위(교집합) → 합산랭크로 정렬
    jo = T[(T["tier"] == "중") & T["PBR"].notna()].copy()
    if len(jo) >= 6:
        jo["r_vol"] = jo["vol60"].rank(pct=True)        # 낮을수록 좋음
        jo["r_pbr"] = jo["PBR"].rank(pct=True)          # 낮을수록 좋음
        jo["결합점수"] = (jo["r_vol"] + jo["r_pbr"]) / 2
        # 교집합 강조: 둘 다 하위 1/2 안에 든 것 우선
        jo["교집합"] = (jo["r_vol"] <= 0.5) & (jo["r_pbr"] <= 0.5)
        jo = jo.sort_values(["교집합", "결합점수"], ascending=[False, True]).head(top)
    else:
        jo = jo.sort_values("vol60").head(top)
        jo["결합점수"] = np.nan; jo["교집합"] = False
    jo["규칙"] = "중형·저변동×저PBR"
    jo["손절_트레일15"] = (jo["close"] * (1 - TRAIL)).round().astype("Int64")
    out["중"] = jo
    return out


def is_late_month_simple(asof, trading_days):
    """월말 역순 −9~−5거래일이면 True (하순). trading_days: 정렬된 거래일 리스트."""
    td = [t for t in trading_days if t.month == asof.month and t.year == asof.year]
    if not td:
        return None
    # asof 이후의 이 달 남은 거래일 포함해 월말까지 역순 위치
    future = [t for t in trading_days if t >= pd.Timestamp(asof)]
    same = [t for t in future if t.month == asof.month and t.year == asof.year]
    # 이 달 마지막 거래일 추정: 같은 달 거래일 중 최대
    rdom = len([t for t in td if t >= pd.Timestamp(asof)])   # 월말까지 남은 거래일 수(≈ 역순 위치)
    if rdom == 0:
        return None
    return 5 <= rdom <= 9, rdom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--asof", default=None, help="YYYY-MM-DD (기본 최신)")
    ap.add_argument("--min-vol", type=float, default=MIN_VOL60,
                    help="최소 일간변동성(스팩·휴면 제외 하한, 기본 0.008)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1

    daily = load_daily()
    if daily is None:
        return 2
    asof = pd.Timestamp(a.asof) if a.asof else daily["date"].max()
    pbr_map = load_pbr(); mcap_map, _ = load_mcap(); names = load_names()
    print(f"기준일 {asof.date()} · 진입엣지 스크리너 (백테스트 필터: 종가≥1000·adv20≥5억)", flush=True)

    # 하순 판정
    tds = sorted(pd.to_datetime(daily["date"].unique()))
    lm = is_late_month_simple(asof.to_pydatetime().date() if hasattr(asof, 'to_pydatetime') else asof, tds)
    if lm is None:
        print("  월중 위치 판정불가")
    else:
        late, rdom = lm
        print(f"  {'🔴 하순('+str(rdom)+'거래일) — 코스닥 소·중형 신규진입 보류 권고' if late else '🟢 진입 가능 구간('+str(rdom)+'거래일) — 하순 아님'}")

    T = build_snapshot(daily, pbr_map, mcap_map, names, asof, a.min_vol)
    print(f"  거래가능 유니버스 {len(T)}종목 (스팩·우선주·초저변동<{a.min_vol*100:.1f}% 제외) · "
          f"tier {T['tier'].value_counts().to_dict()}", flush=True)
    cand = rank_candidates(T, a.top)

    allrows = []
    for tier in ("소", "중"):
        sub = cand[tier]
        if sub is None or len(sub) == 0:
            print(f"\n[{tier}형] 후보 없음"); continue
        sub = sub.copy()
        sub["name"] = sub["code"].map(names).fillna(sub["code"])
        print(f"\n===== {sub['규칙'].iloc[0]} · 상위 {len(sub)} =====")
        cols = ["name", "close", "vol60", "PBR", "손절_트레일15"]
        disp = sub[[c for c in cols if c in sub.columns]].copy()
        disp["vol60"] = (disp["vol60"] * 100).round(1)
        disp = disp.rename(columns={"close": "현재가", "vol60": "변동성60%", "손절_트레일15": "손절참고"})
        print(disp.to_string(index=False))
        allrows.append(sub.assign(tier=tier))

    if allrows:
        out = pd.concat(allrows, ignore_index=True)
        keep = ["tier", "규칙", "code", "name", "close", "vol60", "PBR", "mcap", "손절_트레일15", "결합점수", "교집합"]
        out = out[[c for c in keep if c in out.columns]]
        p = os.path.join(HERE, "진입엣지_후보.csv")
        out.to_csv(p, index=False, encoding="utf-8-sig")
        print(f"\n[산출] 진입엣지_후보.csv ({len(out)}종목)")
    print("\n발굴 ≠ 매수신호 · 진입 시 손절(트레일−15/고정−8) 동시 설정 · 대형은 규칙 밖 · 결정·책임 본인")
    return 0


def _self_test():
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # 합성 일봉: 3종목 × 80일. A=저변동, B=고변동, C=중간
    dts = pd.bdate_range("2026-03-01", periods=80)
    rng = np.random.default_rng(0)
    rows = []
    for code, sig in (("000001", 0.005), ("000002", 0.05), ("000003", 0.02)):
        px = 2000.0
        for dt in dts:
            px *= (1 + rng.normal(0, sig))
            rows.append({"date": dt, "code": code, "close": px, "volume": 1_000_000})
    daily = pd.DataFrame(rows).sort_values(["code", "date"])
    pbr = {"000001": 2.0, "000002": 0.5, "000003": 1.0}
    mc = {"000001": 100e8, "000002": 300e8, "000003": 800e8}
    T = build_snapshot(daily, pbr, mc, names={}, asof=None, min_vol=0.0)
    chk("스냅샷 생성(3종목)", len(T) == 3)
    chk("vol60 계산됨", T["vol60"].notna().all())
    chk("저변동 A < 고변동 B",
        float(T[T.code == "000001"]["vol60"].iloc[0]) < float(T[T.code == "000002"]["vol60"].iloc[0]))

    # 거래필터: adv<5억 제외
    d2 = daily.copy(); d2.loc[d2.code == "000002", "volume"] = 1   # B 거래대금 미미
    T2 = build_snapshot(d2, pbr, mc, names={}, asof=None, min_vol=0.0)
    chk("adv<5억 종목 제외", "000002" not in set(T2["code"]))

    # ★ 스팩·우선주·초저변동 제외
    nm = {"000001": "OK전자", "000002": "가나스팩3호", "000003": "삼성전자 우"}
    Tx = build_snapshot(daily, pbr, mc, names=nm, asof=None, min_vol=0.0)
    chk("스팩 이름 제외", "000002" not in set(Tx["code"]))
    chk("우선주 이름 제외", "000003" not in set(Tx["code"]))
    Tv = build_snapshot(daily, pbr, mc, names={}, asof=None, min_vol=0.02)  # A(0.5%)<2% → 제외
    chk("초저변동(<하한) 제외", "000001" not in set(Tv["code"]))

    # tier 분류(6종목 이상 필요) — 별도 확인
    mc6 = {f"{i:06d}": (50 + i * 100) * 1e8 for i in range(1, 7)}
    T6 = pd.DataFrame({"code": list(mc6), "close": 2000.0, "vol60": 0.02,
                       "adv20": 1e9, "n": 80, "PBR": 1.0})
    T6["mcap"] = T6["code"].map(mc6)
    v = T6["mcap"]; q1, q2 = np.quantile(v, [1/3, 2/3])
    T6["tier"] = np.where(T6["mcap"] < q1, "소", np.where(T6["mcap"] < q2, "중", "대"))
    chk("tier 소/중/대 분포", set(T6["tier"]) == {"소", "중", "대"})

    # 랭킹: 소형은 저변동 우선
    Tr = pd.DataFrame({"code": ["s1", "s2", "s3"], "close": 2000.0,
                       "vol60": [0.01, 0.03, 0.02], "adv20": 1e9, "n": 80,
                       "PBR": [1.0, 1.0, 1.0], "mcap": 50e8, "tier": "소"})
    r = rank_candidates(Tr, 3)
    chk("소형 저변동 1위 = s1(0.01)", r["소"].iloc[0]["code"] == "s1")

    # 중형 결합: 저변동+저PBR 둘 다 낮은 것 우선
    Tm = pd.DataFrame({"code": ["m1", "m2", "m3", "m4", "m5", "m6"], "close": 2000.0,
                       "vol60": [0.01, 0.05, 0.02, 0.04, 0.03, 0.06], "adv20": 1e9, "n": 80,
                       "PBR": [0.5, 3.0, 0.6, 2.5, 0.8, 3.5], "mcap": 500e8, "tier": "중"})
    rm = rank_candidates(Tm, 6)["중"]
    chk("중형 결합 1위 = m1(저변동+저PBR)", rm.iloc[0]["code"] == "m1")
    chk("손절 트레일15 = 종가×0.85", int(rm.iloc[0]["손절_트레일15"]) == int(2000 * 0.85))

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


if __name__ == "__main__":
    sys.exit(main())
