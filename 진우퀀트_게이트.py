#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
진우퀀트_게이트.py — 빌드 게이트 (세션정리 §8-5)

하나라도 실패하면 **exit 1**. 문서·배포·엔진을 한 번에 막는다.

  G1 배포 정합   인계 패키지 vs PC 배포본 SHA256 대조
                 ← 2026-07-27에 실제로 터진 결함: forward_signal.py v1.1이 PC에 없었고
                    감사도구 9종 중 6종이 배포되지 않았다. 문서 감사는 있어도 배포 감사가 없었다.
  G2 샌드박스경로 게이트 대상 스크립트에 /home/claude · /mnt/user-data 하드코딩 0
  G3 백서       audit_whitepaper.py — 무마킹 폐기클레임 0
  G4 탐지기증인  lookahead_shift_test.py가 **알려진 버그를 여전히 탐지**해야 한다
                 (탐지 실패 = 탐지기가 고장난 것 → FAIL)
  G5 교정엔진   교정된 엔진에 shift(1)을 넣어도 3%p 미만이어야 한다
  G6 원장무결성  forward 원장 as-of 중복 없음 · 사양 v1.1
  G7 시총연속성  종목시총_30년.csv 에 빠진 달이 없어야 한다 (2026-07-27: 37개월 결측 발견)

사용:
    py 진우퀀트_게이트.py            # 전체
    py 진우퀀트_게이트.py --quick    # G4·G5(느린 실행검사) 생략
    py 진우퀀트_게이트.py --list     # 검사 항목만 출력

