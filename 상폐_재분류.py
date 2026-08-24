# -*- coding: utf-8 -*-
r"""상폐_재분류.py — 소멸 코드별 재분류 테이블 생성 (2026-07-28 신설)

[위치] 검정_상폐처리_무결성.py(2026-07-19)가 분포를 실측하고 "상폐수익률_가정.md에
가정을 못 박는다"고 결론냈다 — 이 스크립트가 그 못박기의 실행이다:
  ① 소멸 코드 '개별' 분류 테이블 (집계가 아니라 코드별 — 백테가 직접 소비)
  ② 클래스별 터미널 수익률 가정 (사전등록 — 결과 보고 바꾸지 않는다)

[분류 규칙 — 월봉 기반, 우선순위 순. 법적 사유는 데이터에 없다: 가격이 말하게 한다]
  1 시장이전   : 같은 코드가 타시장에서 소멸 ±3개월 내 재등장          → 터미널   0% (연결)
  2 동결소멸   : 마지막 4개월+ 종가 완전 동일(거래정지 동결)           → 터미널 −70% (붕괴 미반영 — 실측: 정지 후 소멸 37.3%)
  3 폭락형     : 직전12M ≤ −50% or 12M고점대비 ≤ −60% or 종가 < 500원  → 터미널 −50% (정리매매 잔여 하락)
  4 정상상승형 : 직전 6M ≥ +10%                                       → 터미널   0% (합병·공개매수 유력 — 실측 10.7%)
  5 완만형     : 나머지                                                → 터미널 −30% (혼재 — 실측 평균 −26.6%와 정합)

[입력] _월봉종가캐시_KOSPI/KOSDAQ.csv (상폐 포함 · 1996~) · 종목시총_30년.csv (참고 지표)
[출력] 소멸_재분류_v1.csv · 소멸_재분류_v1_지문.json · 상폐수익률_가정.md
사용: py 상폐_재분류.py   (진우퀀트 루트)
⚠️ 측정 도구. 투자자문 아님·책임 본인.
"""
import os, sys, json, hashlib
import pandas as pd
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    raise FileNotFoundError(fn)

TERMINAL = {"시장이전": 0.0, "동결소멸": -0.70, "폭락형": -0.50, "정상상승형": 0.0, "완만형": -0.30}
RECENT_CUT = "2025-01"     # 이후 소멸은 재상장 가능성 표기(실측 문서 관례)

print("=" * 78)
print(" 상폐 재분류 — 소멸 코드별 분류 + 터미널 수익률 가정 못박기")
print("=" * 78)

frames = []
for mkt in ("KOSPI", "KOSDAQ"):
    d = pd.read_csv(_find(f"_월봉종가캐시_{mkt}.csv"), dtype={"code": str})
    d["code"] = d["code"].str.zfill(6)
    d["mkt"] = mkt
    frames.append(d)
px = pd.concat(frames).sort_values(["code", "mkt", "ym"])
panel_end = px["ym"].max()
print(f"패널: {px['ym'].min()} ~ {panel_end} · 코드 {px['code'].nunique():,} (양시장 합산)")

# 시장별 생애
span = px.groupby(["code", "mkt"]).agg(first=("ym", "min"), last=("ym", "max")).reset_index()

# 코드 전체(양시장 통합) 마지막 관측
last_any = px.groupby("code")["ym"].max()
gone_codes = last_any[last_any < "2026-04"].index          # 패널 끝 2~3개월 여유
print(f"소멸(양시장 통합 기준): {len(gone_codes):,}개")

mc = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
mc["code"] = mc["code"].str.zfill(6)
mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
mc_last = mc.sort_values("ym").groupby("code").tail(1).set_index("code")["mcap"]

def _mi(ym): return int(ym[:4]) * 12 + int(ym[5:7])

rows = []
for code, g in px.groupby("code"):
    lym = g["ym"].max()
    if lym >= "2026-04":
        continue
    # 시장이전: 이 코드의 시장별 구간이 이어지는가 (예: KOSDAQ 끝 ± 3개월 내 KOSPI 시작)
    sp = span[span["code"] == code]
    transfer = False
    if len(sp) >= 2:
        sp2 = sp.sort_values("first")
        for i in range(len(sp2) - 1):
            gap = _mi(sp2.iloc[i + 1]["first"]) - _mi(sp2.iloc[i]["last"])
            if -1 <= gap <= 3:
                transfer = True
    tail = g.sort_values("ym").tail(13)
    closes = tail["close"].astype(float).values
    last_close = closes[-1]
    ret12 = closes[-1] / closes[0] - 1 if len(closes) >= 13 and closes[0] > 0 else np.nan
    ret6 = closes[-1] / closes[-7] - 1 if len(closes) >= 7 and closes[-7] > 0 else np.nan
    peak12 = closes[-1] / closes.max() - 1 if closes.max() > 0 else np.nan
    flat = 1
    for a, b in zip(closes[::-1], closes[::-1][1:]):
        if a == b: flat += 1
        else: break

    if transfer:
        cls = "시장이전"
    elif flat >= 4:
        cls = "동결소멸"
    elif (pd.notna(ret12) and ret12 <= -0.5) or (pd.notna(peak12) and peak12 <= -0.6) or last_close < 500:
        cls = "폭락형"
    elif pd.notna(ret6) and ret6 >= 0.10:
        cls = "정상상승형"
    else:
        cls = "완만형"

    rows.append(dict(code=code, last_ym=lym, mkt=";".join(sorted(g["mkt"].unique())),
                     cls=cls, terminal_ret=TERMINAL[cls],
                     last_close=round(last_close, 1),
                     ret6=round(ret6, 4) if pd.notna(ret6) else "",
                     ret12=round(ret12, 4) if pd.notna(ret12) else "",
                     peak12=round(peak12, 4) if pd.notna(peak12) else "",
                     flat_months=flat,
                     mcap_last=int(mc_last.get(code, 0) or 0),
                     recent=int(lym >= RECENT_CUT)))

