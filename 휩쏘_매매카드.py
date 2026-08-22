# -*- coding: utf-8 -*-
r"""휩쏘_매매카드.py — 휩쏘 재진입 자리의 진입·청산 카드 (작업B, 2026-08-01)

[전제] 휩쏘_탐색기.py 가 띄운 종목(휩쏘탐지_YYYYMMDD.csv) 또는 --code 로 지정.
       휩쏘는 '급락 이틀 → 장기선 지지 → 되돌림'. 그래서 일반 매매와 진입·손절이 다르다.

[진입 — 2일째 종가 기준 2분할]
  1차 = 2일째 종가(지금)                         ← 지지 확인됐으면 지금 절반
  2차 = 밟은 장기선 −0.5×ATR (하루 더 밀리면)     ← 3일째 재차 눌리면 나머지 절반
  ※ 휩쏘는 '떨어지는 칼'이 아니라 '선에서 받힌 자리'다. 그래서 물타기가 아니라
     '선 지지'라는 근거가 있는 2분할이다. 선을 종가로 이탈하면 근거가 깨진 것 → 손절.

[청산]
  손절  = 밟은 장기선 × (1 − STOP)   기본 STOP 5%   ← 선을 종가로 깨면 휩쏘 실패
          (재난 백스톱: 2일째 저가 × 0.93 중 더 가까운 쪽 — 어차피 여기가 마지노선)
  1차 익절 = 되돌림 목표. 2일 낙폭의 절반 되돌림(피보 50%) 또는 직전 반등 고점
  트레일  = 1차 익절 후 전환. 고점 −12%(성장/사이클) 트레일로 남은 물량을 태운다
  ※ 휩쏘 진입의 손절은 '선'이 기준이다. 가격 −N%가 아니라 '지지선을 지켰나'로 판단한다.

[사이징] 재량 트랙 — 위험 1%/건. 손절까지 거리로 수량 역산. 진우_통합한도.json 준수.

사용: py 휩쏘_매매카드.py --capital 10000000                 (오늘 탐지된 A·B급)
      py 휩쏘_매매카드.py --capital 10000000 --grade A         (A급만)
      py 휩쏘_매매카드.py --capital 10000000 --code 353200,222800
      py 휩쏘_매매카드.py --date 20260730 --grade A            (그날 탐지분으로)
⚠️ 기계적 산출 · 매수/매도 추천 아님 · 투자자문 아님 · 결정과 책임은 본인.
"""
import os, sys, argparse, warnings, re
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd


def _date_from(fn):
    """휩쏘탐지_YYYYMMDD.csv → 2026-07-30. 탐지 날짜를 카드가 그대로 물려받게."""
    m = re.search(r"(\d{8})", os.path.basename(str(fn)))
    return f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}" if m else None

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

RISK_PCT = 0.01           # 위험 1%/건 (재량 트랙)
HEAT_CAP = 0.06           # Σ위험 6%
STOP_A = 0.05             # A 선지지형 손절 = 밟은 선 × (1-5%)
STOP_B = 0.03             # B 리더형 손절 = 월10 × (1-3%)  (얕게 눌렸으니 더 타이트)
TRAIL_A = 0.12            # A 익절 후 트레일 -12%
TRAIL_B = 0.15            # B 리더는 추세 러너 → 더 넓은 트레일 -15%


def dw(t, n, right=False):
    import unicodedata
    t = str(t)
    g = lambda s: sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    while g(t) > n: t = t[:-1]
    return (" " * max(0, n - g(t)) + t) if right else t + " " * max(0, n - g(t))


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def load_daily():
    # 탐색기와 동일하게 로드 — 수정주가 패널 + 원주가(최근분) 이어붙이기.
    # 이걸 안 하면 패널이 며칠 전에서 멈춰 '급락 전 가격'으로 카드가 나온다.
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        p = _find(f"_일봉OHLCV_{m}_adj.csv")
        if p:
            d = pd.read_csv(p, dtype={"code": str}); fr.append(d)
    if not fr: return None
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
            raw = raw.copy(); raw["code"] = raw["code"].astype(str).str.zfill(6)
            add.append(raw[["date","code","open","high","low","close","volume"]])
    if add: D = pd.concat([D] + add, ignore_index=True)
    return D.drop_duplicates(["code","date"], keep="last").sort_values(["code","date"])


