# -*- coding: utf-8 -*-
r"""휩쏘_기준분석.py — 형이 고른 '진짜 휩쏘' 종목의 공통 패턴 역산 (2026-08-01)

[하는 일]
  형이 눈으로 고른 기준 종목(진짜 휩쏘 재진입 자리)을
  ① 7/31 상승 등급으로 카테고리를 나누고 (상한가/25/20/15/10)
  ② 각 종목의 휩쏘 프로파일을 나란히 놓고
  ③ **공통 패턴을 숫자로 역산**한다 — 이게 작업2 일봉 탐색기의 조건이 된다.

  형 픽은 대부분 '반도체 대형 주도주'다. 소형주 노이즈와 다른 별개의 패턴 —
  그래서 시가총액·급락 깊이·어느 선(장기선)·밸류를 같이 본다.

[기준종목] 우선순위:
  ① --codes 로 직접 지정 (코드 또는 종목명, 쉼표)
  ② 기준종목.txt 파일 (한 줄에 코드 또는 종목명)
  ③ 아래 DEFAULT_REF (형이 2026-08-01에 고른 9종)

사용: py 휩쏘_기준분석.py
      py 휩쏘_기준분석.py --codes 대덕전자,심텍,삼성전자,SK하이닉스,삼성전기,피에스케이홀딩스,삼화콘덴서,LSELECTRIC,에스피지
      py 휩쏘_기준분석.py --date 20260731
      py 휩쏘_기준분석.py --save            (기준종목.txt 로 저장 — 다음부터 자동 사용)
필요: 휩쏘추출_YYYYMMDD.csv (휩쏘_추출.py 산출) · 종목명_맵.csv
출력: 휩쏘_패턴사양_YYYYMMDD.md
"""
import os, sys, argparse, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# 형이 2026-08-01에 고른 진짜 휩쏘 종목 (이름 → 코드; 이름은 참고용, 매칭은 코드 우선)
DEFAULT_REF = {
    "대덕전자": "353200", "심텍": "222800", "삼성전자": "005930",
    "SK하이닉스": "000660", "삼성전기": "009150", "피에스케이홀딩스": "031980",
    "삼화콘덴서": "001820", "LS ELECTRIC": "010120", "에스피지": "058610",
}


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