df = pd.DataFrame(rows).sort_values(["cls", "last_ym"])
outp = os.path.join(BASE, "소멸_재분류_v1.csv")
df.to_csv(outp, index=False, encoding="utf-8-sig")

md5 = hashlib.md5(open(outp, "rb").read()).hexdigest()
json.dump({"파일": "소멸_재분류_v1.csv", "md5": md5, "행": len(df),
           "패널끝": panel_end, "동결일": "2026-07-28",
           "클래스별": df["cls"].value_counts().to_dict(),
           "터미널_가정": TERMINAL,
           "생성기": "상폐_재분류.py"},
          open(os.path.join(BASE, "소멸_재분류_v1_지문.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

vc = df["cls"].value_counts()
tot = len(df)
print("\n[분류 결과]")
for c in ("폭락형", "완만형", "정상상승형", "동결소멸", "시장이전"):
    n = int(vc.get(c, 0))
    print(f"  {c:<6} {n:5,}개 ({n/tot*100:5.1f}%)  → 터미널 {TERMINAL[c]*100:+.0f}%")
print(f"  최근(2025+) 소멸 플래그: {int(df['recent'].sum())}개 (재상장 가능 — 백테 시 주의)")

# 실측 문서와의 정합 (일봉 실측: 폭락형 42.8% · 정상상승형 10.7%)
print("\n[정합 검사 — 일봉 실측(2026-07-19) 대비]")
print(f"  폭락형(+동결) {(vc.get('폭락형',0)+vc.get('동결소멸',0))/tot*100:.1f}%  vs 일봉 실측 42.8%")
print(f"  정상상승형    {vc.get('정상상승형',0)/tot*100:.1f}%  vs 일봉 실측 10.7%")

# 가중 드래그 추정 (실효 소멸률 3.0%/년 × 평균 터미널)
w_term = (df["terminal_ret"] * 1.0).mean()
print(f"\n  평균 터미널 가정: {w_term*100:.1f}% → 연간 드래그 추정 ≈ {0.03*w_term*100:.2f}%p (EW 전시장 기준)")

# ── 가정 못박기 문서
md = f"""# 상폐수익률_가정 v1 — 사전등록 (2026-07-28)

검정_상폐처리_무결성(2026-07-19)의 결론("이 문서의 숫자를 보고 가정을 못 박는다")의 실행.
**모든 포트폴리오 백테스트는 이 가정을 쓴다. 결과가 마음에 안 든다고 바꾸지 않는다.**
변경은 새 버전(v2) 사전등록으로만 한다.

## 클래스별 터미널 수익률 (마지막 관측가 이후 추가 손실)

| 클래스 | 정의 (월봉 기준) | 터미널 | 근거 |
|---|---|---:|---|
| 시장이전 | 타시장 ±3개월 내 재등장 | 0% | 소멸 아님 — 수익률 연결 |
| 동결소멸 | 마지막 4개월+ 종가 동일 | **−70%** | 거래정지 동결 — 붕괴가 데이터에 없음 (실측: 정지 후 소멸 37.3%) |
| 폭락형 | 12M ≤ −50% or 고점比 ≤ −60% or <500원 | **−50%** | 정리매매 잔여 하락 (실측 직전20일 평균 −89.3% 유형) |
| 정상상승형 | 직전 6M ≥ +10% | 0% | 합병·공개매수 유력 (실측 10.7% · 평균 +136.5%) |
| 완만형 | 나머지 | **−30%** | 혼재 (실측 전체 평균 −26.6%와 정합) |

## 이번 재분류 결과 (소멸 {tot:,}개 · 지문 md5 {md5[:12]})

| 클래스 | 개수 | 비중 |
|---|---:|---:|
""" + "\n".join(f"| {c} | {int(vc.get(c,0)):,} | {vc.get(c,0)/tot*100:.1f}% |"
                for c in ("폭락형", "완만형", "정상상승형", "동결소멸", "시장이전")) + f"""

- 평균 터미널 {w_term*100:.1f}% × 연 실효 소멸률 ~3.0% → **EW 전시장 연간 드래그 ≈ {0.03*w_term*100:.2f}%p**
  (시총 top300 포트는 소멸 빈도가 훨씬 낮아 드래그 ≪ 이 값 — 코어TR 기준선 실측 3건/157개월)
- 2025년 이후 소멸 {int(df['recent'].sum())}건은 재상장 가능성 있음 — 개별 확인 전까지 보수 유지.
- 한계: 법적 사유 미사용(데이터에 없음) · 월봉 근사 — 일봉 정밀화는 검정_상폐처리_무결성의
  거래량 0 신호로 가능(무기후보 등록부 행).

## 백테 통합

`소멸_재분류_v1.csv`의 (code → terminal_ret)을 소멸 월 수익률에 곱-적용:
r_소멸월 = (1 + r_관측) × (1 + terminal_ret) − 1. 테이블에 없는 소멸 코드는 −30%(완만형 기본).
코어_TR_기준선.py 는 파일이 있으면 자동 사용한다.

⚠️ 과거통계·사전등록 가정. 투자자문 아님·책임 본인.
"""
with open(os.path.join(BASE, "상폐수익률_가정.md"), "w", encoding="utf-8") as f:
    f.write(md)
print("\n저장: 소멸_재분류_v1.csv · 소멸_재분류_v1_지문.json · 상폐수익률_가정.md")
