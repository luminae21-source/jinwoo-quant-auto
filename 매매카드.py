# -*- coding: utf-8 -*-
r"""매매카드.py — 진입 자리 · 청산 자리 (2026-07-30 신설)

딱 두 가지만 답한다:
   ① 어디서 살 것인가 (분할 진입가 3단)
   ② 어디서 팔 것인가 (손절가 · 익절가)

[진입 자리 — 3분할]
  1차 = 현재가        (지금 사는 몫)
  2차 = 현재가 − 1.5×ATR
  3차 = 현재가 − 3.0×ATR
  ※ 분할은 **알파가 아니라 규율**이다. "한 번에 다 사고 틀리는" 비용을 줄이는 것.
     2·3차가 안 오면 1차만 들고 간다 — 안 온 것도 결과다.

[청산 자리]
  가치 트랙  손절 = 평균진입 × 0.60           (재난 백스톱 −40% · 인내형)
            익절 = min( PBR 1.0 도달가 , 평균진입 × 2.0 )
                   PBR 1.0 도달가 = 현재가 × (1.0 ÷ 현재PBR)   ← 장부가만큼 값을 인정받는 지점
  성장 트랙  손절 = 고점 × 0.85               (트레일 −15% · 고점 갱신 시 따라 올림)
            익절 = 없음. 트레일이 대신한다 (이긴 종목을 오래 태우는 게 이 트랙의 전부)

  근거: 매도규칙 v3 정본 · 청산규칙_규칙서(소중형 트레일−15% 1순위, 파국 13분의 1)

사용: py 매매카드.py --pool 본체 --capital 10000000            (본체 top10 · 동일가중)
      py 매매카드.py --code 000660,353200 --track 성장 --capital 10000000
                                                        (재량 트랙 · 아는 종목 · 트레일 -15%)
      py 매매카드.py --pool 본체 --capital 10000000 --topn 30   (검정 사양에 더 가까움)
      py 매매카드.py --capital 10000000                          (재량 트랙 · 위험1% 사이징)
      py 매매카드.py --capital 10000000 --code 024110,036460

[사이징 두 갈래]
  --pool 본체 : 월간 포트 = 동일가중 1/N · 종목캡 15% · 방어 ON이면 절반
                ※ 검정된 사양은 **top30 동일가중**이다. --topn 10은 그 부분집합이며
                  따로 검정되지 않았다(집중 위험). 자본이 허락하면 --topn 30 을 쓸 것.
  그 외        : 재량 트랙 = 위험 1%/건 · Σheat 6% (진우_통합한도.json)
⚠️ 기계적 산출 · 매수/매도 추천 아님 · 투자자문 아님 · 결정과 책임은 본인.
"""
import os, sys, argparse, datetime, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

