#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
audit_lookahead.py — 백테 스크립트의 '시점 짝짓기' 정적 감사

핵심 원리:
  `pct_change()` 자체는 버그가 아니다. 버그는 **당월 수익률 + 당월 선택변수**가 짝을 이룰 때다.

  안전(구조적):  ret = px.pct_change().shift(-1)     # t 선택 → t+1 수익
  위험(조건부):  ret = px.pct_change()               # t-1→t 수익
                 sel = feature.loc[t]                # t 시점 값으로 선택  🚨

  위험 패턴이어도, 선택변수가 별도로 .shift(1) / iloc[:i] 등으로 시차 처리됐으면 정상이다.
  이 도구는 **판정하지 않고 분류한다** — 사람이 볼 순서를 정해주는 트리아지 도구다.

사용:
  python audit_lookahead.py --dir "Desktop\진우퀀트"
  python audit_lookahead.py --dir . --only 유니버스_규칙화_검정.py
"""
try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse, re, sys
from pathlib import Path

FWD = [r"pct_change\([^)]*\)\s*\.shift\(-\s*\d+\)", r"shift\(-\s*\d+\)"]
CONTEMP = [r"pct_change\(\s*\)", r"pct_change\(\s*fill_method[^)]*\)"]
# 당월 선택 정황 — 시점 t의 외부 데이터를 그대로 인덱싱
SELECT_AT_T = [
    r"mcap\.loc\[\s*t\s*\]", r"MC\.loc\[\s*t\s*\]", r"\bmc\s*=\s*\w+\.loc\[\s*t\s*\]",
    r"\w+\.loc\[\s*t\s*\]\s*\.dropna", r"\w+\[\s*\w+\.ym\s*==\s*t\s*\]",
    r"sort_values\(ascending=False\)", 
]
# 시차 처리 정황 — 있으면 안전 쪽으로
LAGGED = [
    r"\.shift\(\s*1\s*\)", r"\.shift\(\s*\d+\s*\)", r"iloc\[\s*[^\]]*i\s*-\s*\d+",
    r"iloc\[\s*:\s*i\s*\]", r"\.rolling\([^)]*\)\.mean\(\)\s*\)?\s*\.shift",
    r"prev", r"lag",
]


def scan(p: Path):
    try:
        s = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    lines = s.splitlines()
    hit = lambda pats: [i + 1 for i, l in enumerate(lines) if any(re.search(x, l) for x in pats)]
    fwd, con, sel, lag = hit(FWD), hit(CONTEMP), hit(SELECT_AT_T), hit(LAGGED)
    if not (fwd or con):
        return None
    if fwd and not con:
        risk, why = "SAFE", "forward 수익률(shift(-1)) 사용 — 구조적으로 안전"
    elif fwd and con:
        risk, why = "MIXED", "forward·당월 혼용 — 어느 쪽이 백테 본체인지 확인 필요"
    elif sel and not lag:
        risk, why = "HIGH", "당월 수익 + 당월 선택변수, 시차 처리 정황 없음 🚨"
    elif sel and lag:
        risk, why = "MED", "당월 수익 + 당월 선택, 단 시차 처리 정황 있음 — 짝짓기 확인"
    else:
        risk, why = "LOW", "당월 수익이나 선택변수 인덱싱 정황 없음"
    return dict(path=p, risk=risk, why=why, fwd=fwd, con=con, sel=sel, lag=lag)


# 백서 클레임과 연결된 스크립트 — 우선 감사 대상
WHITEPAPER_LINK = {
    "유니버스_규칙화_검정.py": "3장 유니버스 20.1%/19.8% (🔴 버그 확정)",
    "유니버스_리더십로테이션.py": "3장 N-스윕·로테이션 (🔴 버그 확정)",
    "factor_efficacy.py": "4장 팩터 IC·롱숏 (배당 0.0487 t=5.9)",
    "multifactor_screen.py": "4장 멀티팩터 합성 +12.3%",
    "ev_fcf_factor_test.py": "4장 EV/FCF '정교함≠알파'",
    "style_conditional_factor.py": "5장 2트랙 조건부 t값",
    "exit_routing_backtest.py": "5장 매도 라우팅 (인내 vs 트레일)",
    "배당_인과검정.py": "4장 배당 최강 근거",
    "밸류축_확정.py": "4장 가치축",
    "비용반영_백테.py": "비용 관문",
    "검정_상폐처리_무결성.py": "1.3절 생존편향 방어",
    "선정_vs_EW_검증.py": "7장 'vs MKT + IC' 규율",
}
ORDER = {"HIGH": 0, "MIXED": 1, "MED": 2, "LOW": 3, "SAFE": 4}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--only", default=None)
    ap.add_argument("--out", default="감사_룩어헤드_트리아지.md")
    a = ap.parse_args()

    root = Path(a.dir)
    if not root.exists():
        sys.exit(f"경로 없음: {root}")
    files = [root / a.only] if a.only else sorted(root.rglob("*.py"))
    res = [r for r in (scan(p) for p in files) if r]
    res.sort(key=lambda r: (ORDER[r["risk"]], r["path"].name))

    L = []
    def say(x=""):
        print(x); L.append(x)

    say("# 룩어헤드 짝짓기 트리아지\n")
    say(f"대상 `{root}` · 스크립트 {len(res)}개\n")
    say("> ⚠️ 이 도구는 **판정하지 않고 분류한다.** `pct_change()`는 그 자체로 버그가 아니며,")
    say("> 선택변수가 시차 처리됐으면 정상이다. 사람이 볼 순서를 정하는 트리아지 용도.\n")

    cnt = {}
    for r in res:
        cnt[r["risk"]] = cnt.get(r["risk"], 0) + 1
    say("## 요약\n")
    for k in ("HIGH", "MIXED", "MED", "LOW", "SAFE"):
        if k in cnt:
            say(f"- **{k}** {cnt[k]}개")

    say("\n## ★ 백서 클레임 연결 스크립트 (최우선)\n")
    say("| 스크립트 | 위험 | 백서 근거 | 비고 |")
    say("|---|---|---|---|")
    seen = set()
    for r in res:
        n = r["path"].name
        if n in WHITEPAPER_LINK and n not in seen:
            seen.add(n)
            say(f"| `{n}` | **{r['risk']}** | {WHITEPAPER_LINK[n]} | {r['why']} |")
    for n, d in WHITEPAPER_LINK.items():
        if n not in seen:
            say(f"| `{n}` | — | {d} | 파일 없음 |")

    say("\n## HIGH — 당월 수익 + 당월 선택, 시차 정황 없음\n")
    for r in [x for x in res if x["risk"] == "HIGH"]:
        rel = r["path"].relative_to(root) if root in r["path"].parents else r["path"].name
        say(f"- `{rel}`  (수익 L{r['con'][:2]} · 선택 L{r['sel'][:3]})")

    say("\n## SAFE — forward 수익률\n")
    for r in [x for x in res if x["risk"] == "SAFE"]:
        rel = r["path"].relative_to(root) if root in r["path"].parents else r["path"].name
        say(f"- `{rel}`  L{r['fwd'][:2]}")

    say("\n## 확인 방법 — 정적 분석의 한계\n")
    say("정적 패턴만으로는 최종 판정이 불가능하다. 결정적 검사는 **실행 기반**이다:\n")
    say("```python")
    say("# 선택 변수에 shift(1)을 넣고 다시 돌린다")
    say("M_orig = mcap.pivot_table(...)")
    say("M_lag  = M_orig.shift(1)")
    say("# 두 결과의 CAGR 차이가 3%p 이상이면 → 그 변수는 미래 정보를 담고 있다")
    say("```")
    say("\n이 검사는 어떤 선택 변수에도 적용된다(시총·거래대금·재무·모멘텀).")
    say("**self-test에 넣으면 이 종류 버그는 재발하지 않는다.**")

    Path(a.out).write_text("\n".join(L), encoding="utf-8")
    print(f"\n저장: {a.out}")


if __name__ == "__main__":
    main()
