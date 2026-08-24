# -*- coding: utf-8 -*-
r"""본체_이번달.py — 검증 통과한 코어 엔진의 '이번 달 선정' (2026-07-30 신설)

[왜 이게 매수 후보인가]
  이 프로젝트에서 **전기간 검정을 통과한 유일한 선정 로직**이 이것이다.
    · 유니버스: 시총 상위 300 (양시장)
    · 점수: 합성 z(배당수익률 · B/P · E/P · ROE) 4팩터 평균 — 4개 모두 있는 종목만
    · 보유: 상위 30 동일가중, 월간 리밸런싱
    · 방어: KOSPI 월봉 종가 < 10개월 이동평균 → 투입 절반
  기준선 결과(코어TR_기준선): 2016-24 +5.82%p · 2026-06~07 급락 구간 +23.08%p

[왜 주도주 풀이 아닌가]
  `검정_주도주풀_지속성.py` 사전등록 검정에서 **기각**됐다.
  1·3·5년 모두 시장을 이긴 상위 30종목은 이후 12개월에 유니버스 대비 −4.58%(승률 34.7%),
  36개월에 −30.56%(승률 8.9%). 시총을 맞춘 대조군 대비로도 −9.17%p / −36.70%p.
  → 다기간 지속 초과수익은 **매수 신호가 아니라 매도 경계 신호**에 가깝다.
  주도주 풀은 '아는 종목 목록(워치리스트)'로만 남긴다.

[정직성]
  · 팩터는 최신 재무 스냅샷 사용. 실전 집행이므로 시차 없음(백테와 달리 미래 정보 아님).
  · 이 목록은 **후보**다. 진입·청산 자리는 `매매카드.py --pool 본체`가 붙인다.

사용: py 본체_이번달.py
출력: 본체_선정.csv (code,name,score,div,bp,ep,roe,mcap_rank)
⚠️ 기계적 산출 · 투자자문 아님 · 결정과 책임은 본인.
"""
import os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

N, TOPUNIV = 30, 300


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    raise FileNotFoundError(fn)


def zsc(s):
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and sd > 0 else s * 0


print("=" * 84)
print(" 본체 — 이번 달 선정 (합성z top30 · 시총상위300 · 월간)")
print("=" * 84)

# ── 재무 (최신 스냅샷)
fins = []
for m in ("KOSPI", "KOSDAQ"):
    fins.append(pd.read_csv(_find(f"종목재무_KRX_{m}.csv"), dtype={"code": str},
                            usecols=["date", "code", "BPS", "PER", "PBR", "EPS", "DIV"]))
F = pd.concat(fins)
F["code"] = F["code"].str.zfill(6)
for c in ("BPS", "PER", "PBR", "EPS", "DIV"):
    F[c] = pd.to_numeric(F[c], errors="coerce")
asof = F["date"].max()
F = F.sort_values("date").groupby("code").tail(1).set_index("code")
F["bp"]  = np.where(F["PBR"] > 0, 1 / F["PBR"], np.nan)
F["ep"]  = np.where(F["PER"] > 0, 1 / F["PER"], np.nan)
F["roe"] = np.where(F["BPS"] > 0, F["EPS"] / F["BPS"], np.nan)
F["div"] = F["DIV"].clip(0, 60)
print(f"재무 기준일 {asof} · {len(F):,}종목")

# ── 시총 (최신)
mc = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
mc["code"] = mc["code"].str.zfill(6)
mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
mcd = mc["date"].max()
MC = mc[mc["date"] == mcd].set_index("code")["mcap"]
rank = MC.rank(ascending=False)
print(f"시총 기준일 {mcd} · {len(MC):,}종목")

# ── 방어 상태
ix = pd.read_csv(_find("kospi_index_daily.csv"))
ix["ym"] = pd.to_datetime(ix["Date"]).dt.strftime("%Y-%m")
im = ix.groupby("ym")["Close"].last(); ma10 = im.rolling(10).mean()
ym = im.index[-1]
defense = bool(pd.notna(ma10[ym]) and im[ym] < ma10[ym])
print(f"방어 판정 {ym}: KOSPI {im[ym]:,.0f} vs 10개월MA {ma10[ym]:,.0f} → "
      f"{'🔴 방어 ON — 신규 투입 절반' if defense else '🟢 방어 OFF'}")

# ── 이름
names = {}
np_ = os.path.join(HERE, "종목명_맵.csv")
if os.path.exists(np_):
    try:
        nm = pd.read_csv(np_, dtype=str)
        names = dict(zip(nm.iloc[:, 0].str.zfill(6), nm.iloc[:, 1]))
    except Exception: pass
if len(names) < 1000:
    print("  ⚠️ 종목명_맵.csv가 비었거나 부족하다 → `py 종목명_수집.py` 먼저 실행 권장")

# ── 선정
univ = rank[rank <= TOPUNIV].index
D = F.reindex(univ)[["div", "bp", "ep", "roe", "PBR", "PER"]].copy()
D = D.dropna(subset=["div", "bp", "ep", "roe"])          # 4팩터 완전 케이스만
print(f"유니버스 시총상위 {TOPUNIV} → 4팩터 완비 {len(D):,}종목")
D["score"] = (zsc(D["div"]) + zsc(D["bp"]) + zsc(D["ep"]) + zsc(D["roe"])) / 4
D = D.nlargest(N, "score")
D["name"] = [names.get(c, c) for c in D.index]
D["mcap_rank"] = rank.reindex(D.index).astype(int)

print("\n" + "-" * 84)
print(f"{'#':>3} {'코드':>7} {'종목명':<14} {'점수':>6} {'배당%':>6} {'PBR':>6} {'PER':>7} {'ROE%':>6} {'시총순':>5}")
print("-" * 84)
for i, (c, r) in enumerate(D.iterrows(), 1):
    print(f"{i:>3} {c:>7} {r['name'][:13]:<14} {r['score']:>6.2f} {r['div']:>6.1f} "
          f"{r['PBR']:>6.2f} {r['PER']:>7.1f} {r['roe']*100:>6.1f} {r['mcap_rank']:>5}")
print("-" * 84)

out = D.reset_index()[["code", "name", "score", "div", "PBR", "PER", "roe", "mcap_rank"]]
out.to_csv(os.path.join(HERE, "본체_선정.csv"), index=False, encoding="utf-8-sig")
print(f"\n저장: 본체_선정.csv ({len(out)}종목)")
print(f"다음: py 매매카드.py --pool 본체 --capital 10000000"
      + ("   ← 방어 ON이라 비중 자동 절반" if defense else ""))