RISK_PCT, HEAT_CAP, STOCK_CAP = 0.01, 0.06, 0.15
SECTOR_CAP = 0.35                                   # 진우_통합한도.json · 본체_월간포트
MAX_LADDER_DD = 0.25                                # 진입 사다리 최심 −25% 제한
VALUE_STOP, TRAIL_STOP = 0.40, 0.15
NEW_LISTING_M = 36
NEAR_HIGH, VOL_MULT, WICK_MIN, BODY_SMALL = 0.90, 2.0, 0.03, 0.02
PX_FLOOR, AMT_FLOOR = 1000, 10e8
SPLIT = [(0.0, 0.34), (1.5, 0.33), (3.0, 0.33)]     # (ATR배수 하락, 배분비율)


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def load():
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        p = _find(f"_일봉OHLCV_{m}_adj.csv")
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["mkt"] = m; fr.append(d)
    if not fr: sys.exit("❌ _일봉OHLCV_*_adj.csv 없음")
    D = pd.concat(fr, ignore_index=True); D["code"] = D["code"].str.zfill(6)
    amax = D["date"].max(); add = []
    for m in ("KOSPI", "KOSDAQ"):
        rp = _find(f"종목일봉_30년_{m}.csv")
        if not rp: continue
        try: raw = pd.read_csv(rp, dtype={"code": str})
        except Exception: continue
        if not {"date","code","open","high","low","close","volume"}.issubset(raw.columns): continue
        raw = raw[raw["date"] > amax]
        if len(raw):
            raw = raw.copy(); raw["code"] = raw["code"].astype(str).str.zfill(6); raw["mkt"] = m
            add.append(raw[["code","date","open","high","low","close","volume","mkt"]])
    if add: D = pd.concat([D] + add, ignore_index=True)
    return D.drop_duplicates(["code","date"], keep="last").sort_values(["code","date"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=10_000_000)
    ap.add_argument("--code", default=None)
    ap.add_argument("--pool", default=None,
                    help="본체 = 본체_선정.csv(검정 통과 코어 엔진) / 주도주 = 주도주_풀.csv(워치리스트·검정 기각)")
    ap.add_argument("--track", choices=["가치", "성장"], default=None,
                    help="트랙 강제. 기본은 시총 300위 안=가치. 하이닉스·대덕전자처럼 "
                         "대형이지만 성장·사이클로 다룰 종목은 --track 성장 (트레일 -15%%)")
    ap.add_argument("--force", action="store_true",
                    help="--code 로 지정한 종목의 위생 필터(60일선·거래대금)를 무시하고 카드 생성")
    ap.add_argument("--topn", type=int, default=None,
                    help="카드 장수 (기본: 재량 6 · --pool 본체 10)")
    a = ap.parse_args()
    if a.topn is None: a.topn = 10 if a.pool == "본체" else 6
    pool_order = []

    if a.pool and not a.code:
        pf = {"본체": "본체_선정.csv", "주도주": "주도주_풀.csv"}.get(a.pool, a.pool)
        pp = _find(pf)
        if not pp: sys.exit(f"❌ {pf} 없음 — 먼저 본체_이번달.py 실행")
        pdf = pd.read_csv(pp, dtype={"code": str})
        pool_order = pdf["code"].str.zfill(6).tolist()      # 풀이 정한 순위 = 그대로 쓴다
        a.code = ",".join(pool_order)
        print(f"  풀 = {pf} ({len(pdf)}종목) · 순위는 풀 순서를 따른다")
        if a.pool == "주도주":
            print("  ⚠️ 주도주 풀은 사전등록 검정에서 **기각**됐다(12m −4.58%, 36m −30.56%).")
            print("     매수 후보가 아니라 워치리스트다. 카드는 참고용으로만.")

    D = load(); last = D["date"].max()
    g = D.groupby("code")
    D["hi252"] = g["high"].transform(lambda s: s.rolling(252, min_periods=120).max())
    D["volma"] = g["volume"].transform(lambda s: s.rolling(60, min_periods=40).mean())
    D["ma60"]  = g["close"].transform(lambda s: s.rolling(60, min_periods=40).mean())
    tr = pd.concat([D["high"] - D["low"],
                    (D["high"] - g["close"].shift()).abs(),
                    (D["low"] - g["close"].shift()).abs()], axis=1).max(axis=1)
    D["atr"] = tr.groupby(D["code"]).transform(lambda s: s.rolling(20, min_periods=15).mean())
    D["body"] = D["close"]/D["open"] - 1
    D["wick"] = (D["high"] - D[["open","close"]].max(axis=1)) / D["high"]
    D["amt"]  = D["close"] * D["volume"]
    D["nearhi"] = (D["close"] >= D["hi252"]*NEAR_HIGH) & (D["close"]>=PX_FLOOR) & (D["amt"]>=AMT_FLOOR)
    D["sig"] = D["nearhi"] & (D["volume"]>=D["volma"]*VOL_MULT) & (D["wick"]>=WICK_MIN) & (D["body"]<=BODY_SMALL)
    D["sig10"] = g["sig"].transform(lambda s: s.rolling(10, min_periods=1).sum())
    # 종목마다 마지막 거래일이 다를 수 있다(거래정지·시장별 수집 시차).
    # 전체 max 날짜로 자르면 그 종목이 통째로 사라진다 → 종목별 마지막 행을 쓴다.
    cur = D.sort_values("date").groupby("code").tail(1).set_index("code")
    cur_date = D.sort_values("date").groupby("code")["date"].last()
    hi20 = D.groupby("code")["high"].apply(lambda s: s.tail(20).max())

    first = D.groupby("code")["date"].min()
    age = ((pd.Timestamp(last) - pd.to_datetime(first)).dt.days / 30.44)

    fins = []
    for m in ("KOSPI","KOSDAQ"):
        p = _find(f"종목재무_KRX_{m}.csv")
        if p: fins.append(pd.read_csv(p, dtype={"code":str}, usecols=["date","code","PBR","BPS","EPS","DIV"]))
    if not fins: sys.exit("❌ 종목재무_KRX_*.csv 없음")
    F = pd.concat(fins); F["code"] = F["code"].str.zfill(6)
    for c in ("PBR","BPS","EPS","DIV"): F[c] = pd.to_numeric(F[c], errors="coerce")
    F = F.sort_values("date").groupby("code").tail(1).set_index("code")
    F["roe"] = np.where(F["BPS"]>0, F["EPS"]/F["BPS"], np.nan)

    MC = pd.Series(dtype=float)
    mp = _find("종목시총_30년.csv")
    if mp:
        mc = pd.read_csv(mp, dtype={"code":str}); mc.columns=[c.strip().lstrip("﻿") for c in mc.columns]
        mc["code"]=mc["code"].str.zfill(6)
        MC = pd.to_numeric(mc.sort_values("date").groupby("code")["mcap"].last(), errors="coerce")
    rank = MC.rank(ascending=False) if len(MC) else pd.Series(dtype=float)

    NAME = os.path.join(HERE, "종목명_맵.csv"); names = {}
    if os.path.exists(NAME):
        try:
            nm = pd.read_csv(NAME, dtype=str); names = dict(zip(nm.iloc[:,0].str.zfill(6), nm.iloc[:,1]))
        except Exception: pass

    defense = False; idx_note = ""
    ip = _find("kospi_index_daily.csv")
    if ip:
        ix = pd.read_csv(ip); ix["ym"] = pd.to_datetime(ix["Date"]).dt.strftime("%Y-%m")
        im = ix.groupby("ym")["Close"].last(); ma10 = im.rolling(10).mean(); ym = im.index[-1]
        defense = bool(pd.notna(ma10[ym]) and im[ym] < ma10[ym])
        idx_note = f"KOSPI {im[ym]:,.0f} vs 10MA {ma10[ym]:,.0f} → {'🔴방어ON(투입 절반)' if defense else '🟢방어OFF'}"

    # ── 섹터 (진우_통합한도.json 본체_월간포트 sector_cap_pct 35 적용용)
    SEC = {}
    for fn in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        sp = _find(fn)
        if not sp: continue
        try:
            sd = pd.read_csv(sp, dtype=str); sd.columns = [c.strip().lstrip("\ufeff") for c in sd.columns]
            if {"code", "sector"}.issubset(sd.columns):
                SEC.update(dict(zip(sd["code"].str.zfill(6), sd["sector"].astype(str))))
        except Exception: pass

    def bucket(c):
        s0 = SEC.get(c, "")
        if not s0 or s0 == "nan": return "미분류"
        # 은행·보험·카드·증권·지주회사가 모두 KRX '금융' 계열로 묶인다.
        # 지주는 사업 내용이 달라도 지주 팩터를 공유하므로 한 바구니로 본다.
        if any(k in s0 for k in ("금융", "은행", "보험", "신탁")): return "금융/지주"
        return s0

    ALLC = set(D["code"].unique())
    is_common = lambda c: c.isdigit() and not ((not c.endswith("0")) and (c[:5]+"0") in ALLC)

    picks = [x.strip().zfill(6) for x in a.code.split(",")] if a.code else None
    if picks:
        miss = [c for c in picks if c not in cur.index]
        if miss:
            print(f"  ⚠️ 일봉 데이터에 없는 코드: {', '.join(miss)}")
            print(f"     → 종목일봉_30년_*.csv / _일봉OHLCV_*_adj.csv 에 해당 종목이 있는지 확인")
        stale = [(c, cur_date[c]) for c in picks if c in cur.index and cur_date[c] < last]
        if stale:
            print(f"  ⚠️ 최신일({last})보다 오래된 데이터: "
                  + ", ".join(f"{names.get(c,c)} {d}" for c, d in stale))
            print(f"     → 가격이 옛날 것이다. 진우_일봉_증분수집.py 를 먼저 돌릴 것")
    pool_mode = bool(a.pool)      # 풀 모드: 풀로 좁히되 위생 필터는 그대로 건다
    rows, dropped = [], []
    for c in cur.index:
        if picks and c not in picks: continue
        if not picks or pool_mode:
            if not is_common(c) or age.get(c,0) < NEW_LISTING_M:
                dropped.append((c, "우선주/신규상장")); continue
            if c not in F.index or not (pd.notna(F.loc[c,"roe"]) and F.loc[c,"roe"] > 0):
                dropped.append((c, "ROE<=0")); continue
            if cur.loc[c,"sig10"] >= 1:
                dropped.append((c, "🔴고점대량매도 신호")); continue
        r = cur.loc[c]
        if r["close"] < PX_FLOOR or (r["amt"] < AMT_FLOOR and not (picks and a.force)):
            dropped.append((c, f"거래대금 {r['amt']/1e8:.1f}억 < {AMT_FLOOR/1e8:.0f}억")); continue
        if c not in F.index:
            dropped.append((c, "재무 결측")); continue
        f = F.loc[c]
        pbr = f["PBR"] if pd.notna(f["PBR"]) and f["PBR"] > 0 else np.nan
        div = f["DIV"] if pd.notna(f["DIV"]) else 0
        big = bool(len(rank)) and rank.get(c, 9e9) <= 300
        track = a.track or ("가치" if big else "성장")
        if track == "성장" and not (pd.notna(r["ma60"]) and r["close"] >= r["ma60"]):
            gap = (r["close"]/r["ma60"] - 1)*100 if pd.notna(r["ma60"]) and r["ma60"] else float("nan")
            if not (picks and a.force):
                dropped.append((c, f"성장트랙 60일선 아래 ({gap:+.1f}%)")); continue
            print(f"  ⚠️ {names.get(c,c)} 60일선 {gap:+.1f}% — 추세 아래다. --force 로 통과시킨다.")
        atr = r["atr"] if pd.notna(r["atr"]) and r["atr"] > 0 else r["close"]*0.03
        rows.append(dict(code=c, name=names.get(c,c), track=track, price=r["close"], atr=atr,
                         pbr=pbr, div=div, roe=f["roe"]*100, hi20=hi20.get(c, r["close"]),
                         score=(div or 0) + (1/pbr if pd.notna(pbr) else 0)*2))
    if dropped:
        head = (f"  풀 {len(picks)}종 중 {len(dropped)}종 탈락:" if pool_mode
                else f"  탈락 {len(dropped)}종:")
        print(head)
        for c, w in dropped:
            print(f"     · {names.get(c, c)}({c}) — {w}")
        if picks and not pool_mode:
            print("     ※ 지정 종목을 그래도 보려면  --force  를 붙일 것")
    if not rows: sys.exit("후보 없음")
    df = pd.DataFrame(rows)
    if pool_mode:
        # 풀 순위 보존 — 카드 자체 score로 재정렬하면 검정된 사양(top-N)이 깨진다
        rk = {c: i for i, c in enumerate(pool_order)}
        df = df.assign(_rk=df["code"].map(rk)).sort_values("_rk").drop(columns="_rk")
    else:
        df = df.sort_values(["track", "score"], ascending=[True, False])

    print("=" * 92)
    print(f" 매매 카드 — 기준일 {last} · 자본 {a.capital:,.0f}원")
    print("=" * 92)
    print(f"  {idx_note}")
    dfac = 0.5 if defense else 1.0

    port_mode = (a.pool == "본체")            # 본체 = 월간 포트(동일가중) · 그 외 = 재량(위험1%)
    cap_on = (not picks) or pool_mode         # 풀 모드도 종목수 한도 적용

    def select(sec_cap):
        """섹터당 최대 sec_cap 종으로 카드 선정. (cards, heat, 보류목록) 반환"""
        heat, cards, hold, defer = 0.0, [], {}, []
        for _, r in df.iterrows():
            if len(cards) >= a.topn and cap_on: break
            if not port_mode and heat + RISK_PCT*100 > HEAT_CAP*100 + 1e-9 and cap_on: break
            b = bucket(r["code"])
            if hold.get(b, 0) >= sec_cap:
                defer.append((r["code"], f"섹터캡 초과 — {b}")); continue
            hold[b] = hold.get(b, 0) + 1
            heat += RISK_PCT*100; cards.append(r)
        return cards, heat, hold, defer

    n_possible = min(a.topn, len(df)) if cap_on else len(df)
    if port_mode:
        # 캡을 한 번만 계산하면 탈락으로 카드 수가 줄었을 때 실제 비중이 캡을 넘는다.
        # 실제 결과 기준으로 최대 섹터 비중이 한도 이하가 될 때까지 캡을 좁힌다.
        cards = []
        for sc in range(max(n_possible, 1), 0, -1):
            cards, heat, hold, defer = select(sc)
            if not cards: continue
            if max(hold.values()) / len(cards) <= SECTOR_CAP + 1e-9:
                sec_cap = sc; break
        else:
            sec_cap = 1
        if defer:
            print(f"  섹터캡으로 보류 {len(defer)}종: "
                  + ", ".join(f"{names.get(c,c)}" for c, _ in defer[:10])
                  + (" …" if len(defer) > 10 else ""))
        top_b = sorted(hold.items(), key=lambda x: -x[1])[:3]
        print(f"  섹터캡 {SECTOR_CAP*100:.0f}% → 섹터당 최대 {sec_cap}종 · 실제: "
              + " · ".join(f"{b} {n}종({n/len(cards)*100:.0f}%)" for b, n in top_b))
        print("     ※ 기준선 백테는 섹터캡 없이 산출됐다. 한도(진우_통합한도.json)를 우선하므로"
              " 실전 성과는 기준선과 다를 수 있다.")
    else:
        cards, heat, hold, defer = select(10**9)

    out_rows = []
    if port_mode:
        print(f"  사이징: 본체 월간포트 — 동일가중 1/{len(cards)} · 종목캡 {STOCK_CAP*100:.0f}%"
              + (" · 방어로 절반" if defense else ""))
    for r in cards:
        onR = VALUE_STOP if r["track"] == "가치" else TRAIL_STOP
        w = (min(1.0/max(len(cards),1), STOCK_CAP) if port_mode
             else min(RISK_PCT/onR, STOCK_CAP)) * dfac
        budget = a.capital * w
        # 적응형 분할 — 예산으로 몇 주나 살 수 있느냐에 따라 분할 수를 줄인다
        # (3분할하면 차수당 예산이 1/3이라, 고가주는 0주가 나온다)
        max_sh = int(budget // r["price"]) if r["price"] > 0 else 0
        if max_sh < 1:
            print(f"\n  ▣ {r['name']}({r['code']}) — 예산 {budget:,.0f}원 < 1주 {r['price']:,.0f}원 → **매수 불가** (건너뜀)")
            continue
        n_leg = 3 if max_sh >= 3 else (2 if max_sh >= 2 else 1)
        plan = SPLIT[:n_leg]
        wsum = sum(x[1] for x in plan)
        plan = [(m, sh/wsum) for m, sh in plan]
        # ATR이 가격 대비 큰 종목은 최심 차수가 −35%씩 내려가 '오지 않을 가격'이 된다.
        # 최심 하락폭을 MAX_LADDER_DD로 눌러 사다리 모양은 유지한 채 축척만 줄인다.
        deep = max(m for m, _ in plan) * r["atr"] / r["price"] if r["price"] > 0 else 0
        ladder_note = ""
        if deep > MAX_LADDER_DD:
            k = MAX_LADDER_DD / deep
            plan = [(m*k, sh) for m, sh in plan]
            ladder_note = f" · ATR 과대({r['atr']/r['price']*100:.1f}%) → 사다리 −{MAX_LADDER_DD*100:.0f}%로 압축"

        legs, tot_q, tot_cost = [], 0, 0.0
        for mult, share in plan:
            px = r["price"] - mult*r["atr"]
            if px <= 0: continue
            q = int((budget*share)//px)
            if q < 1: q = 0
            legs.append((px, q, share)); tot_q += q; tot_cost += q*px
        # 잔여 예산으로 1차 보강 (분할 후 남은 돈이 1주 이상이면 지금 더 산다)
        if legs:
            left = budget - tot_cost
            extra = int(left // legs[0][0])
            if extra > 0:
                px0, q0, sh0 = legs[0]
                legs[0] = (px0, q0 + extra, sh0); tot_q += extra; tot_cost += extra*px0
        avg = tot_cost/tot_q if tot_q else r["price"]
        split_note = (f"{n_leg}분할" + ("" if n_leg == 3 else f" (예산상 {max_sh}주까지 → 분할 축소)")
                      + ladder_note)

        print(f"\n{'─'*92}")
        if r["div"] >= 10.0:
            print(f"  ⚠️ {r['name']} 배당수익률 {r['div']:.1f}% — **특별배당(일회성) 가능성**. "
                  f"과거 배당이지 앞으로 받을 배당이 아닐 수 있다. 배당락 지났는지 직접 확인할 것.")
        print(f"  ▣ {r['name']}({r['code']})  [{r['track']}]   현재 {r['price']:,.0f}원  "
              f"· ATR {r['atr']:,.0f}  · 배당 {r['div']:.1f}%  PBR {(r['pbr'] if pd.notna(r['pbr']) else 0):.2f}  ROE {r['roe']:.1f}%")
        print(f"     예산 {budget:,.0f}원 (비중 {w*100:.1f}%{' · 방어로 절반' if defense else ''})")
        print(f"\n     ■ 진입 자리 ({split_note})")
        for i, (px, q, share) in enumerate(legs, 1):
            tag = "지금" if i == 1 else f"−{(r['price']-px)/r['price']*100:.0f}%"
            if q < 1: tag += " · 0주(예산부족)"
            print(f"        {i}차  {px:>9,.0f}원  {q:>4,}주  {q*px:>10,.0f}원   ({tag})"
                  + ("   ← 지금 주문" if i == 1 else "   ← 지정가 대기"))
        print(f"        ────────────────────────────────────────────────")
        print(f"        전량 체결 시  평균 {avg:,.0f}원 · {tot_q:,}주 · {tot_cost:,.0f}원")

        print(f"\n     ■ 청산 자리")
        if r["track"] == "가치":
            stop = avg * (1 - VALUE_STOP)
            # PBR 1.0 도달가는 **PBR<1 종목에서만** 상승 목표다.
            # PBR>1이면 1.0 도달 = 주가 하락 → 익절가로 쓰면 손절보다 낮아지는 오류가 난다.
            t_pbr = (r["price"] * (1.0/r["pbr"])
                     if pd.notna(r["pbr"]) and 0 < r["pbr"] < 1.0 else np.nan)
            if pd.notna(t_pbr) and t_pbr <= avg: t_pbr = np.nan
            t_dbl = avg * 2
            tgt = np.nanmin([t_pbr, t_dbl])
            which = "PBR 1.0" if pd.notna(t_pbr) and t_pbr <= t_dbl else "+100%"
            print(f"        손절  {stop:>9,.0f}원  (평균진입 −40% · 재난 백스톱)   손실 {tot_q*(avg-stop):>10,.0f}원 = 계좌 {tot_q*(avg-stop)/a.capital*100:.1f}%")
            if pd.notna(t_pbr):
                print(f"        익절  {tgt:>9,.0f}원  ({which} 도달 · 평균진입 대비 +{(tgt/avg-1)*100:.0f}%)   이익 {tot_q*(tgt-avg):>10,.0f}원")
                print(f"              · PBR 1.0 도달가 {t_pbr:,.0f}원 / +100% 도달가 {t_dbl:,.0f}원 → 낮은 쪽 먼저")
            else:
                note = ("PBR 1.0 초과 — 장부가 목표 없음" if pd.notna(r["pbr"]) and r["pbr"] >= 1.0
                        else "PBR 결측")
                print(f"        익절  {t_dbl:>9,.0f}원  (+100% · {note})")
            print(f"        ※ 스톱은 재난용이다. −20%쯤에서 흔들려 팔지 않는 것이 이 트랙의 규칙.")
        else:
            stop = r["hi20"] * (1 - TRAIL_STOP)
            print(f"        손절  {stop:>9,.0f}원  (최근 20일 고점 {r['hi20']:,.0f} × 0.85 · 트레일)")
            print(f"              고점이 갱신되면 손절가도 따라 올린다 — 매주 재계산")
            print(f"        익절  없음 — 트레일이 대신한다. 이긴 종목을 오래 태우는 게 이 트랙의 전부.")
        out_rows.append(dict(code=r["code"], name=r["name"], track=r["track"], price=r["price"],
                             buy1=legs[0][0] if legs else np.nan, qty1=legs[0][1] if legs else 0,
                             buy2=legs[1][0] if len(legs)>1 else np.nan, qty2=legs[1][1] if len(legs)>1 else 0,
                             buy3=legs[2][0] if len(legs)>2 else np.nan, qty3=legs[2][1] if len(legs)>2 else 0,
                             avg=avg, total_qty=tot_q, total_cost=tot_cost,
                             stop=(avg*(1-VALUE_STOP) if r["track"]=="가치" else r["hi20"]*(1-TRAIL_STOP)),
                             target=(np.nanmin([r["price"]*(1.0/r["pbr"])
                                     if pd.notna(r["pbr"]) and 0 < r["pbr"] < 1.0
                                     and r["price"]*(1.0/r["pbr"]) > avg else np.nan, avg*2])
                                     if r["track"]=="가치" else np.nan)))

    O = pd.DataFrame(out_rows)
    print(f"\n{'='*92}")
    cap_note = (f"동일가중 1/{len(cards)}·종목캡 {STOCK_CAP*100:.0f}%" if port_mode
                else f"총 heat {heat:.1f}%/{HEAT_CAP*100:.0f}%")
    print(f"  카드 {len(O)}장 · {cap_note} · "
          f"전량 체결 시 투입 {O['total_cost'].sum():,.0f}원 ({O['total_cost'].sum()/a.capital*100:.1f}%)")
    print(f"  1차만 체결 시 투입 {(O['buy1']*O['qty1']).sum():,.0f}원 ({(O['buy1']*O['qty1']).sum()/a.capital*100:.1f}%)")
    print(f"\n  ⚠️ 집행 전: ①현재가 재확인 ②ADTV 1% 주문캡 ③섹터 2종·계열 1종")
    print("=" * 92)
    O.to_csv(os.path.join(HERE, "매매카드.csv"), index=False, encoding="utf-8-sig")
    print(f"  저장: 매매카드.csv")


if __name__ == "__main__":
    main()