def line_price(g, asof, key):
    """밟은 선의 실제 가격 값을 되돌려준다."""
    g = g[g["date"] <= asof]; cl = g["close"].values.astype(float)
    dts = pd.to_datetime(g["date"].values)
    if key == "일240": return float(np.mean(cl[-240:])) if len(cl) >= 240 else np.nan
    s = pd.Series(cl, index=dts)
    if key == "주60주":
        wk = s.resample("W-FRI").last().dropna()
        return float(wk.tail(60).mean()) if len(wk) >= 60 else np.nan
    if key == "월10":
        mo = s.resample("ME").last().dropna()
        return float(mo.tail(10).mean()) if len(mo) >= 10 else np.nan
    return np.nan


def atr_of(g, asof, n=20):
    g = g[g["date"] <= asof]
    hi = g["high"].values.astype(float); lo = g["low"].values.astype(float)
    cl = g["close"].values.astype(float)
    if len(cl) < n + 1: return np.nan
    tr = np.maximum(hi[1:] - lo[1:], np.maximum(np.abs(hi[1:] - cl[:-1]), np.abs(lo[1:] - cl[:-1])))
    return float(np.mean(tr[-n:]))


def recent_high(g, asof, n=60):
    """급락 이전(마지막 2봉 제외) 최근 n일 고점 — B 리더형의 '추세 재개' 목표."""
    hh = g[g["date"] <= asof]["high"].values.astype(float)
    if len(hh) <= 3: return np.nan
    seg = hh[-(n + 2):-2] if len(hh) >= n + 2 else hh[:-2]
    return float(np.max(seg)) if len(seg) else np.nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=10_000_000)
    ap.add_argument("--date", default=None, help="탐지 기준일 (기본 최신 휩쏘탐지 파일)")
    ap.add_argument("--grade", default="AB", help="대상 등급 A/B/C 조합 (기본 AB)")
    ap.add_argument("--code", default=None)
    ap.add_argument("--topn", type=int, default=0, help="카드 장수 제한 (0=제한 없음, 전 종목)")
    a = ap.parse_args()

    # 탐지 결과 로드
    import glob
    det_date = None
    if a.code:
        codes = [x.strip().zfill(6) for x in a.code.split(",")]
        det = None
        fs = sorted(glob.glob(os.path.join(HERE, "휩쏘탐지_*.csv")))
        if fs:
            det = pd.read_csv(fs[-1], dtype={"code": str}); det["code"] = det["code"].str.zfill(6)
            det = det[det["code"].isin(codes)]
            det_date = _date_from(fs[-1])
    else:
        fn = f"휩쏘탐지_{a.date}.csv" if a.date else None
        src = _find(fn) if fn else None
        if not src:
            fs = sorted(glob.glob(os.path.join(HERE, "휩쏘탐지_*.csv")))
            src = fs[-1] if fs else None
        if not src: sys.exit("휩쏘탐지_*.csv 없음 — 먼저 휩쏘_탐색기.py 실행 (또는 --code 지정)")
        det = pd.read_csv(src, dtype={"code": str}); det["code"] = det["code"].str.zfill(6)
        det_date = _date_from(src)
        if "등급" in det.columns:
            det = det[det["등급"].isin(list(a.grade))]
            gnote = f"등급 [{a.grade}] {len(det)}종"
            # 위험 한도(6장)로 잘리니 좋은 것부터 — 등급(A>B>C)·품질 순
            if "품질" in det.columns:
                det = det.sort_values(["등급", "품질"], ascending=[True, False])
        else:
            gnote = f"{len(det)}종 (구버전 파일 — 등급 없음. 휩쏘_탐색기 최신본으로 재생성 권장)"
        codes = det["code"].tolist()
        print(f"  탐지 파일: {os.path.basename(src)} · {gnote}")
        if not codes:
            sys.exit(f"  → [{a.grade}]급 종목 없음. 오늘 탐지가 비었으면 카드도 없다(정상). "
                     f"특정일: --date YYYYMMDD, 등급 확대: --grade ABC")

    if not codes: sys.exit("대상 종목 없음")

    D = load_daily()
    if D is None: sys.exit("_일봉OHLCV_*_adj.csv 없음")
    last = D["date"].max()
    # 탐지 날짜(=2일째)를 기준으로. 없으면 패널 마지막. 단 패널이 그날까지 있어야 함.
    asof = det_date if (det_date and (D["date"] <= det_date).any()) else last
    if det_date and asof != det_date:
        print(f"  ⚠️ 일봉이 {det_date}까지 없음(마지막 {last}) → {last} 기준으로 계산. "
              f"진우_일봉_증분수집.py 로 최신화 권장")

    names = {}
    npp = _find("종목명_맵.csv")
    if npp:
        try:
            nm = pd.read_csv(npp, dtype=str); names = dict(zip(nm.iloc[:,0].str.zfill(6), nm.iloc[:,1]))
        except Exception: pass
    dmeta = det.set_index("code") if det is not None and len(det) else pd.DataFrame()

    print("=" * 96)
    print(f" 휩쏘 매매카드 — 2일째 {asof} · 자본 {a.capital:,.0f}원 · 위험 {RISK_PCT*100:.0f}%/건")
    print("=" * 96)
    print(" 손절은 '가격 −N%'가 아니라 '기준선을 종가로 지켰나'로 본다. 선 이탈 = 휩쏘 실패.")
    print(" A 선지지형: 깊게 빠졌다 장기선 지지 · 2분할 반반 · 손절 선−5% · 목표 낙폭 50% 되돌림")
    print(" B 리더형  : 대장주 얕은 눌림 · 1차 크게 · 손절 월10−3%(타이트) · 목표 직전 고점(추세 재개)")

    heat, cards = 0.0, []
    for c in codes:
        g = D[D["code"] == c]
        if len(g) < 260: continue
        gg = g[g["date"] <= asof]
        px = float(gg["close"].iloc[-1])
        typ = str(dmeta.loc[c, "유형"]) if (len(dmeta) and c in dmeta.index and "유형" in dmeta.columns) else "A"
        if typ not in ("A", "B"): typ = "A"
        key = dmeta.loc[c, "핵심선"] if (len(dmeta) and c in dmeta.index and "핵심선" in dmeta.columns) else None
        held = str(dmeta.loc[c, "지지"]) if (len(dmeta) and c in dmeta.index and "지지" in dmeta.columns) else ""
        cum2 = float(dmeta.loc[c, "2일누적"]) if (len(dmeta) and c in dmeta.index and "2일누적" in dmeta.columns) else np.nan
        if typ == "B":
            key = "월10"                          # 대장주는 월10선에서 받친다
        if not key or str(key) == "nan":
            key = (held.split(", ")[0] if held and held != "nan" else "일240")
        lp = line_price(g, asof, key)
        atr = atr_of(g, asof)
        if not (np.isfinite(lp) and np.isfinite(atr) and lp > 0): continue
        zlow = float(gg["low"].iloc[-1])

        # 방어 기준: 종가 '아래'에 있는 지지. 선이 종가 위면(뚫고 내려옴) 2일째 저가로.
        below = lp if lp < px else zlow
        if typ == "B":
            # 리더형: 얕은 눌림 → 타이트 손절, 1차 크게, 목표는 직전 고점(추세 재개)
            stop = max(zlow * 0.99, below * (1 - STOP_B))
            stop = min(stop, px * 0.985); stop = max(stop, px * 0.95)
            buy2 = min(max(below, px - atr), px * 0.99)   # 월10/−1ATR 중 위, 단 현재가 아래
            buy1 = px; split1 = 0.67
            ph = recent_high(g, asof, 60)
            t1 = ph if (np.isfinite(ph) and ph > px) else px * 1.10
            trail, tlabel = TRAIL_B, "직전 60일 고점(추세 재개)"
            stoplabel = f"2일저가·월10 기준 {(stop/px-1)*100:+.1f}%"
        else:
            # 선지지형: 깊은 플러시 → 방어선−5% 손절, 반반 2분할, 목표는 낙폭 50% 되돌림
            stop = below * (1 - STOP_A)
            stop = min(stop, px * 0.97); stop = max(stop, px * 0.90)
            buy1 = px
            buy2 = min(max(below - 0.5 * atr, px * 0.88), px * 0.99)   # 항상 현재가 아래
            split1 = 0.5
            if np.isfinite(cum2) and cum2 < 0:
                t1 = px + (px / (1 + cum2) - px) * 0.5
            else:
                t1 = px * 1.10
            trail, tlabel = TRAIL_A, "2일 낙폭 50% 되돌림"
            stoplabel = (f"{key}−5%" if lp < px else "2일저가 기준(선 아래로 이탈)")

        risk_per = px - stop
        if risk_per <= 0: continue
        qty = int(a.capital * RISK_PCT / risk_per)
        if qty < 1:
            cards.append((c, None)); continue
        # 한도(6%)는 '자르는' 게 아니라 '실행/관찰'을 가른다 — 종목은 다 뜬다.
        within = heat + RISK_PCT <= HEAT_CAP + 1e-9
        if within: heat += RISK_PCT
        cards.append((c, dict(typ=typ, px=px, key=key, lp=lp, atr=atr, buy1=buy1, buy2=buy2,
                              split1=split1, stop=stop, t1=t1, trail=trail, tlabel=tlabel,
                              stoplabel=stoplabel, qty=qty, held=held, risk_per=risk_per,
                              status=("실행" if within else "관찰"))))
        if a.topn and len([x for x in cards if x[1]]) >= a.topn: break

    out_rows = []
    for c, cd in cards:
        nm = names.get(c, c)
        if cd is None:
            print(f"\n  ▣ {nm}({c}) — 1주 위험이 계좌 1% 초과 → 건너뜀(고가주)")
            continue
        q = cd["qty"]; n1 = max(1, int(round(q * cd["split1"]))); n2 = max(0, q - n1)
        tag = "A 선지지형" if cd["typ"] == "A" else "B 리더형"
        st = "" if cd["status"] == "실행" else "  ⟨관찰·위험한도 초과⟩"
        print(f"\n{'─'*96}")
        print(f"  ▣ [{tag}]{st} {nm}({c})   현재(2일째 종가) {cd['px']:,.0f}원   "
              f"· 기준선 {cd['key']} {cd['lp']:,.0f}  · ATR {cd['atr']:,.0f}"
              + (f"  · 지지[{cd['held']}]" if cd['held'] and cd['held'] != 'nan' else ""))
        if cd["typ"] == "B":
            print(f"     ■ 진입 (대장주 얕은 눌림 · 1차 크게)")
            print(f"        1차  {cd['buy1']:>9,.0f}원  {n1:>4}주   ← 지금(추세 상단 되돌림 매수)")
            print(f"        2차  {cd['buy2']:>9,.0f}원  {n2:>4}주   ← 월10선까지 밀리면({(cd['buy2']/cd['px']-1)*100:+.1f}%)")
        else:
            print(f"     ■ 진입 (2분할 · 근거=선 지지)")
            print(f"        1차  {cd['buy1']:>9,.0f}원  {n1:>4}주   ← 지금(지지 확인분)")
            print(f"        2차  {cd['buy2']:>9,.0f}원  {n2:>4}주   ← 3일째 {cd['key']}−0.5ATR 재차 눌리면")
        print(f"     ■ 청산")
        print(f"        손절  {cd['stop']:>9,.0f}원  ({cd['stoplabel']} 이탈 · {(cd['stop']/cd['px']-1)*100:+.1f}%)"
              f"   손실 {q*cd['risk_per']:>9,.0f}원 = 계좌 {q*cd['risk_per']/a.capital*100:.1f}%")
        print(f"        익절1 {cd['t1']:>9,.0f}원  ({cd['tlabel']} · {(cd['t1']/cd['px']-1)*100:+.1f}%)"
              f"   → 절반 청산 후 나머지 트레일 −{cd['trail']*100:.0f}%")
        print(f"        ※ 손절 판단은 '{cd['key']} 종가 이탈'. 장중 -N% 흔들림엔 반응 안 한다.")
        out_rows.append(dict(code=c, name=nm, 유형=cd['typ'], 상태=cd['status'], 종가=cd['px'],
                             기준선=cd['key'], 선가=cd['lp'], buy1=cd['buy1'], qty1=n1,
                             buy2=cd['buy2'], qty2=n2, 손절=cd['stop'], 익절1=cd['t1'],
                             trail=f"-{cd['trail']*100:.0f}%", 위험원=q*cd['risk_per']))
    if out_rows:
        O = pd.DataFrame(out_rows)
        na, nb = int((O["유형"] == "A").sum()), int((O["유형"] == "B").sum())
        ex = O[O["상태"] == "실행"]
        print(f"\n{'='*96}")
        print(f"  카드 {len(O)}장 (A {na} · B {nb}) · 실행 {len(ex)}장(위험 {len(ex)*RISK_PCT*100:.0f}%/{HEAT_CAP*100:.0f}%)"
              f" · 관찰 {len(O)-len(ex)}장(한도 초과)")
        print(f"  실행분 1차 진입 투입 {(ex['buy1']*ex['qty1']).sum():,.0f}원")
        print(f"  ⚠️ '실행'은 위험 6% 안 · '관찰'은 한도 넘어 표시만. 어느 걸 실행할진 형이 고른다.")
        print(f"  ⚠️ 집행 전: ①2일째 종가로 지지 재확인 ②선 이탈 시 진입 취소 ③섹터 쏠림 확인")
        O.to_csv(os.path.join(HERE, f"휩쏘카드_{asof.replace('-','')}.csv"), index=False, encoding="utf-8-sig")
        print(f"  저장: 휩쏘카드_{asof.replace('-','')}.csv")
    print("=" * 96)


if __name__ == "__main__":
    main()
