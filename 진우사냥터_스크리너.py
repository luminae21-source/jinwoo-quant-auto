#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우사냥터_스크리너.py — 진우 스타일 안에서 '더 싸고(저PBR) 덜 출렁이는(저변동)' 종목 탐색기

기획서: 진우_사냥터_발굴툴_기획.md (2026-07-17 6절 확정)
근거   : 가상매매\검증\섹터내_기울기_결과.md (저PBR OOS t=+3.17 우세 · 저변동 +2.68, 둘 다 조건부)
손절/사이징: 매도규칙서 v2 §1·§3 (jq_discover.py와 동일 규칙)

핵심(정직한 프레이밍):
  · 이건 "이기는 시스템"이 아니라 "동점자 가르기" 툴이다.
  · 진우님 스타일(대형·초고변동·고PBR 성장주)은 전시장 엣지의 반대다. 평균 오르막.
  · 툴이 하는 건 그 오르막 안에서 상대적으로 나은 쪽(저PBR·저변동)으로 기울이는 것뿐.
  · 기울기는 조건부 검증(2028 재판정). 스톱은 타협 불가.

유니버스 = 하이브리드 합집합:
  ① 섹터내 검정 유니버스: 기술제조 섹터 키워드(검정 스크립트와 동일) 매칭 종목.
  ② 특성기반: 초고변동(vol60>4%) + 고PBR/성장(PBR>2) + 중·대형(시총 floor 이상).
  → union, 코드 유일화. 섹터맵에 없는 성장주(예: 에코프로=금융업 오분류)도 포착.

랭킹 = 사냥터내 상대 percentile:
  · PBR·vol60을 유니버스 전체(=진우 사냥터 peer group) 내 percentile로 환산(절대값 아님).
  · 점수 = 0.65·(저PBR) + 0.35·(저변동). 낮을수록 상위.

부가(초고변동이므로 필수):
  · 손절 = max(현재가 − 2.5×ATR14, 현재가×0.80) · 트레일 = (최고가 − 2.5×ATR14) 래칫.
  · 리스크 기반 수량: (자본×리스크%) ÷ 1R, 1R = 현재가 − 손절가. 리스크 기본 1%.
  · 섹터당 2종 · 동시 5~7종 · 돌파(추격)는 리스크 0.5%·발굴참고용(매도규칙서 §3·§8).
  · 하순 플래그: 월말 잔여 거래일 5~9일 구간이면 신규진입 보류 권고.

산출: 진우사냥터_후보.csv + 콘솔 표.
사용: py 진우사냥터_스크리너.py [--capital 10000000] [--risk 1.0] [--top 30]
      py 진우사냥터_스크리너.py --self-test

⚠️ 섹터매핑=현재상장 기준 → 롱온리 절대수익은 생존편향. 이 툴은 랭킹·기울기 용도.
   투자자문 아님. 발굴 ≠ 매수신호. 결정·책임은 본인.
