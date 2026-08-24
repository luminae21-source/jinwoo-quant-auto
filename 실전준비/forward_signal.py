# -*- coding: utf-8 -*-
r"""forward_signal.py — Forward 동결 규칙 신호 생성 + 원장 기록 (사양서 v1.1 + 병행관찰 v1.2)

동결 규칙(수정금지): 유니버스=대형 후보 · 합성 z(배당div·B/P·E/P·ROE) 등가중 top30 동일가중 ·
  방어=KOSPI 10개월MA 아래면 현금 50% · 병행관찰=배당단독 top30(기록만).
출력: 이번 달 보유 명단·비중·방어상태 + forward_ledger.csv 누적.

── 2026-07-27 수정 ──────────────────────────────────────────────────
1) 경로 자동탐색 — 종전 기본값이 샌드박스 경로(/home/claude/...)여서 PC에서 즉시 실패했다.
2) 🚨 신선도 게이트 추가 — 패널 최신월이 이미 원장에 있으면 **덮어쓰지 않고 중단**한다.
   종전 로직은 `old[old.date_asof != asof]`로 같은 달을 지우고 다시 넣어,
   패널이 갱신되지 않은 채 실행하면 **1개월차를 덮어쓰고 2개월차가 생기지 않는다.**
   본인은 트랙이 진행 중이라 믿지만 실제로는 멈춰 있는 상태가 된다.
   → 강제 재생성이 필요하면 --force.

── 2026-07-28 v1.3 — 사양서 약속 컬럼 실체화 ──────────────────────
원장에 spec_sha(동결사양서 해시)·defense_on·port_nav·b1_nav·b2_nav·notes 컬럼 추가.
NAV 3종은 수기/벤치마크 기입란 — 이 스크립트는 빈칸으로 만들고, --force 재생성 시
이미 기입된 NAV·notes는 보존한다(증거 파기 방지). 동결 라인 계산은 변경 없음.

── 2026-07-27 v1.2 — 병행관찰 2 (N=10) 추가 ────────────────────────
전략서 v2.0 코어 후보(시총 top100 풀 · 합성 z top10)를 **기록 전용**으로 나란히 남긴다.
동결 라인(top30)의 계산·기록은 **한 글자도 바뀌지 않았다** — n10_* 컬럼만 추가.
목적: 2026-12 판정일에 top30 동결 사양과 N=10 후보 사양 모두 6개월 실기록이 있게.
⚠️ 신호 생성·기록 전용. 실제 주문은 사용자가 PC/KIS에서 직접. 투자자문·수익보장 아님.
"""
try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse, glob, hashlib, os, sys, warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # 진우퀀트 루트 (실전준비의 상위)
N, TOPUNIV = 30, 300


def find(name, extra=()):
    """이름으로 파일 자동탐색: 환경변수 → 루트 재귀 → 스크립트 폴더"""
    for p in extra:
        if p and os.path.exists(p):
            return p
    for base in (ROOT, HERE, os.getcwd()):
        hits = glob.glob(os.path.join(base, "**", name), recursive=True)
        if hits:
            return sorted(hits, key=len)[0]
    return None


ap = argparse.ArgumentParser()
ap.add_argument("--force", action="store_true", help="같은 as-of 재생성 허용(덮어씀)")
ap.add_argument("--panel", default=None)
args = ap.parse_args()

PANEL = find("mini_style_panel.csv", extra=(args.panel, os.environ.get("JQ_PANEL")))
IDXP = find("kospi_index_daily.csv", extra=(os.environ.get("JQ_INDEX"),))
LEDGER = os.path.join(HERE, "forward_ledger.csv")

# v1.3: 동결사양서 해시 — "이 기록이 어느 사양으로 계산됐나"의 증거
SPEC = find("forward_동결사양서_v1.1.md")
try:
    spec_sha = hashlib.sha256(open(SPEC, "rb").read()).hexdigest()[:12] if SPEC else ""
except Exception:
    spec_sha = ""

if not PANEL:
    sys.exit("❌ mini_style_panel.csv 를 못 찾음 — --panel 로 경로 지정")


def zc(s):
    s = pd.to_numeric(s, errors="coerce")
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and sd > 0 else s * 0


sty = pd.read_csv(PANEL, dtype={"code": str})
sty["code"] = sty["code"].str.zfill(6)
asof = sty["ym"].max()

