#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""관심종목_상태.py — 내 종목·관심종목 '지금 타점 형성됐나' 상태표 (PC 실행)

발굴툴이 스캔 전체를 훑는다면, 이건 **내가 지정한 종목만** 콕 집어 현재 기술 상태를 본다.
질문: "테크윙·주성 지금 진입 타점이야?" → 추세·신고가 근접·자금유입·변동성·PBR로 한눈에.

⚠️ 발굴 ≠ 매수신호. 상태 확인일 뿐, 매수 판단·책임은 진우.

입력: my_holdings.csv(보유) + 아래 WATCH(관심). kospi_pit_daily.csv/kosdaq_pit_daily.csv,
      종목재무_KRX_*.csv. (발굴데이터_갱신.py를 먼저 돌려 최신화할 것)
사용: py 관심종목_상태.py            /  py 관심종목_상태.py --self-test
      py 관심종목_상태.py --add 005930,000660   (임시 추가)
"""
import os, sys, argparse
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

WATCH = {"089030": "테크윙", "036930": "주성엔지니어링"}   # 진우 관심(보유 밖)


def load_names():
    out = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            d = pd.read_csv(p, dtype={"code": str})
            for _, r in d.iterrows():
                out.setdefault(str(r["code"]).zfill(6), r.get("name"))
    return out


def load_pbr():
    out = {}
    for f in ("종목재무_KRX_KOSPI.csv", "종목재무_KRX_KOSDAQ.csv"):
        p = os.path.join(HERE, f)
        if not os.path.exists(p): continue
        d = pd.read_csv(p, dtype={"code": str}, usecols=["date", "code", "PBR"], encoding="utf-8-sig")
        d["PBR"] = pd.to_numeric(d["PBR"], errors="coerce")
        d = d[d["PBR"] > 0].dropna().sort_values("date").groupby("code").tail(1)
        for _, r in d.iterrows(): out[str(r["code"]).zfill(6)] = float(r["PBR"])
    return out


def load_daily(codes):
    frames = []
    for f in ("kospi_pit_daily.csv", "kosdaq_pit_daily.csv"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            d = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
            d = d[d["code"].isin(codes)]
            if len(d): frames.append(d)
    if not frames: return None
    return pd.concat(frames, ignore_index=True)


def posture(g, pbr):
    """한 종목의 현재 기술 상태 dict. g=일봉(정렬 전)."""
    g = g.sort_values("date")
    if len(g) < 210:
        return {"note": f"데이터 {len(g)}일(<210) — 판정보류"}
    close = g["close"].iloc[-1]
    ma200 = g["close"].rolling(200).mean().iloc[-1]
    hi52 = g["close"].tail(250).max()
    ret = g["close"].pct_change()
    vol60 = ret.tail(60).std() * 100
    val20 = (g["close"] * g["volume"]).rolling(20).mean().iloc[-1]
    val60 = (g["close"] * g["volume"]).rolling(60).mean().iloc[-1]
    infl = val20 / val60 if val60 > 0 else np.nan
    rs3m = close / g["close"].iloc[-60] - 1 if len(g) > 60 else np.nan
    near_high = bool(close >= hi52 * 0.95)
    uptrend = bool(close > ma200)
    inflow = bool(pd.notna(infl) and infl > 1.2)
    # 돌파 타점 근접 = 상승추세 + 신고가부근 + 자금유입
    setup = bool(uptrend and near_high and inflow)
    return {"date": g["date"].iloc[-1], "close": close, "trend": close / ma200,
            "hi_pct": close / hi52 * 100, "vol60": vol60, "pbr": pbr,
            "infl": infl, "rs3m": rs3m * 100 if pd.notna(rs3m) else np.nan,
            "uptrend": uptrend, "near_high": near_high, "inflow": inflow, "setup": setup}


def read_holdings():
    p = os.path.join(HERE, "my_holdings.csv")
    codes = {}
    if os.path.exists(p):
        for line in open(p, encoding="utf-8-sig"):
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("code"):
                continue
            parts = line.split(",")
            if parts and parts[0].isdigit():
                codes[parts[0].zfill(6)] = parts[1] if len(parts) > 1 else parts[0]
    return codes


def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    n = 260
    up = pd.DataFrame({"date": [f"d{i:03d}" for i in range(n)], "code": "T",
                       "open": 1, "high": 1, "low": 1,
                       "close": np.linspace(100, 200, n), "volume": 1000})
    st = posture(up, 1.0)
    chk("상승추세 종목 uptrend=True", st["uptrend"] is True)
    chk("꾸준상승 → 신고가 부근", st["near_high"] is True)
    down = up.copy(); down["close"] = np.linspace(200, 100, n)
    sd = posture(down, 1.0)
    chk("하락추세 uptrend=False", sd["uptrend"] is False)
    chk("하락 → 신고가 아님", sd["near_high"] is False)
    short = up.head(100)
    chk("데이터<210 판정보류", "note" in posture(short, 1.0))
    chk("setup=추세+신고가+유입 3조건", "setup" in st)
    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", default="", help="임시 추가 코드(쉼표)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1

    names = load_names(); pbr = load_pbr()
    hold = read_holdings()
    watch = dict(WATCH)
    for c in [x.strip() for x in a.add.split(",") if x.strip()]:
        watch[c.zfill(6)] = names.get(c.zfill(6), c)
    universe = {**{k: (names.get(k) or v) for k, v in hold.items()},
                **{k: (names.get(k) or v) for k, v in watch.items()}}
    tag = {**{k: "보유" for k in hold}, **{k: "관심" for k in watch if k not in hold}}

    daily = load_daily(set(universe))
    print("=" * 78)
    print("관심종목 상태 — 지금 타점 형성됐나  (발굴 ≠ 매수신호 · 판단·책임 본인)")
    print("=" * 78)
    if daily is None:
        print("일봉 없음 — 발굴데이터_갱신.py 먼저 실행"); return 1
    asof = daily["date"].max()
    print(f"기준일 {asof} · 추세=종가/MA200(>1 상승) · 신고가%=52주최고 대비 · 유입=20/60일거래대금\n")
    hdr = f"{'구분':<5}{'종목':<12}{'현재가':>9}{'추세':>6}{'신고가%':>8}{'변동60':>7}{'PBR':>7}{'유입':>6}{'RS3M':>8}  신호"
    print(hdr); print("-" * len(hdr))
    rows = []
    for code, nm in universe.items():
        sub = daily[daily["code"] == code]
        if not len(sub):
            print(f"{tag.get(code,''):<5}{nm:<12}{'— 유니버스에 없음(상폐/미상장?)':<40}"); continue
        st = posture(sub, pbr.get(code))
        if "note" in st:
            print(f"{tag.get(code,''):<5}{nm:<12}{st['note']}"); continue
        sig = ("🟢돌파근접" if st["setup"] else
               ("↑추세" if st["uptrend"] else "↓추세이탈"))
        pbs = f"{st['pbr']:.2f}" if st["pbr"] is not None and pd.notna(st["pbr"]) else "—"
        print(f"{tag.get(code,''):<5}{nm:<12}{round(st['close']):>9,}{st['trend']:>6.2f}"
              f"{st['hi_pct']:>8.1f}{st['vol60']:>7.1f}{pbs:>7}{st['infl']:>6.2f}"
              f"{st['rs3m']:>+8.1f}  {sig}")
        rows.append((nm, st))
    print("\n🟢돌파근접 = 상승추세 + 신고가 95%내 + 자금유입(20/60>1.2) 동시. "
          "없으면 지금 깔끔한 돌파 타점은 미형성.")
    print("발굴 ≠ 매수신호. 추격 금지 · 진입 시 손절 동시설정 · 결정·책임 본인.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
