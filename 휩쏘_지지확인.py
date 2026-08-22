# -*- coding: utf-8 -*-
r"""휩쏘_지지확인.py — 휩쏘추출 결과에서 '핵심선 지지·근접' 종목만 뽑는다 (2026-08-01)

[무엇] 휩쏘추출_YYYYMMDD.csv 를 읽어(=KRX 재조회 없음, 즉시),
       7/30 저가가 주20/60·월5/10·일240 선을 **찍고 올라온(지지)** 종목과,
       선에서 N%%  안으로 **근접**한 종목을 등급별로 정리한다.

[왜] 급락 이틀 후 정확히 지지선에서 반등 = 휩쏘 재진입의 교과서 자리.
     나머지 대부분은 선까지 −30~−50% 남은 '그냥 눌림'이라 구분해야 한다.

[근접 변수] 형이 말한 5·6·7·8% — --near 로 조절. 기본 8%.
       · 지지(★): 저가가 선을 실제로 관통했다가 종가가 위 (선지지 칸에 선 이름)
       · 근접( ): 종가가 선에서 ±N%% 이내 (아직 안 닿았지만 코앞)

사용: py 휩쏘_지지확인.py                       (지지 + 8% 근접)
      py 휩쏘_지지확인.py --near 5              (5% 근접만)
      py 휩쏘_지지확인.py --touch               (실제 지지만, 근접 제외)
      py 휩쏘_지지확인.py --date 20260731
출력: 휩쏘_지지_YYYYMMDD.csv
"""
import os, sys, argparse, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def dw(t, n, right=False):
    import unicodedata
    t = str(t)
    g = lambda s: sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    while g(t) > n: t = t[:-1]
    return (" " * max(0, n - g(t)) + t) if right else t + " " * max(0, n - g(t))


def _find(fn):
    for d in (HERE, os.getcwd(), os.path.dirname(HERE)):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="20260731")
    ap.add_argument("--near", type=float, default=8.0, help="근접 변수 %% (기본 8)")
    ap.add_argument("--touch", action="store_true", help="실제 지지만 (근접 제외)")
    a = ap.parse_args()

    src = _find(f"휩쏘추출_{a.date}.csv")
    if not src: sys.exit(f"휩쏘추출_{a.date}.csv 없음 — 먼저 휩쏘_추출.py 실행")
    X = pd.read_csv(src, dtype={"code": str})
    X["code"] = X["code"].str.zfill(6)
    N = a.near / 100.0

    # 지지 = 선지지 칸에 선 이름이 있음 / 근접 = 핵심선거리 절댓값 ≤ N
    sup = X["선지지"].astype(str).str.strip()
    X["지지"] = sup.notna() & (sup != "") & (sup.str.lower() != "nan")
    dist = pd.to_numeric(X["핵심선거리"], errors="coerce")
    X["근접"] = dist.abs() <= N
    X["구분"] = np.where(X["지지"], "★지지", np.where(X["근접"], "근접", ""))

    sel = X[X["지지"]] if a.touch else X[X["지지"] | X["근접"]]
    if len(sel) == 0:
        print("해당 종목 없음 — --near 를 넓혀볼 것"); return

    # 등급 순서
    torder = ["상한가", "25%↑", "20%↑", "15%↑", "10%↑"]
    def tkey(t):
        for i, k in enumerate(torder):
            if str(t).startswith(k): return i
        return 99
    sel = sel.assign(_t=sel["등급"].map(tkey),
                     _d=pd.to_numeric(sel["핵심선거리"], errors="coerce").abs())
    sel = sel.sort_values(["_t", "구분", "_d"], ascending=[True, True, True])

    print("=" * 104)
    print(f" 휩쏘 지지·근접 — {a.date} · 지지(★) + {a.near:.0f}% 근접"
          + ("  [지지만]" if a.touch else ""))
    print("=" * 104)
    print(f" 지지 {int(X['지지'].sum())}종" + ("" if a.touch else f" · {a.near:.0f}% 근접 {int((X['근접']&~X['지지']).sum())}종")
          + f"  (전체 {len(X)}종 중)")

    hdr = (dw("구분",6) + dw("등급",9) + dw("코드",7) + dw("종목명",16) + dw("테마",10)
           + dw("종0730",9,1) + dw("급락1",8,1) + dw("급락2",8,1) + dw("핵심선",7)
           + dw("거리",7,1) + dw("선지지",14) + dw("5년比",7,1) + dw("PBR",6,1))
    for t in torder:
        sub = sel[sel["등급"].astype(str).str.startswith(t)]
        if len(sub) == 0: continue
        print("\n" + "─" * 104)
        print(f" {t} — {len(sub)}종")
        print("─" * 104)
        print(hdr); print("-" * 104)
        for _, r in sub.iterrows():
            g = lambda k, f="{:.1%}": (f.format(r[k]) if pd.notna(r.get(k)) else "-")
            c31 = r.get("종_0730")
            kl = str(r.get("핵심선", "-"))
            sp = str(r.get("선지지", "")); sp = "" if sp.lower() == "nan" else sp
            print(dw(r["구분"], 6) + dw(str(r["등급"]).replace("(≥28%)", ""), 9)
                  + dw(r["code"], 7) + dw(r["종목명"], 16) + dw(r.get("테마", ""), 10)
                  + dw(f"{c31:,.0f}" if pd.notna(c31) else "-", 9, 1)
                  + dw(g("급락1"), 8, 1) + dw(g("급락2"), 8, 1) + dw(kl, 7)
                  + dw(g("핵심선거리"), 7, 1) + dw(sp, 14)
                  + dw(g("고점5년比", "{:.0%}"), 7, 1)
                  + dw(f"{r['PBR']:.2f}" if pd.notna(r.get("PBR")) else "-", 6, 1))

    # 어느 선에서 지지가 많이 나왔나
    print("\n" + "=" * 104)
    lines = {"주20주": 0, "주60주": 0, "월5": 0, "월10": 0, "일240": 0}
    for v in X.loc[X["지지"], "선지지"].astype(str):
        for k in lines:
            if k in v: lines[k] += 1
    print(" 지지가 나온 선: " + " · ".join(f"{k} {v}종" for k, v in lines.items() if v))
    tv = sel["테마"].value_counts()
    print(" 테마: " + " · ".join(f"{k} {v}" for k, v in tv.head(8).items()))

    out = os.path.join(HERE, f"휩쏘_지지_{a.date}.csv")
    keep = ["구분", "등급", "code", "종목명", "테마", "종_0729", "종_0730", "등락률_31",
            "급락1", "급락2", "핵심선", "핵심선거리", "선지지",
            "주20주근접", "주60주근접", "월5근접", "월10근접", "이격MA240",
            "고점5년比", "PBR", "PER", "시가총액"]
    keep = [c for c in keep if c in sel.columns]
    sel[keep].to_csv(out, index=False, encoding="utf-8-sig")
    print(f"\n저장: 휩쏘_지지_{a.date}.csv ({len(sel)}종)")
    print("\n다음: 이 목록에서 '진짜 지지'로 보이는 종목을 골라줘.")
    print("      그 공통값(급락1 크기·급락2 꼬리·어느 선·근접%)을 작업2 일봉 탐색기 조건으로 굳힌다.")


if __name__ == "__main__":
    main()