# ── 🚨 신선도 게이트 ────────────────────────────────────────────────
prev = None
if os.path.exists(LEDGER):
    old = pd.read_csv(LEDGER, dtype=str)
    if len(old):
        prev = old["date_asof"].max()
        if asof in set(old["date_asof"]) and not args.force:
            print("=" * 66)
            print(" 🚨 중단 — 패널이 갱신되지 않았다")
            print("=" * 66)
            print(f"  패널 최신월  : {asof}")
            print(f"  원장 기록월  : {sorted(old['date_asof'])}")
            print()
            print(f"  as-of {asof} 는 이미 원장에 있다. 이대로 진행하면 **기존 행을 덮어쓰고**")
            print("  새 달이 추가되지 않는다 — 트랙이 멈춘 채 진행 중으로 오인된다.")
            print()
            print("  조치: 스타일 패널을 최신월까지 갱신한 뒤 다시 실행할 것.")
            print(f"        패널 위치: {PANEL}")
            print("        (의도적 재생성이면 --force)")
            sys.exit(1)

print("=" * 66)
print(f" Forward 동결신호 · as-of {asof} · 규칙 v1.1(수정금지) · 병행 N=10 v1.2(기록만)")
print("=" * 66)
print(f"  패널: {os.path.relpath(PANEL, ROOT)}")
print(f"  지수: {os.path.relpath(IDXP, ROOT) if IDXP else '없음'}")
if prev:
    print(f"  직전 기록월: {prev} → 이번 {asof}")

# 사양서 §1: 팩터 계산 불가 종목 제외(4팩터 완전 case만, 임의 대체 금지)
g = sty[sty["ym"] == asof].dropna(subset=["div", "bp", "ep", "roe"]).copy()
print(f"  유효 종목: {len(g)} (4팩터 완전)")

# ── 방어 상태(KOSPI 10개월 MA)
defense_note, cash = "판정불가(지수파일 없음)", 0.0
if IDXP and os.path.exists(IDXP):
    idx = pd.read_csv(IDXP)
    idx["ym"] = pd.to_datetime(idx["Date"]).dt.strftime("%Y-%m")
    im = idx.groupby("ym")["Close"].last()
    ma = im.rolling(10).mean()
    if asof in im.index and pd.notna(ma.get(asof)):
        below = im[asof] < ma[asof]
        cash = 0.5 if below else 0.0
        defense_note = (f"지수 {im[asof]:.0f} vs 10MA {ma[asof]:.0f} → "
                        f"{'방어ON(현금50%)' if below else '방어OFF(풀투자)'}")

# ── 동결 합성 규칙
for c in ["div", "bp", "ep", "roe"]:
    g[c + "z"] = zc(g[c])
g["score"] = g[["divz", "bpz", "epz", "roez"]].mean(axis=1)
main = g.dropna(subset=["score"]).nlargest(N, "score").copy()
w = (1 - cash) / N
main["weight"] = round(w * 100, 2)
div_only = g.dropna(subset=["div"]).nlargest(N, "div")["code"].tolist()

print(f"\n방어: {defense_note}  |  종목당 {w*100:.2f}% × {N}  |  현금 {cash*100:.0f}%")
print("\n[주력 보유 — 합성 z(배당·B/P·E/P·ROE) top30]")
show = main[["code", "div", "bp", "ep", "roe", "score", "weight"]].reset_index(drop=True)
show.index = show.index + 1
print(show.round(3).to_string())
overlap = len(set(main["code"]) & set(div_only))
print(f"\n[병행관찰] 배당단독 top30과 겹침 {overlap}/{N}종목 (기록만, 실전배분 아님)")

