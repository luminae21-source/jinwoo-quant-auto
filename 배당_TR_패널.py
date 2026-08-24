# -*- coding: utf-8 -*-
r"""배당_TR_패널.py — 월봉 총수익(TR) 캐시 생성 (2026-07-28 신설 · 백서 '남은 구멍 ①배당 TR축' 해소)

[존재 이유] 지금까지 모든 백테스트는 가격수익(PX)만 쟀다. 한국 배당수익률은 연 1~4%로,
가치·배당 팩터 포트에서는 알파의 상당 부분이 여기 있는데 측정 밖이었다.
이 스크립트는 기존 월봉종가캐시에 배당을 얹은 TR 캐시를 만들어, 기존 백테가
"종가캐시 → TR캐시" 교체 한 줄로 총수익 기준 재판정을 할 수 있게 한다.

[방법 — 근사임을 명시]
  ret_tr(m) = ret_px(m) + DIV(m-1)/100/12
  · DIV = KRX 종목재무의 배당수익률(%) — 직전월 값을 12등분해 매월 가산(look-ahead 없음)
  · 배당락 시점을 안 쓰는 균등 발생 근사. 개별월 오차는 있으나 연 단위 기여는 보수적으로 정확.
  · DIV 데이터는 2002-01부터 — 그 이전 구간은 ret_tr = ret_px (div_y=0, 컬럼으로 구분 가능).
  · 월 갭(거래정지 등)이 있으면 해당 월 수익률은 NaN 처리(다개월 점프를 1개월로 오인 방지).

[입력]  _월봉종가캐시_KOSPI/KOSDAQ.csv (code, ym, close) · 종목재무_KRX_KOSPI/KOSDAQ.csv (date, code, ..., DIV)
[출력]  _월봉TR캐시_KOSPI/KOSDAQ.csv (code, ym, close, ret_px, div_y, ret_tr) + 배당TR_요약.md

사용: py 배당_TR_패널.py            (전체 생성 + 시장 EW 요약)
      py 배당_TR_패널.py --since 2008-01   (요약 통계 시작월 변경)
⚠️ 측정 도구·정보용. 투자자문 아님·책임 본인.
"""
import os, sys, argparse
import pandas as pd
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def build_market(mkt, since="2002-07"):
    pxp = _find(f"_월봉종가캐시_{mkt}.csv"); fnp = _find(f"종목재무_KRX_{mkt}.csv")
    if not pxp or not fnp:
        print(f"⚠️ {mkt}: 입력 파일 없음 (px={bool(pxp)}, fin={bool(fnp)}) — 건너뜀"); return None
    px = pd.read_csv(pxp, dtype={"code": str}); px["code"] = px["code"].str.zfill(6)
    fn = pd.read_csv(fnp, dtype={"code": str}, usecols=["date", "code", "DIV"])
    fn["code"] = fn["code"].str.zfill(6)
    fn["ym"] = fn["date"].str[:7]
    div = fn.groupby(["code", "ym"], as_index=False)["DIV"].last()

    px = px.sort_values(["code", "ym"]).reset_index(drop=True)
    # 월 인덱스(정수)로 갭 검출
    ymi = pd.to_datetime(px["ym"] + "-01")
    px["_mi"] = ymi.dt.year * 12 + ymi.dt.month
    g = px.groupby("code")
    px["ret_px"] = g["close"].pct_change()
    px.loc[g["_mi"].diff() != 1, "ret_px"] = np.nan   # 첫 행·월 갭 → NaN

    # 직전월 배당수익률(look-ahead 방지: shift 후 merge)
    px["_ym_prev_mi"] = px["_mi"] - 1
    div_ymi = pd.to_datetime(div["ym"] + "-01")
    div["_mi"] = div_ymi.dt.year * 12 + div_ymi.dt.month
    px = px.merge(div[["code", "_mi", "DIV"]].rename(columns={"_mi": "_ym_prev_mi", "DIV": "div_y"}),
                  on=["code", "_ym_prev_mi"], how="left")
    px["div_y"] = pd.to_numeric(px["div_y"], errors="coerce").clip(lower=0, upper=60).fillna(0.0)
    px["ret_tr"] = px["ret_px"] + np.where(px["ret_px"].notna(), px["div_y"] / 100.0 / 12.0, np.nan)

    out = px[["code", "ym", "close", "ret_px", "div_y", "ret_tr"]]
    op = os.path.join(BASE, f"_월봉TR캐시_{mkt}.csv")
    out.to_csv(op, index=False, encoding="utf-8-sig")

    # ── 시장 EW 요약 (since 이후, 배당데이터 존재 구간)
    #   ⚠️ 절대 수준 주의: 현행 종가캐시는 무수정 주가 구간(액면병합 점프 등)과 동전주 EW 왜곡을
    #   포함할 수 있어 '가격수익 연환산'의 절대값은 진단용이다. 신뢰 가능한 숫자는 배당 '기여(gap)'.
    #   수정주가 재수집(데이터수리) 완료 후 캐시를 교체하고 재실행하면 절대 수준도 유효해진다.
    s = out[(out["ym"] >= since) & out["ret_px"].notna()].copy()
    s["ret_px_w"] = s["ret_px"].clip(-0.50, 0.50)          # 윈저화(±50%) — 점프·데이터오류 완충
    s["ret_tr_w"] = s["ret_px_w"] + s["div_y"] / 100 / 12
    ew = s.groupby("ym")[["ret_px", "ret_tr", "ret_px_w", "ret_tr_w"]].mean().dropna()
    yrs = len(ew) / 12.0
    ann = lambda c: ((1 + ew[c]).prod()) ** (1 / yrs) - 1 if yrs > 0 else np.nan
    a_px, a_tr = ann("ret_px"), ann("ret_tr")
    w_px, w_tr = ann("ret_px_w"), ann("ret_tr_w")
    cover = s.groupby("ym")["div_y"].apply(lambda d: (d > 0).mean()).mean()
    res = dict(mkt=mkt, months=len(ew), a_px=a_px, a_tr=a_tr, gap=a_tr - a_px,
               w_px=w_px, w_tr=w_tr, cover=cover, path=os.path.basename(op),
               n_codes=out["code"].nunique())
    print(f"  [{mkt}] {since}~{ew.index.max()} · {len(ew)}개월 · 종목 {res['n_codes']:,}")
    print(f"    EW 연환산(원자료): 가격 {a_px*100:6.2f}% → TR {a_tr*100:6.2f}%   ← 절대값은 진단용(무수정주가 왜곡 포함 가능)")
    print(f"    EW 연환산(±50%윈저): 가격 {w_px*100:6.2f}% → TR {w_tr*100:6.2f}%")
    print(f"    ★ 배당 기여: +{(a_tr-a_px)*100:.2f}%p/년 (배당>0 종목비율 {cover*100:.0f}%) — 이 숫자가 이 패널의 핵심")
    print(f"    저장: {os.path.basename(op)} ({len(out):,}행)")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2002-07", help="요약 통계 시작월 (기본 2002-07 — DIV 데이터 개시+6개월)")
    a = ap.parse_args()
    print("=" * 78)
    print(" 배당 TR 패널 — 월봉 총수익 캐시 생성 (근사: 직전월 배당수익률/12 매월 가산)")
    print("=" * 78)
    rs = [r for m in ("KOSPI", "KOSDAQ") if (r := build_market(m, a.since))]
    if not rs: sys.exit("입력 파일을 찾지 못함 — 진우퀀트 루트에서 실행할 것")

    lines = ["# 배당 TR 패널 요약", "", f"- 방법: ret_tr = ret_px + 직전월 DIV/12 (균등발생 근사 · look-ahead 없음)",
             f"- 통계 구간: {a.since} 이후 · 시장 동일가중(EW) 전 종목", ""]
    lines.append("| 시장 | 개월 | 가격수익(연·윈저) | TR(연·윈저) | ★배당 기여 |")
    lines.append("|---|---:|---:|---:|---:|")
    for r in rs:
        lines.append(f"| {r['mkt']} | {r['months']} | {r['w_px']*100:.2f}% | {r['w_tr']*100:.2f}% | +{r['gap']*100:.2f}%p |")
    lines += ["",
              "> ⚠️ 가격수익 절대값은 진단용 — 현행 종가캐시의 무수정주가 구간·동전주 EW 왜곡 포함 가능.",
              "> 믿을 숫자는 '배당 기여'다. 수정주가 재수집 완료 후 캐시 교체·재실행하면 절대값도 유효해진다.",
              "", "## 다음 단계",
              "- 기존 백테에서 `_월봉종가캐시_*.csv` 대신 `_월봉TR캐시_*.csv`의 `ret_tr`을 쓰면 총수익 기준 재판정.",
              "- 코어 포트(top30)는 시장 평균보다 고배당 편향 → 포트 단 배당 기여는 위 수치보다 클 것으로 예상(별도 재산출로 확정).",
              "- 정밀화(선택): DPS·배당락월 기반 정확 계상은 무기후보 등록부로 — 연 단위 판정에는 본 근사로 충분.",
              "", "⚠️ 측정 도구·과거통계. 투자자문 아님·책임 본인."]
    md = "\n".join(lines)
    with open(os.path.join(BASE, "배당TR_요약.md"), "w", encoding="utf-8") as f:
        f.write(md + "\n")
    print("\n저장: 배당TR_요약.md")
    print("다음: 기존 백테의 종가캐시 → TR캐시 교체 재산출로 '진짜 총수익' 확정.")


if __name__ == "__main__":
    main()