⚠️ 정보·검증용 · 투자자문 아님
"""
import argparse
import hashlib
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(ROOT, "감사", "진우퀀트_2026-07-27")
RESULTS = []


def rec(gate, name, ok, detail=""):
    RESULTS.append((gate, name, ok, detail))
    mark = "✅" if ok else "❌"
    print(f"  {mark} [{gate}] {name}" + (f"  — {detail}" if detail else ""))
    return ok


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


# ══════════════════════════════════════════════════════════════════
# G1. 배포 정합 — 인계 패키지 vs PC 배포본
# ══════════════════════════════════════════════════════════════════
# (패키지 상대경로, 배포 위치 상대경로)
DEPLOY_MAP = [
    ("04_감사도구/audit_data_coverage.py", "audit_data_coverage.py"),
    ("04_감사도구/audit_docs.py", "audit_docs.py"),
    ("04_감사도구/audit_lookahead.py", "audit_lookahead.py"),
    ("04_감사도구/audit_whitepaper.py", "audit_whitepaper.py"),
    ("04_감사도구/check_mcap_pit.py", "check_mcap_pit.py"),
    ("04_감사도구/verify_all.py", "verify_all.py"),
    ("04_감사도구/클레임_레지스트리.csv", "클레임_레지스트리.csv"),
    ("03_forward/build_style_panel.py", "build_style_panel.py"),
    ("03_forward/forward_benchmark.py", "forward_benchmark.py"),
    ("03_forward/forward_signal.py", "실전준비/forward_signal.py"),
    ("03_forward/forward_동결사양서_v1.1.md", "실전준비/forward_동결사양서_v1.1.md"),
    ("06_재량트랙_복리/정직한_복리시나리오_v2.md", "실전준비/재량트랙/정직한_복리시나리오_v2.md"),
    ("06_재량트랙_복리/재량트랙_측정사양서_v2.1.md", "실전준비/재량트랙/재량트랙_측정사양서_v2.1.md"),
    ("06_재량트랙_복리/discretionary_metrics.py", "실전준비/재량트랙/discretionary_metrics.py"),
]

# 배포 후 의도적으로 수정된 파일 — 해시 대신 존재+마커로 검사
PATCHED = {
    # 2026-07-27 기준선 재설정: 인코딩 가드 등으로 갈렸던 파일들을 인계 패키지 정본으로 **승격**했다.
    # 마커 검사는 해시 검사보다 훨씬 약하다 — 승격으로 SHA256 검사를 복원한다.
    # (구 정본은 감사/진우퀀트_2026-07-27/_구정본_0727/ 에 보존)
    "lookahead_shift_test.py": "sys.exit(1 if any",   # 패키지에 미포함 → 마커 유지
}


def g1_deploy():
    print("\n[G1] 배포 정합 — 인계 패키지 vs PC 배포본")
    if not os.path.isdir(PKG):
        return rec("G1", "인계 패키지", False, f"{PKG} 없음")
    ok_all = True
    for src, dst in DEPLOY_MAP:
        sp, dp = os.path.join(PKG, src), os.path.join(ROOT, dst)
        base = os.path.basename(dst)
        if not os.path.exists(sp):
            ok_all &= rec("G1", dst, False, "패키지 원본 없음")
            continue
        if not os.path.exists(dp):
            ok_all &= rec("G1", dst, False, "🚨 배포 안 됨")
            continue
        if base in PATCHED:
            marker = PATCHED[base]
            body = open(dp, encoding="utf-8", errors="replace").read()
            ok_all &= rec("G1", dst, marker in body, "의도적 수정본(마커 확인)")
            continue
        same = sha(sp) == sha(dp)
        ok_all &= rec("G1", dst, same, "일치" if same else f"🚨 불일치 {sha(sp)} vs {sha(dp)}")
    return ok_all


# ══════════════════════════════════════════════════════════════════
# G2. 샌드박스 경로 하드코딩
# ══════════════════════════════════════════════════════════════════
G2_TARGETS = [
    "build_style_panel.py", "forward_benchmark.py", "audit_whitepaper.py",
    "audit_lookahead.py", "audit_data_coverage.py", "audit_docs.py",
    "check_mcap_pit.py", "verify_all.py", "lookahead_shift_test.py",
    "실전준비/forward_signal.py", "강화키트/GP_보유기간_백테.py",
]
SANDBOX = re.compile(r'["\']/(?:home/claude|mnt/user-data)')


def g2_sandbox():
    print("\n[G2] 샌드박스 경로 하드코딩 — 게이트 대상 스크립트")
    ok_all = True
    for rel in G2_TARGETS:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            ok_all &= rec("G2", rel, False, "파일 없음")
            continue
        hits = [i for i, ln in enumerate(open(p, encoding="utf-8", errors="replace"), 1)
                if SANDBOX.search(ln)]
        ok_all &= rec("G2", rel, not hits, "clean" if not hits else f"🚨 L{hits[:5]}")
    return ok_all


# ══════════════════════════════════════════════════════════════════
# G3 / G5 / G6 — 외부 스크립트 실행
# ══════════════════════════════════════════════════════════════════
def child_env():
    """2026-07-27: 윈도 PowerShell에서 stdout이 **파이프**면 파이썬이 locale(cp949)로 인코딩한다.
    자식이 ✅·🚨 같은 문자를 찍는 순간 UnicodeEncodeError로 죽어서 exit 1이 된다.
    콘솔에 직접 찍을 땐 멀쩡하므로 '수동으로 돌리면 되는데 게이트만 실패'하는 형태로 나타난다."""
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    e["PYTHONUTF8"] = "1"
    return e


def run(args, timeout=1800):
    try:
        r = subprocess.run([sys.executable] + args, cwd=ROOT, capture_output=True,
                           text=True, timeout=timeout, encoding="utf-8", errors="replace",
                           env=child_env())
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout"


def g3_whitepaper():
    print("\n[G3] 백서 — 무마킹 폐기클레임")
    wp = os.path.join(ROOT, "백서_빌더", "진우퀀트_백서.md")
    if not os.path.exists(wp):
        return rec("G3", "백서 파일", False, "백서_빌더/진우퀀트_백서.md 없음")
    code, out = run(["audit_whitepaper.py", "백서_빌더/진우퀀트_백서.md"])
    tail = "" if code == 0 else " :: " + " ".join(out.strip().splitlines()[-2:])[:120]
    return rec("G3", "audit_whitepaper.py", code == 0, f"exit={code}{tail}")


def g4_witness():
    print("\n[G4] 탐지기 증인 — 알려진 버그를 여전히 잡는가")
    code, out = run(["lookahead_shift_test.py"])
    # 이 데모는 **고의로** 결함 엔진을 재현한다. 탐지(exit 1)가 정상이다.
    hit = ("룩어헤드" in out) or ("LOOKAHEAD" in out)
    d = re.search(r"([-+]?\d+\.\d+)%p", out)
    tail = "" if hit else " :: " + " ".join(out.strip().splitlines()[-2:])[:120]
    return rec("G4", "lookahead_shift_test.py", hit and code == 1,
               f"탐지 {d.group(1) if d else '?'}%p (exit={code}, 1이 정상){tail}")


def g5_fixed_engine():
    print("\n[G5] 교정 엔진 — shift(1) 넣어도 3%p 미만")
    p = os.path.join(ROOT, "강화키트", "GP_보유기간_백테.py")
    if not os.path.exists(p):
        return rec("G5", "GP_보유기간_백테.py", False, "파일 없음")
    r = subprocess.run(
        [sys.executable, "-c", GP_CHECK], cwd=ROOT, capture_output=True,
        text=True, timeout=1800, encoding="utf-8", errors="replace", env=child_env())
    m = re.search(r"MAXDELTA=([-\d.]+)", (r.stdout or "") + (r.stderr or ""))
    if not m:
        return rec("G5", "GP_보유기간_백테.py", False, "측정 실패")
    d = abs(float(m.group(1)))
    return rec("G5", "GP_보유기간_백테.py", d < 3.0, f"최대 |Δ| {d:.1f}%p (교정 전 14.4%p)")


GP_CHECK = r'''
import importlib.util, os, sys, warnings
warnings.filterwarnings("ignore")
ROOT=os.getcwd()
spec=importlib.util.spec_from_file_location("gpbt", os.path.join(ROOT,"강화키트","GP_보유기간_백테.py"))
m=importlib.util.module_from_spec(spec); m.__dict__["__name__"]="gpbt"; spec.loader.exec_module(m)
px,rets=m.load_panel(); mcap=m.load_mcap(); gp=m.load_gp_monthly(rets.index)
have=gp.notna().sum(axis=1); first=have[have>=30].index.min()
r2=rets.loc[rets.index>=first]; g2=gp.loc[gp.index>=first]
worst=0.0
for H in (1,3,6,12):
    a=m.backtest(H,r2,g2,mcap)                      # 교정본(내부에서 shift)
    b=m.backtest(H,r2,g2,mcap.shift(1))             # 한 번 더 밀기
    if a and b: worst=max(worst,abs(b["net_cagr"]-a["net_cagr"]))
print(f"MAXDELTA={worst:.2f}")
'''


def g6_ledger():
    print("\n[G6] forward 원장 무결성")
    led = os.path.join(ROOT, "실전준비", "forward_ledger.csv")
    ret = os.path.join(ROOT, "실전준비", "forward_returns.csv")
    ok = True
    if not os.path.exists(led):
        return rec("G6", "forward_ledger.csv", False, "없음")
    import csv
    rows = list(csv.DictReader(open(led, encoding="utf-8-sig")))
    months = [r["date_asof"] for r in rows]
    ok &= rec("G6", "원장 as-of 중복", len(months) == len(set(months)), f"{len(months)}개월 {months}")
    if os.path.exists(ret):
        body = open(ret, encoding="utf-8-sig").read()
        ok &= rec("G6", "수익률 사양 v1.1", "v1.1" in body, "spec 컬럼")
    else:
        ok &= rec("G6", "forward_returns.csv", False, "없음")
    # v1.2 (2026-07-27): as-of 단면 스냅샷 — 2026-07 이후 행은 빈티지 보존 필수.
    # (2026-06은 스냅샷 도입 전 + 패널 재생성으로 빈티지 소실 → 면제, 사양 부속서에 기록)
    need = [m for m in months if m >= "2026-07"]
    miss = [m for m in need
            if not os.path.exists(os.path.join(ROOT, "실전준비", "forward_snapshots", f"asof_{m}.csv"))]
    ok &= rec("G6", "단면 스냅샷(빈티지)", not miss,
              f"필요 {len(need)} · 누락 {miss}" if miss else
              f"2026-07+ 행 {len(need)}건 전부 보존" if need else "해당 행 없음(2026-06은 도입 전 면제)")
    return ok


def g7_mcap_months():
    """2026-07-27 발견: 종목시총_30년.csv에 12월이 매년 통째로 빠져 있었다(37개월).
    시총은 유니버스 선택 변수라 그 달이 없으면 백테가 통째로 건너뛴다(+1.64%p 상방 편향)."""
    print("\n[G7] 시총 월 연속성")
    p = os.path.join(ROOT, "종목시총_30년.csv")
    if not os.path.exists(p):
        return rec("G7", "종목시총_30년.csv", False, "없음")
    import csv as _csv
    months = set()
    with open(p, encoding="utf-8-sig", newline="") as f:
        r = _csv.reader(f); next(r)
        for row in r:
            if row:
                months.add(row[0][:7])
    lo, hi = min(months), max(months)
    y, m = int(lo[:4]), int(lo[5:7]); ly, lm = int(hi[:4]), int(hi[5:7])
    full = []
    while (y, m) <= (ly, lm):
        full.append(f"{y:04d}-{m:02d}"); m += 1
        if m > 12: y += 1; m = 1
    miss = [x for x in full if x not in months]
    dec = [x for x in miss if x.endswith("-12")]
    return rec("G7", "월 연속성", not miss,
               f"{len(months)}/{len(full)}개월" +
               (f" · 🚨 결측 {len(miss)}(12월 {len(dec)}) — `py 시총_결측월_보수.py`" if miss else " · 연속"))


def g8_cost_ssot():
    """2026-07-27: 거래비용 상수 7종 병존 확인. 게이트 대상은 비용모델.py(SSOT)를 쓰거나
    최소한 실측 왕복 0.559%와 정합해야 한다."""
    print("\n[G8] 비용 모델 SSOT")
    ssot = os.path.join(ROOT, "비용모델.py")
    ok = rec("G8", "비용모델.py 존재", os.path.exists(ssot))
    if not ok:
        return False
    body = open(os.path.join(ROOT, "롱온리_재산출.py"), encoding="utf-8", errors="replace").read() \
        if os.path.exists(os.path.join(ROOT, "롱온리_재산출.py")) else ""
    ok &= rec("G8", "롱온리_재산출.py → SSOT 사용", "비용모델 import" in body or "from 비용모델" in body)
    # 참고: 코드베이스 전체 하드코딩 잔존 수 (차단하지 않고 보고만)
    import glob as _g
    pat = re.compile(r"(?<!_jq_cost\()(?:COST|TAX)\s*=\s*0\.0\d+|\btax\s*=\s*0\.002\b|\bslip\w*\s*=\s*0\.0005\b")
    hits = 0
    for f in _g.glob(os.path.join(ROOT, "*.py")) + _g.glob(os.path.join(ROOT, "강화키트", "*.py")):
        if any(x in f for x in ("_백업", ".bak", "비용모델", "슬리피지_실측", "재량트랙")):
            continue
        try:
            # 주석 줄은 제외 — 마이그레이션 근거 주석에 종전 값이 남아 있다
            body = "\n".join(l for l in open(f, encoding="utf-8", errors="replace")
                             if not l.strip().startswith("#"))
            if pat.search(body):
                hits += 1
        except Exception:
            pass
    # 2026-07-27 §8-3 마이그레이션 완료 → 보고에서 **차단**으로 승격.
    # 예외: 실전준비/재량트랙 = forward 동결사양(트랙 중 변경 금지)
    ok &= rec("G8", "비용 상수 하드코딩 잔존", hits == 0,
              f"{hits}개 파일" + (" — `_jq_cost()` 로 교체할 것" if hits else " · 전량 SSOT 경유"))
    return ok


def g9_px_coverage():
    """2026-07-27 §8-1b: 조정본(_adj)은 2014년 이전 커버리지가 27%였다(생존편향).
    복원본(_full)이 전 구간 100% · 상폐 45%를 유지하는지 감시한다."""
    print("\n[G9] 가격 패널 커버리지 (§8-1b 복원본)")
    import csv as _csv
    ok = True
    for tag, pat in (("복원본(_full)", "_월봉종가캐시_{}_full.csv"),):
        rows_by_ym, codes, last = {}, set(), {}
        found = False
        for mkt in ("KOSPI", "KOSDAQ"):
            p2 = os.path.join(ROOT, "데이터수리", pat.format(mkt))
            if not os.path.exists(p2):
                continue
            found = True
            with open(p2, encoding="utf-8-sig", newline="") as f:
                r = _csv.DictReader(f)
                for row in r:
                    c, y = row["code"].zfill(6), row["ym"]
                    rows_by_ym[y] = rows_by_ym.get(y, 0) + 1
                    codes.add(c)
                    if y > last.get(c, ""):
                        last[c] = y
        if not found:
            ok &= rec("G9", tag, False, "파일 없음 — `py 조정본_과거복원.py`")
            continue
        # 미조정 대비 커버리지 (핵심 연도)
        base = {}
        for mkt in ("KOSPI", "KOSDAQ"):
            p3 = os.path.join(ROOT, f"_월봉종가캐시_{mkt}.csv")
            if not os.path.exists(p3):
                continue
            with open(p3, encoding="utf-8-sig", newline="") as f:
                for row in _csv.DictReader(f):
                    base[row["ym"]] = base.get(row["ym"], 0) + 1
        worst, worst_ym = 1.0, ""
        for y in ("1996-01", "2000-01", "2005-01", "2010-01", "2015-01", "2020-01"):
            if base.get(y):
                cov = rows_by_ym.get(y, 0) / base[y]
                if cov < worst:
                    worst, worst_ym = cov, y
        ok &= rec("G9", f"{tag} 최저 커버리지", worst >= 0.95,
                  f"{worst*100:.1f}% @ {worst_ym} (종목 {len(codes):,})")
        gone = sum(1 for c in codes if last.get(c, "") < "2026-06") / max(len(codes), 1)
        ok &= rec("G9", "상폐 포함률", gone >= 0.40,
                  f"중도소멸 {gone*100:.1f}% (미조정 45.0% 기준 · 낮으면 생존편향)")
    return ok


def g10_root_hygiene():
    """2026-07-27: 루트가 쓰레기통이 되면 '못 찾음 → 다시 만듦 → 중복' 사이클이 돈다.
    실제로 오늘 재산출 리포트가 루트에 6개 쌓였고 그중 하나는 만들자마자 구버전이 됐다.
    기준선을 박아두고 **증가**를 감시한다 (기존 315개를 지금 옮기면 import 217건이 깨진다)."""
    print("\n[G10] 루트 위생")
    import glob as _g
    npy = len([f for f in _g.glob(os.path.join(ROOT, "*.py")) if ".bak" not in f])
    nmd = len([f for f in _g.glob(os.path.join(ROOT, "*.md")) if ".bak" not in f])
    BASE_PY, BASE_MD = 320, 258      # 2026-07-27 기준선 (+여유)
    ok = rec("G10", "루트 .py 증가", npy <= BASE_PY, f"{npy}개 (기준 {BASE_PY})")
    ok &= rec("G10", "루트 .md 증가", nmd <= BASE_MD,
              f"{nmd}개 (기준 {BASE_MD}) — 리포트는 산출물\\<YYYY-MM>\\ 로")
    ok &= rec("G10", "프로젝트_지도.md", os.path.exists(os.path.join(ROOT, "프로젝트_지도.md")),
              "파일 배치 규칙 정본")
    return ok


# ══════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="G4·G5(느린 실행검사) 생략")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()

    if a.list:
        print(__doc__)
        return 0

    print("=" * 74)
    print(" 진우퀀트 빌드 게이트 · §8-5" + ("  [--quick]" if a.quick else ""))
    print("=" * 74)

    g1_deploy(); g2_sandbox(); g3_whitepaper()
    if not a.quick:
        g4_witness(); g5_fixed_engine()
    g6_ledger(); g7_mcap_months(); g8_cost_ssot(); g9_px_coverage(); g10_root_hygiene()

    fails = [r for r in RESULTS if not r[2]]
    print("\n" + "=" * 74)
    print(f" 판정: {len(RESULTS) - len(fails)}/{len(RESULTS)} 통과")
    if fails:
        print("\n 🚨 실패 항목:")
        for gate, name, _, detail in fails:
            print(f"   [{gate}] {name} — {detail}")
        print("\n ⛔ 게이트 차단. 위 항목을 고치기 전에는 배포·문서갱신 금지.")
        print("=" * 74)
        return 1
    print(" ✅ 전 항목 통과.")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    sys.exit(main())