"""
import os, sys, argparse, warnings
from datetime import date
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── 파라미터 (검정 스크립트와 동일 기준) ──────────────────────────
SECTOR_KW = ["반도체", "전자부품", "이차전지", "특수 목적용 기계",
             "일반 목적용 기계", "광학", "전기장비", "통신 및 방송 장비"]
MIN_PRICE = 1000          # 거래필터: 종가
MIN_ADV   = 5e8           # 거래필터: 20일 평균거래대금
VOL_HI    = 0.04          # 특성기반: 초고변동 vol60 임계
PBR_HI    = 2.0           # 특성기반: 고PBR/성장 프록시
CAP_FLOOR = 3e11          # 특성기반: 중형 이상 시총 floor (3,000억)
W_PBR, W_VOL = 0.65, 0.35 # 기울기 가중 (OOS 저PBR 우세 반영)
# 손절/사이징 = 매도규칙서 v2 §1·§3 (jq_discover.py와 동일 규칙)
ATR_N, ATR_K = 14, 2.5    # 손절 = 현재가 − 2.5×ATR14
STOP_CAP = 0.20           # 손절 floor = 현재가 × (1 − 0.20)
RECENT_ROWS = 600000      # --recent 고속 모드: 일봉 끝 N행만(최근 ~300거래일, 전체와 동일결과)

# 진우 6종목 (검증 앵커) — 코드:이름
JINWOO6 = {
    "247540": "에코프로비엠", "086520": "에코프로", "036930": "주성엔지니어링",
    "353200": "대덕전자", "450080": "에코프로머티", "089030": "테크윙",
}


# ── 로더 ─────────────────────────────────────────────────────────
def load_maps(pd):
    """code -> (name, sector). liquidity_sector.csv + kosdaq_industry.csv 병합."""
    name, sector = {}, {}
    specs = [("liquidity_sector.csv", ["code", "name", "sector"]),
             ("kosdaq_industry.csv",  ["code", "name", "sector"])]
    for f, cols in specs:
        p = os.path.join(BASE, f)
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
        df.columns = [c.lstrip("﻿") for c in df.columns]
        for _, r in df[cols].dropna(subset=["code"]).iterrows():
            c = str(r["code"]).zfill(6)
            name.setdefault(c, r.get("name"))
            if pd.notna(r.get("sector")):
                sector.setdefault(c, r["sector"])
    return name, sector


def sector_universe(sector_map):
    """섹터 키워드 매칭 종목 집합."""
    return {c for c, s in sector_map.items()
            if isinstance(s, str) and any(k in s for k in SECTOR_KW)}


def _read_recent_csv(pd, path, n_rows, usecols):
    """파일 끝에서 최근 n_rows행만 읽는다(전체를 안 읽어 빠름).
    일봉이 날짜 오름차순 → 끝부분 = 최근. 헤더는 첫 줄에서 보존."""
    import io
    with open(path, "rb") as f:
        header = f.readline()
        f.seek(0, 2); pos = f.tell()
        data = b""; block = 1 << 20; nl = 0
        while pos > 0 and nl <= n_rows:
            step = min(block, pos); pos -= step
            f.seek(pos); data = f.read(step) + data
            nl = data.count(b"\n")
    lines = [ln for ln in data.split(b"\n") if ln.strip()]
    tail = lines[-n_rows:] if len(lines) > n_rows else lines
    buf = header + b"\n".join(tail)
    return pd.read_csv(io.BytesIO(buf), usecols=usecols,
                       dtype={"code": str}, encoding="utf-8-sig")


def load_daily_features(pd, np, candidates=None, recent=None):
    """code -> {date, close, vol60, adv20, atr14}. 마지막 관측 기준.
    candidates(set) 주면 그 코드만 계산(성능). recent(int)이면 일봉 끝 N행만."""
    frames = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{m}.csv")
        if not os.path.exists(p):
            print(f"  [없음] {os.path.basename(p)}"); continue
        cols = ["date", "code", "high", "low", "close", "volume"]
        if recent:
            d = _read_recent_csv(pd, p, recent, cols)
        else:
            d = pd.read_csv(p, usecols=cols, dtype={"code": str}, encoding="utf-8-sig")
        d["code"] = d["code"].str.zfill(6)
        if candidates is not None:
            d = d[d["code"].isin(candidates)]
        frames.append(d)
    if not frames:
        return None
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["date", "close"])
    d = d[d["close"] > 0].sort_values(["code", "date"])
    g = d.groupby("code", sort=False)
    d["ret"] = g["close"].pct_change()
    d["val"] = d["close"] * d["volume"]
    d["vol60"] = g["ret"].transform(lambda s: s.rolling(60, min_periods=40).std())
    d["adv20"] = g["val"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    # ATR14 (매도규칙서 §1 / jq_discover atr() 동일): TR = max(H-L, |H-pc|, |L-pc|)
    pc = g["close"].shift(1)
    hi = d["high"].where(d["high"] > 0, d["close"])
    lo = d["low"].where(d["low"] > 0, d["close"])
    tr = pd.concat([hi - lo, (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.groupby(d["code"], sort=False).transform(
        lambda s: s.rolling(ATR_N).mean())
    last = d.groupby("code", sort=False).tail(1)
    feat = {r.code: {"date": r.date, "close": r.close, "vol60": r.vol60,
                     "adv20": r.adv20, "atr14": r.atr14}
            for r in last.itertuples()}
    return feat, d["date"].max()


def load_pbr(pd):
    """code -> 최신 PBR(>0)."""
    frames = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목재무_KRX_{m}.csv")
        if not os.path.exists(p):
            continue
        df = pd.read_csv(p, usecols=["date", "code", "PBR"],
                         dtype={"code": str}, encoding="utf-8-sig")
        frames.append(df)
    if not frames:
        return {}
    d = pd.concat(frames, ignore_index=True)
    d["code"] = d["code"].str.zfill(6)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["PBR"] = pd.to_numeric(d["PBR"], errors="coerce")
    d = d.dropna(subset=["date", "PBR"])
    d = d[d["PBR"] > 0].sort_values(["code", "date"])
    last = d.groupby("code").tail(1)
    return dict(zip(last["code"], last["PBR"]))


def load_mcap(pd):
    """code -> 최신 시총."""
    p = os.path.join(BASE, "종목시총_30년.csv")
    if not os.path.exists(p):
        return {}
    d = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
    d.columns = [c.lstrip("﻿") for c in d.columns]
    d["code"] = d["code"].str.zfill(6)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["mcap"] = pd.to_numeric(d["mcap"], errors="coerce")
    d = d.dropna(subset=["date", "mcap"]).sort_values(["code", "date"])
    last = d.groupby("code").tail(1)
    return dict(zip(last["code"], last["mcap"]))


# ── 시장 regime (추세 낙폭방어 레버 — 검증: 하락장마다 낙폭 반토막) ──
def market_regime(pd):
    """KOSPI 종가 vs MA200 → (regime, 이격%). 진입맥락(신호 아님)."""
    p = os.path.join(BASE, "kospi_index_daily.csv")
    if not os.path.exists(p):
        return "N/A", None
    try:
        d = pd.read_csv(p, encoding="utf-8-sig")
        d.columns = [c.lstrip("\ufeff").lower() for c in d.columns]
        d["close"] = pd.to_numeric(d["close"], errors="coerce")
        d = d.dropna(subset=["close"])
        ma = d["close"].rolling(200).mean().iloc[-1]; cl = d["close"].iloc[-1]
        if ma != ma:
            return "N/A", None
        gap = cl/ma - 1
        reg = "NEUTRAL" if abs(gap) < 0.02 else ("RISK_ON" if gap > 0 else "RISK_OFF")
        return reg, round(gap*100, 1)
    except Exception:
        return "N/A", None


# ── 하순 플래그 ──────────────────────────────────────────────────
def late_month_flag(np, today=None):
    """월말 잔여 거래일(영업일)이 5~9일 구간이면 True(신규진입 보류 권고)."""
    today = today or date.today()
    y, m = today.year, today.month
    nm = date(y + (m == 12), 1 if m == 12 else m + 1, 1)  # 다음달 1일
    rem = int(np.busday_count(today.isoformat(), nm.isoformat()))  # today~월말 영업일 수
    return (5 <= rem <= 9), rem


# ── 랭킹 ─────────────────────────────────────────────────────────
def build_ranking(pd, np, name, sector_map, feat, pbr, mcap, args):
    su = sector_universe(sector_map)

    # 특성기반: 초고변동 + 고PBR + 중대형
    char = set()
    for c, fv in feat.items():
        v = fv["vol60"]; p = pbr.get(c); mc = mcap.get(c)
        if v is not None and not pd.isna(v) and v > args.vol_hi \
           and p is not None and p > args.pbr_hi \
           and mc is not None and mc >= args.cap_floor:
            char.add(c)

    union = su | char
    rows = []
    for c in union:
        fv = feat.get(c)
        if not fv:
            continue
        close, vol60, adv20 = fv["close"], fv["vol60"], fv["adv20"]
        p = pbr.get(c)
        # 거래필터 + 랭킹에 필요한 값 존재
        if close is None or close < MIN_PRICE:
            continue
        if adv20 is None or pd.isna(adv20) or adv20 < MIN_ADV:
            continue
        if p is None or vol60 is None or pd.isna(vol60):
            continue
        if c in su and c in char:
            src = "섹터+특성"
        elif c in su:
            src = "섹터"
        else:
            src = "특성"
        rows.append({"code": c, "name": name.get(c, c),
                     "sector": sector_map.get(c, "-"),
                     "close": float(close), "pbr": float(p),
                     "vol60": float(vol60), "adv20": float(adv20),
                     "atr14": fv.get("atr14"),
                     "mcap": mcap.get(c, np.nan), "src": src})
    if not rows:
        return None
    df = pd.DataFrame(rows)

    # 사냥터내 percentile (낮을수록 좋음 → 1-pct)
    df["pbr_pct"] = df["pbr"].rank(pct=True)          # 낮은 PBR = 낮은 pct
    df["vol_pct"] = df["vol60"].rank(pct=True)
    df["s_pbr"] = 1.0 - df["pbr_pct"]                 # 저PBR일수록 큼
    df["s_vol"] = 1.0 - df["vol_pct"]
    df["score"] = args.w_pbr * df["s_pbr"] + args.w_vol * df["s_vol"]
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    n = len(df)
    df["pbr_rank"] = df["pbr"].rank(method="min").astype(int)    # 1=제일 쌈
    df["vol_rank"] = df["vol60"].rank(method="min").astype(int)  # 1=제일 안정
    df["n_univ"] = n

    # 스톱 & 수량 = 매도규칙서 v2 §1·§3 (jq_discover 동일)
    atr = pd.to_numeric(df["atr14"], errors="coerce")
    atr_stop = df["close"] - ATR_K * atr
    floor_stop = df["close"] * (1 - STOP_CAP)
    df["stop"] = np.where(atr.notna(), np.maximum(atr_stop, floor_stop),
                          floor_stop).round().astype(int)
    one_r = (df["close"] - df["stop"]).clip(lower=1)
    df["stop_pct"] = (one_r / df["close"] * 100).round(1)     # 손절폭%
    df["qty"] = np.floor((args.capital * args.risk / 100.0) / one_r).astype(int)
    df["is_jinwoo6"] = df["code"].isin(JINWOO6)
    return df


# ── 출력 ─────────────────────────────────────────────────────────
def render(pd, np, df, args, data_date, late, rem):
    n = len(df)
    print("\n" + "=" * 78)
    print("진우 사냥터 발굴 — 사냥터내 저PBR·저변동 기울기 랭킹")
    print(f"데이터일: {str(data_date)[:10]} · 유니버스 {n}종목 · "
          f"가중 저PBR {args.w_pbr}/저변동 {args.w_vol}")
    print(f"자본 {args.capital:,.0f}원 · 리스크 {args.risk}%/건 · "
          f"손절=max(현재가-2.5·ATR14, 현재가×0.80) · 트레일=(최고가-2.5·ATR14) 래칫")
    print("매도규칙서 v2: 섹터당 최대 2종 · 동시 5~7종 · 돌파(추격)는 리스크 0.5%·발굴참고용")
    flag = "[!] 하순(신규진입 보류 권고)" if late else "정상"
    print(f"하순 플래그: {flag}  (월말 잔여 영업일 {rem}일)")
    reg, gap = market_regime(pd)
    gap_s = f"{gap:+.1f}%" if gap is not None else "N/A"
    print(f"시장 regime(KOSPI vs MA200): {reg} ({gap_s})  — 추세 규율=하락장 낙폭방어 레버(검증)")
    print("=" * 78)

    top = df.head(args.top)
    hdr = f"{'순':>3} {'코드':>6} {'종목':<10} {'점수':>5} " \
          f"{'PBR':>6}({'순':>3}) {'변동%':>5}({'순':>3}) " \
          f"{'현재가':>8} {'손절':>7}({'폭%':>4}) {'수량':>5} {'출처':<7}"
    print(hdr)
    print("-" * 92)
    for r in top.itertuples():
        mark = "*" if r.is_jinwoo6 else " "
        nm = (r.name or r.code)[:10]
        print(f"{mark}{r.rank:>2} {r.code:>6} {nm:<10} {r.score:>5.2f} "
              f"{r.pbr:>6.2f}({r.pbr_rank:>3}) {r.vol60*100:>5.1f}({r.vol_rank:>3}) "
              f"{r.close:>8,.0f} {r.stop:>7,.0f}({r.stop_pct:>4.1f}) {r.qty:>5,d} {r.src:<7}")

    # 진우 6종목 위치
    print("\n[진우 6종목 랭킹 위치] *=6종목")
    j = df[df["is_jinwoo6"]].sort_values("rank")
    if len(j):
        for r in j.itertuples():
            print(f"  {r.rank:>3}/{n}  {r.code} {r.name:<10} "
                  f"PBR {r.pbr:>6.2f}(#{r.pbr_rank}) · 변동 {r.vol60*100:>4.1f}%(#{r.vol_rank}) "
                  f"· 점수 {r.score:.2f}")
    missing = [f"{c}({nm})" for c, nm in JINWOO6.items()
               if c not in set(df["code"])]
    if missing:
        print(f"  [유니버스 밖] {', '.join(missing)}")

    # CSV
    cols = ["rank", "code", "name", "sector", "src", "score", "pbr", "pbr_rank",
            "vol60", "vol_rank", "close", "mcap", "adv20", "atr14",
            "stop", "stop_pct", "qty", "n_univ", "is_jinwoo6"]
    outp = os.path.join(BASE, "진우사냥터_후보.csv")
    df[cols].to_csv(outp, index=False, encoding="utf-8-sig")
    print(f"\n저장: 진우사냥터_후보.csv ({n}행)")
    print("※ 발굴 != 매수신호. 스톱은 타협 불가. 기울기는 조건부(2028 재판정).")


# ── 셀프테스트 ───────────────────────────────────────────────────
def _self_test():
    import numpy as np, pandas as pd
    ok = tot = 0

    def chk(nm, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {nm}")

    # 1) 섹터 키워드 매칭
    sm = {"001": "반도체 제조업", "002": "음식점업",
          "003": "전자부품 제조업", "004": "기타 금융업"}
    su = sector_universe(sm)
    chk("섹터 매칭: 반도체·전자부품 포함, 음식점·금융 제외", su == {"001", "003"})

    args = argparse.Namespace(vol_hi=0.04, pbr_hi=2.0, cap_floor=3e11,
                              w_pbr=0.65, w_vol=0.35, capital=1e7, risk=1.0, top=30)

    # 2) 특성기반이 금융 오분류 성장주(에코프로형) 포착
    feat = {"004": {"date": pd.Timestamp("2026-07-13"), "close": 100000.0,
                    "vol60": 0.06, "adv20": 1e10, "atr14": 5000.0}}
    df = build_ranking(pd, np, {"004": "에코프로형"}, {"004": "기타 금융업"},
                       feat, {"004": 7.3}, {"004": 1e13}, args)
    chk("특성기반: 금융 오분류 성장주 포착", df is not None and "004" in set(df["code"]))
    chk("출처 라벨=특성", df is not None and df.iloc[0]["src"] == "특성")

    # 3) 랭킹: 저PBR이 위로
    name = {f"{i:03d}": f"n{i}" for i in range(20)}
    sm = {f"{i:03d}": "반도체 제조업" for i in range(20)}
    feat, pbr, mcap = {}, {}, {}
    for i in range(20):
        c = f"{i:03d}"
        feat[c] = {"date": pd.Timestamp("2026-07-13"), "close": 5000.0,
                   "vol60": 0.05, "adv20": 1e9, "atr14": 250.0}
        pbr[c] = 1.0 + i          # 000이 제일 쌈
        mcap[c] = 1e12
    df = build_ranking(pd, np, name, sm, feat, pbr, mcap, args)
    chk("저PBR(000)이 1위", df.iloc[0]["code"] == "000")
    chk("고PBR(019)이 최하위", df.iloc[-1]["code"] == "019")

    # 4) 가중: PBR 0.65 → 저PBR극단이 저변동극단보다 상위
    feat2, pbr2, mcap2, sm2, nm2 = {}, {}, {}, {}, {}
    for i in range(10):
        c = f"{i:03d}"
        nm2[c] = c; sm2[c] = "반도체 제조업"
        feat2[c] = {"date": pd.Timestamp("2026-07-13"), "close": 5000.0,
                    "vol60": 0.02 + i * 0.001, "adv20": 1e9, "atr14": 250.0}
        pbr2[c] = 10.0 - i * 0.5  # 000이 제일 비쌈·변동 최저, 009 저PBR·변동 최고
        mcap2[c] = 1e12
    df2 = build_ranking(pd, np, nm2, sm2, feat2, pbr2, mcap2, args)
    s009 = df2[df2["code"] == "009"]["score"].iloc[0]
    s000 = df2[df2["code"] == "000"]["score"].iloc[0]
    chk("PBR 가중 0.65 → 저PBR극단 > 저변동극단", s009 > s000)

    # 5) ATR 손절 = max(close-2.5·ATR, close×0.80), 수량 = (자본×리스크)/1R
    #    close=10000, atr14=800 → atr_stop=8000, floor=8000 → stop 8000, R 2000, qty 50
    df3 = build_ranking(pd, np, {"001": "x"}, {"001": "반도체 제조업"},
                        {"001": {"date": pd.Timestamp("2026-07-13"), "close": 10000.0,
                                 "vol60": 0.05, "adv20": 1e9, "atr14": 800.0}},
                        {"001": 5.0}, {"001": 1e12}, args)
    chk("ATR 손절 = 8000", int(df3.iloc[0]["stop"]) == 8000)
    chk("리스크 기반 수량 = 50", int(df3.iloc[0]["qty"]) == 50)
    # 5b) 저ATR이면 2.5·ATR가 floor보다 얕음: close=10000, atr14=200 → atr_stop=9500 > floor 8000
    df3b = build_ranking(pd, np, {"001": "x"}, {"001": "반도체 제조업"},
                         {"001": {"date": pd.Timestamp("2026-07-13"), "close": 10000.0,
                                  "vol60": 0.05, "adv20": 1e9, "atr14": 200.0}},
                         {"001": 5.0}, {"001": 1e12}, args)
    chk("저ATR 손절 = 9500(2.5·ATR 우선)", int(df3b.iloc[0]["stop"]) == 9500)

    # 6) 하순 플래그
    late, rem = late_month_flag(np, date(2026, 7, 24))
    chk("하순 플래그 함수 동작(bool/int)", isinstance(late, bool) and isinstance(rem, int))

    # 7) 거래필터: 저가/저유동 제거
    df4 = build_ranking(pd, np, {"001": "x", "002": "y"},
                        {"001": "반도체 제조업", "002": "반도체 제조업"},
                        {"001": {"date": pd.Timestamp("2026-07-13"), "close": 500.0,
                                 "vol60": 0.05, "adv20": 1e9, "atr14": 25.0},
                         "002": {"date": pd.Timestamp("2026-07-13"), "close": 5000.0,
                                 "vol60": 0.05, "adv20": 1e6, "atr14": 250.0}},
                        {"001": 3.0, "002": 3.0}, {"001": 1e12, "002": 1e12}, args)
    chk("거래필터: 저가(500)·저유동 모두 제거", df4 is None)

    # 8) 최근행 리더: 파일 끝 N행만 정확히 읽는가
    import tempfile as _tf
    tp = os.path.join(_tf.mkdtemp(), "d.csv")
    with open(tp, "w", encoding="utf-8-sig") as _f:
        _f.write("date,code,high,low,close,volume\n")
        for i in range(100):
            _f.write(f"2026-01-{(i%28)+1:02d},{i%3:06d},{10+i},{9+i},{10+i},100\n")
    rc = _read_recent_csv(pd, tp, 10, ["date", "code", "high", "low", "close", "volume"])
    chk("최근행 리더: 끝 10행·마지막 close=109",
        len(rc) == 10 and int(rc.iloc[-1]["close"]) == 109)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


# ── 메인 ─────────────────────────────────────────────────────────
def run(args):
    import pandas as pd, numpy as np
    print("데이터 적재...")
    name, sector_map = load_maps(pd)
    print(f"  이름/섹터 맵: {len(name)}종목")
    pbr = load_pbr(pd);  print(f"  PBR: {len(pbr)}종목")
    mcap = load_mcap(pd); print(f"  시총: {len(mcap)}종목")

    su = sector_universe(sector_map)
    char_pre = {c for c in mcap
                if mcap.get(c, 0) >= args.cap_floor and pbr.get(c, 0) > args.pbr_hi}
    candidates = su | char_pre | set(JINWOO6)
    print(f"  후보: 섹터 {len(su)} ∪ 특성후보 {len(char_pre)} → {len(candidates)}종목 일봉만 계산")
    recent = RECENT_ROWS if getattr(args, "recent", False) else None
    if recent:
        print(f"  [고속 모드] 일봉 끝 {recent:,}행만 읽음(최근 ~300거래일, 전체와 동일 결과)")
    res = load_daily_features(pd, np, candidates, recent=recent)
    if res is None:
        print("  [중단] 일봉 데이터 없음"); return 2
    feat, data_date = res
    print(f"  일봉 특징: {len(feat)}종목 · 최신 {str(data_date)[:10]}")

    df = build_ranking(pd, np, name, sector_map, feat, pbr, mcap, args)
    if df is None:
        print("  [중단] 유니버스 비어있음"); return 2
    late, rem = late_month_flag(np)
    render(pd, np, df, args, data_date, late, rem)
    return 0


def main():
    ap = argparse.ArgumentParser(description="jinwoo hunting-ground screener")
    ap.add_argument("--capital", type=float, default=10_000_000, help="capital KRW")
    ap.add_argument("--risk", type=float, default=1.0, help="risk pct per trade")
    ap.add_argument("--top", type=int, default=30, help="console top N")
    ap.add_argument("--w-pbr", type=float, default=W_PBR, dest="w_pbr")
    ap.add_argument("--w-vol", type=float, default=W_VOL, dest="w_vol")
    ap.add_argument("--vol-hi", type=float, default=VOL_HI, dest="vol_hi")
    ap.add_argument("--pbr-hi", type=float, default=PBR_HI, dest="pbr_hi")
    ap.add_argument("--cap-floor", type=float, default=CAP_FLOOR, dest="cap_floor")
    ap.add_argument("--recent", action="store_true",
                    help="고속 모드: 일봉 끝부분만 읽음(스케줄/자동 실행용)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