# ── 병행관찰 2 (v1.2): 전략서 v2.0 코어 후보 — 시총 top100 풀 · 합성 z top10 · 기록만
n10_codes, n10_w, top100 = [], [], set()
MCAPF = find("종목시총_30년.csv", extra=(os.environ.get("JQ_MCAP"),))
if MCAPF:
    _mc = pd.read_csv(MCAPF, dtype={"code": str})
    _mc.columns = [c.strip().lstrip("\ufeff") for c in _mc.columns]
    _mc["code"] = _mc["code"].str.zfill(6)
    _mc["ym"] = pd.to_datetime(_mc["date"]).dt.strftime("%Y-%m")
    _ms = pd.to_numeric(_mc[_mc["ym"] == asof].groupby("code")["mcap"].last(), errors="coerce").dropna()
    top100 = set(_ms.nlargest(100).index)
    cand10 = g[g["code"].isin(top100)].dropna(subset=["score"])
    if len(cand10) >= 10:
        _n10 = cand10.nlargest(10, "score")
        n10_codes = _n10["code"].tolist()
        _w10 = (1 - cash) / 10
        n10_w = [round(_w10 * 100, 2)] * 10
        _ov = len(set(n10_codes) & set(main["code"]))
        print("\n[병행관찰 2 — 전략서 v2.0 코어 후보 (v1.2 신설 · 기록만 · 매매 아님)]")
        print(f"  시총 top100 풀 내 유효 {len(cand10)}종 → 합성 z top10 · 종목당 {_w10*100:.2f}% · 동결 top30과 겹침 {_ov}/10")
        print("  " + " ".join(n10_codes))
    else:
        print(f"\n[병행관찰 2] ⚠️ top100 풀 내 유효종목 {len(cand10)} < 10 — 이번 달 기록 생략")
else:
    print("\n[병행관찰 2] ⚠️ 종목시총_30년.csv 못 찾음 — N=10 기록 생략 (동결 라인 영향 없음)")

# ── 원장 기록
row = {"date_asof": asof, "defense_cash": cash, "n": N,
       "holdings": ";".join(main["code"].tolist()),
       "weights": ";".join(map(str, main["weight"].tolist())),
       "div_only_top30": ";".join(div_only),
       "n10_holdings": ";".join(n10_codes),
       "n10_weights": ";".join(map(str, n10_w)),
       # v1.3 — 사양서 약속 컬럼
       "spec_sha": spec_sha,
       "defense_on": int(cash > 0),
       "port_nav": "", "b1_nav": "", "b2_nav": "", "notes": ""}
led = pd.DataFrame([row])
if os.path.exists(LEDGER):
    old = pd.read_csv(LEDGER, dtype=str)
    # v1.3: --force 재생성이라도 이미 수기 기입된 NAV·notes는 보존(증거 파기 방지)
    if asof in set(old["date_asof"]):
        _prev = old[old["date_asof"] == asof].iloc[-1]
        for _c in ("port_nav", "b1_nav", "b2_nav", "notes"):
            _v = str(_prev.get(_c, "") or "").strip()
            if _c in old.columns and _v and _v.lower() != "nan":
                led.loc[0, _c] = _v
    led = pd.concat([old[old["date_asof"] != asof], led], ignore_index=True)
led = led.sort_values("date_asof")
led = led.fillna("")     # v1.2 신설 컬럼 — 과거 행은 빈칸 (NaN 문자열 방지)
led.to_csv(LEDGER, index=False, encoding="utf-8-sig")
print(f"\n원장 기록 → {os.path.basename(LEDGER)} ({len(led)}개월 누적)")

# ── v1.2: as-of 단면 스냅샷 — 입력 빈티지 보존
#   (2026-07-27 교훈: 패널 재생성으로 원장 계산 당시 빈티지가 소실되어 2026-06 top30이
#    현행 데이터로 재도출 불가(15/30 상이). 이제 기록의 증거를 기록과 함께 남긴다.)
_snapdir = os.path.join(HERE, "forward_snapshots")
os.makedirs(_snapdir, exist_ok=True)
_snap = g[["code", "div", "bp", "ep", "roe", "score"]].copy()
_snap["in_mcap_top100"] = _snap["code"].isin(top100)
_snap["sel_top30"] = _snap["code"].isin(set(main["code"]))
_snap["sel_n10"] = _snap["code"].isin(set(n10_codes))
_snap.insert(0, "asof", asof)
_snap = _snap.sort_values("score", ascending=False)
_snap.to_csv(os.path.join(_snapdir, f"asof_{asof}.csv"), index=False, encoding="utf-8-sig")
print(f"단면 스냅샷 → forward_snapshots/asof_{asof}.csv ({len(_snap)}종 · 빈티지 보존)")
print("다음: py forward_benchmark.py  (벤치마크 B1·B2 산출)")
print("⚠️ 신호·기록 전용 · 실제 체결은 PC/KIS에서 본인 · 투자자문 아님.")