def rng(v):
    v = pd.to_numeric(pd.Series(v), errors="coerce").dropna()
    if len(v) == 0: return (np.nan, np.nan, np.nan)
    return (v.median(), v.min(), v.max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="20260731")
    ap.add_argument("--codes", default=None, help="코드 또는 종목명, 쉼표 구분")
    ap.add_argument("--save", action="store_true", help="기준종목.txt 로 저장")
    a = ap.parse_args()

    src = _find(f"휩쏘추출_{a.date}.csv")
    if not src: sys.exit(f"휩쏘추출_{a.date}.csv 없음 — 먼저 휩쏘_추출.py 실행")
    X = pd.read_csv(src, dtype={"code": str}); X["code"] = X["code"].str.zfill(6)

    names = {}
    npp = _find("종목명_맵.csv")
    if npp:
        try:
            nm = pd.read_csv(npp, dtype=str)
            names = dict(zip(nm.iloc[:, 0].str.zfill(6), nm.iloc[:, 1]))
        except Exception: pass
    name2code = {str(v).replace(" ", ""): k for k, v in names.items()}

    # ── 기준종목 확보
    def resolve(tok):
        tok = tok.strip()
        if not tok: return None
        # 코드 = ASCII 5~6자 + 숫자 포함 (예 005930, 35320K). 한글 이름은 제외.
        if tok.isascii() and 5 <= len(tok) <= 6 and tok.isalnum() and any(ch.isdigit() for ch in tok):
            return tok.zfill(6)
        key = tok.replace(" ", "")
        if key in name2code: return name2code[key]
        # 부분 일치
        for nm_, cd in name2code.items():
            if key in nm_ or nm_ in key: return cd
        return None

    raw = None
    if a.codes:
        raw = a.codes.split(",")
    elif _find("기준종목.txt"):
        with open(_find("기준종목.txt"), encoding="utf-8") as f:
            raw = [ln for ln in f.read().splitlines() if ln.strip() and not ln.startswith("#")]
    else:
        raw = list(DEFAULT_REF.keys())

    ref, miss = [], []
    for tok in raw:
        c = resolve(tok)
        if c is None and tok in DEFAULT_REF: c = DEFAULT_REF[tok]
        (ref.append(c) if c else miss.append(tok))
    ref = list(dict.fromkeys(ref))

    if a.save:
        with open(os.path.join(HERE, "기준종목.txt"), "w", encoding="utf-8") as f:
            f.write("# 진우 휩쏘 기준종목 (코드 또는 종목명, 한 줄에 하나)\n")
            for c in ref: f.write(f"{c}  # {names.get(c, '')}\n")
        print(f"저장: 기준종목.txt ({len(ref)}종)")

    R = X[X["code"].isin(ref)].copy()
    R["종목명"] = R["code"].map(lambda c: names.get(c, c))
    print("=" * 104)
    print(f" 휩쏘 기준종목 패턴 분석 — {a.date} · 기준 {len(ref)}종")
    print("=" * 104)
    if miss: print(f" ⚠️ 못 찾음: {', '.join(miss)}")
    found = set(R["code"]); notin = [c for c in ref if c not in found]
    if notin:
        print(f" ⚠️ 휩쏘추출에 없음(그날 +10% 미만이라 제외됐을 수 있음): "
              + ", ".join(f"{names.get(c,c)}({c})" for c in notin))

    if len(R) == 0: sys.exit("기준종목 데이터 없음")

    # 2일 누적 낙폭 (급락1·급락2 복리)
    R["급락1"] = pd.to_numeric(R["급락1"], errors="coerce")
    R["급락2"] = pd.to_numeric(R["급락2"], errors="coerce")
    R["2일누적"] = (1 + R["급락1"]) * (1 + R["급락2"]) - 1
    for k in ("등락률_31", "핵심선거리", "고점5년比", "이격MA240", "PBR", "PER", "시가총액"):
        if k in R.columns: R[k] = pd.to_numeric(R[k], errors="coerce")

    # ── 카테고리별
    torder = ["상한가", "25%↑", "20%↑", "15%↑", "10%↑"]
    def tkey(t):
        for i, k in enumerate(torder):
            if str(t).startswith(k): return i
        return 99
    R = R.assign(_t=R["등급"].map(tkey)).sort_values(["_t", "등락률_31"], ascending=[True, False])

    hdr = (dw("코드",7)+dw("종목명",14)+dw("테마",10)+dw("등락%",7,1)
           +dw("급락1",7,1)+dw("급락2",7,1)+dw("2일누적",8,1)+dw("핵심선",7)
           +dw("거리",7,1)+dw("5년比",7,1)+dw("시총(억)",10,1)+dw("PBR",6,1))
    for t in torder:
        sub = R[R["등급"].astype(str).str.startswith(t)]
        if len(sub) == 0: continue
        print("\n" + "─" * 104)
        print(f" {t} — {len(sub)}종")
        print("─" * 104)
        print(hdr); print("-" * 104)
        for _, r in sub.iterrows():
            g = lambda k, f="{:.1%}": (f.format(r[k]) if pd.notna(r.get(k)) else "-")
            mc = r.get("시가총액")
            e31 = r.get("등락률_31")
            print(dw(r["code"],7)+dw(r["종목명"],14)+dw(r.get("테마",""),10)
                  +dw(f"{e31:.1f}%" if pd.notna(e31) else "-",7,1)
                  +dw(g("급락1"),7,1)+dw(g("급락2"),7,1)
                  +dw(g("2일누적"),8,1)+dw(str(r.get("핵심선","-")),7)
                  +dw(g("핵심선거리"),7,1)+dw(g("고점5년比","{:.0%}"),7,1)
                  +dw(f"{mc/1e8:,.0f}" if pd.notna(mc) else "-",10,1)
                  +dw(f"{r['PBR']:.2f}" if pd.notna(r.get('PBR')) else "-",6,1))

    # ── 공통 패턴 역산
    print("\n" + "=" * 104)
    print(" 공통 패턴 (기준종목 전체)")
    print("=" * 104)
    def line(label, key, fmt="{:.1%}", scale=1.0):
        m, lo, hi = rng(R[key]) if key in R.columns else (np.nan,)*3
        if not np.isfinite(m): print(f"  {label:<12} -"); return
        f = lambda x: fmt.format(x*scale)
        print(f"  {dw(label,12)} 중앙 {f(m):>9}   범위 {f(lo):>9} ~ {f(hi):>9}")
    line("급락1", "급락1")
    line("급락2", "급락2")
    line("2일누적낙폭", "2일누적")
    line("7/31 상승", "등락률_31", "{:.1f}%", 1.0)
    line("핵심선거리", "핵심선거리")
    line("5년고점比", "고점5년比", "{:.0%}")
    line("MA240이격", "이격MA240")
    line("시총(억)", "시가총액", "{:,.0f}", 1/1e8)
    line("PBR", "PBR", "{:.2f}")

    lc = {"주20주":0,"주60주":0,"월5":0,"월10":0,"일240":0}
    for v in R["핵심선"].astype(str):
        for k in lc:
            if k == v or k in v: lc[k] += 1
    print("\n  핵심선 분포: " + " · ".join(f"{k} {v}" for k, v in lc.items() if v))
    tv = R["테마"].value_counts()
    print("  테마 분포:   " + " · ".join(f"{k} {v}" for k, v in tv.items()))
    big = int((R["시가총액"] >= 1e12).sum()) if "시가총액" in R.columns else 0
    print(f"  시총 1조 이상: {big}/{len(R)}종")

    # ── 탐색기 조건 초안
    crash = R[R["급락1"] < 0]
    exc = R[R["급락1"] >= 0]
    m1, l1, h1 = rng(crash["급락1"]); m2c, l2c, h2c = rng(crash["2일누적"])
    NEARLINE = 0.15
    near_r = R[R["핵심선거리"].abs() <= NEARLINE]
    far_r  = R[R["핵심선거리"].abs() >  NEARLINE]
    mk, lk, hk = rng(near_r["핵심선거리"].abs()); m5, l5, h5 = rng(R["고점5년比"])
    cn = crash[crash["핵심선거리"].abs() <= NEARLINE]
    mkc1 = rng(cn["급락1"])[0]; mkc2 = rng(cn["2일누적"])[0]
    print("\n" + "=" * 104)
    print(" → 작업2 일봉 휩쏘 탐색기 조건 초안 (이 범위에서 형이 조이면 됨)")
    print("=" * 104)
    if len(exc):
        print(f"  ※ 크래시 패턴 예외(1일째 상승): "
              + ", ".join(f"{n}({r['급락1']*100:+.0f}%)" for n, r in zip(exc['종목명'], [x for _, x in exc.iterrows()])))
        print(f"     → 아래 범위는 크래시형 {len(crash)}종 기준")
    print(f"  · 급락1(1차 플러시) {h1*100:.0f}% ~ {l1*100:.0f}% (중앙 {m1*100:.0f}%)")
    print(f"  · 2일 누적 낙폭     {h2c*100:.0f}% ~ {l2c*100:.0f}% (중앙 {m2c*100:.0f}%)  ← 휩쏘 깊이")
    print(f"  · 핵심선 근접       |거리| ≤ {hk*100:.0f}% (선지지형 {len(near_r)}종, 중앙 {mk*100:.1f}%)")
    print(f"  · 대상 선           " + " · ".join(f"{k}({v})" for k, v in lc.items() if v))
    print(f"  · 5년 고점 대비     {h5*100:.0f}% ~ {l5*100:.0f}% (깊은 조정)")
    print(f"  · 시총 하한         {'1조원 (대형 주도주 한정)' if big >= len(R)*0.6 else '별도 미설정'}")
    if len(far_r):
        print("\n  ── 두 갈래로 갈린다 ──")
        print(f"  [A 선지지형] {len(near_r)}종: {', '.join(near_r['종목명'])}")
        print(f"     장기선(주60/월10/일240) ±{NEARLINE*100:.0f}% 안 + 깊은 2일 플러시(중앙 {mkc2*100:.0f}%)")
        print(f"  [B 리더형]   {len(far_r)}종: {', '.join(far_r['종목명'])}")
        print(f"     선에서 멀다(추세 상단, MA240 위) + 얕은 플러시. 대장주가 지수를 끌 때.")
        print(f"     → 두 패턴은 조건이 다르다. 탐색기도 A/B 따로 만들어야 한다.")

    # md 저장
    md = [f"# 휩쏘 패턴 사양 — {a.date}\n",
          f"기준종목 {len(R)}종: " + ", ".join(R["종목명"]) + "\n",
          "## 공통 패턴 (탐색기 조건 초안)\n",
          f"- 급락1: {h1*100:.0f}% ~ {l1*100:.0f}% (중앙 {m1*100:.0f}%)",
          f"- 2일 누적 낙폭: {h2c*100:.0f}% ~ {l2c*100:.0f}% (중앙 {m2c*100:.0f}%)",
          f"- 핵심선 근접: |거리| ≤ {hk*100:.0f}%",
          f"- 대상 선: " + " · ".join(f"{k}({v})" for k, v in lc.items() if v),
          f"- 5년 고점 대비: {h5*100:.0f}% ~ {l5*100:.0f}%",
          f"- 테마: " + " · ".join(f"{k} {v}" for k, v in tv.items()),
          f"- 시총 1조 이상: {big}/{len(R)}종",
          "\n⚠️ 표본 소수. 이건 형 직관의 좌표화지 검정된 규칙이 아니다. 다음 휩쏘에서 재확인 필요.\n"]
    with open(os.path.join(HERE, f"휩쏘_패턴사양_{a.date}.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print(f"\n저장: 휩쏘_패턴사양_{a.date}.md")
    print("\n다음: 이 조건으로 작업2 일봉 탐색기를 만든다 (오늘 기준 D-1·D-0로 휩쏘 자리 탐지).")


if __name__ == "__main__":
    main()
