#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""감가상각_진단.py — 감가상각 커버리지 26% 정체 원인 진단 (로컬 실행, DART API 필요)

문제: dart_value_factors.py --rebuild 후에도 감가상각 커버리지 25.8% 고정.
      라벨 매칭을 넓혔는데도 안 오름 → 매칭 문제인가, 데이터 자체가 없는가?

이 스크립트가 하는 일 (재무상세_EBITDA.csv에서 depr 누락된 종목을 표본추출해 DART 원본 재조회):
  각 (code, year)에 대해 fnlttSinglAcntAll 전체계정을 받아
   1) 어떤 재무제표(sj_div: BS/IS/CIS/CF/SCE)가 반환되나 — 특히 현금흐름표(CF) 존재 여부
   2) CF가 간접법(당기순이익+가산조정)인가 직접법인가 — 감가상각 가산라인 유무
   3) '감가/상각' 포함 계정이 실제로 있는데 우리가 놓쳤나(=회수 가능) vs 아예 없나(=불가)
  → 누락 원인을 3분류로 집계: (A)CF 미반환  (B)CF직접법/가산라인없음  (C)매칭실패(회수가능)

판정:
  · (C)매칭실패 비중 크면 → extract() 매칭 규칙 보강으로 회수 가능(엔드포인트 OK)
  · (A)+(B) 비중 크면 → fnlttSinglAcntAll로는 한계. 주석(fnlttSinglAcnt 주석)·타 소스 필요.

사용:
  py 감가상각_진단.py                 (누락 종목 40개 표본·최근2년)
  py 감가상각_진단.py --sample 80 --year 2023
  py 감가상각_진단.py --codes 005930,000660

키/캐시: dart_value_factors.py 와 동일 규칙 재사용(.dart_key·dart_corp_codes.json).
⚠️ 정보용·과거재무. 투자자문 아님·책임 본인.
"""
import os, sys, io, json, time, zipfile, argparse, csv, random
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).parent.resolve()
DART_BASE = "https://opendart.fss.or.kr/api"
SEARCH_DIRS = [BASE, BASE.parent]
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DEP_TERMS = ["감가상각", "상각비", "감가"]          # 감가상각 계열
AMO_TERMS = ["무형자산상각", "무형", "상각"]        # 무형상각 계열
CF_HINT_INDIRECT = ["당기순이익", "당기순손실", "법인세비용차감전"]  # 간접법 CF 상단 신호


def _ensure_requests():
    try:
        import requests; return requests
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests"], check=True)
        import requests; return requests


def _find(fn):
    for d in SEARCH_DIRS:
        p = d / fn
        if p.exists(): return p
    return None


def get_api_key():
    k = os.environ.get("DART_API_KEY")
    if k and k.strip(): return k.strip()
    cfg = _find("dart_config.json")
    if cfg:
        try:
            k = json.loads(Path(cfg).read_text(encoding="utf-8")).get("api_key")
            if k: return k.strip()
        except Exception: pass
    for name in (".dart_key", "재무_APIKEY.txt"):
        f = _find(name)
        if f:
            try:
                for ln in Path(f).read_text(encoding="utf-8-sig").splitlines():
                    if ln.strip(): return ln.strip()
            except Exception: pass
    return None


def get_corp_map(key, req):
    cache = _find("dart_corp_codes.json") or (BASE / "dart_corp_codes.json")
    if Path(cache).exists():
        try: return json.loads(Path(cache).read_text(encoding="utf-8"))
        except Exception: pass
    r = req.get(f"{DART_BASE}/corpCode.xml", params={"crtfc_key": key}, timeout=30); r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        root = ET.fromstring(zf.read("CORPCODE.xml"))
    m = {}
    for c in root.findall("list"):
        sc = (c.findtext("stock_code") or "").strip(); cc = (c.findtext("corp_code") or "").strip()
        if sc and cc and sc != " ": m[sc] = cc
    Path(cache).write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return m


def fetch_annual_full(corp_code, year, key, req):
    """전체계정 반환(list). CFS 우선, 없으면 OFS. fs_div 태그 포함."""
    for fs in ("CFS", "OFS"):
        p = {"crtfc_key": key, "corp_code": corp_code, "bsns_year": str(year),
             "reprt_code": "11011", "fs_div": fs}
        try:
            d = req.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=p, timeout=15).json()
        except Exception:
            return None, None
        if d.get("status") == "000":
            return d.get("list", []), fs
        if d.get("status") == "013":   # 해당 fs_div 없음 → 다음
            continue
        return None, d.get("status")
    return None, "013"


def load_missing(outpath):
    """재무상세_EBITDA.csv 에서 depr 누락 (code,year) 목록. 없으면 빈 목록."""
    miss = []; have = []
    if not os.path.exists(outpath):
        return miss, have
    with open(outpath, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["code"], str(row["fiscal_year"]))
            d = (row.get("depr") or "").strip()
            (have if d not in ("", "None") else miss).append(key)
    return miss, have


def analyze(fs_list):
    """전체계정 → 제표구성·CF방식·감가상각 라인 분석."""
    sj = {}                       # sj_div -> 계정수
    dep_lines = []                # 감가상각 계열 계정(있으면 회수가능)
    amo_lines = []
    cf_rows = []                  # CF 계정명들
    for it in fs_list or []:
        s = (it.get("sj_div") or "").strip() or "?"
        sj[s] = sj.get(s, 0) + 1
        anm = (it.get("account_nm") or "").replace(" ", "")
        val = it.get("thstrm_amount")
        if s == "CF":
            cf_rows.append(anm)
        if any(t in anm for t in DEP_TERMS):
            dep_lines.append((s, anm, val))
        if ("무형" in anm and "상각" in anm):
            amo_lines.append((s, anm, val))
    has_cf = "CF" in sj
    cf_indirect = has_cf and any(any(h in r for h in [x.replace(" ", "") for x in CF_HINT_INDIRECT]) for r in cf_rows)
    # 분류
    if dep_lines:
        cls = "C_회수가능(감가라인존재)"
    elif not has_cf:
        cls = "A_CF미반환"
    elif has_cf and not cf_indirect:
        cls = "B_CF직접법추정(가산라인없음)"
    else:
        cls = "B_CF간접법이나감가라인없음"
    return dict(sj=sj, has_cf=has_cf, cf_indirect=cf_indirect,
                dep_lines=dep_lines[:5], amo_lines=amo_lines[:3], cls=cls,
                n_accounts=len(fs_list or []))


def run(a):
    req = _ensure_requests(); key = get_api_key()
    if not key:
        print("❌ DART API key 없음(.dart_key/dart_config.json/DART_API_KEY/재무_APIKEY.txt)"); return 1
    print(f"키 OK(…{key[-4:]}). corp 매핑 로드…", flush=True)
    cmap = get_corp_map(key, req)
    outpath = _find("재무상세_EBITDA.csv") or (BASE / "재무상세_EBITDA.csv")

    if a.codes:
        codes = [c.strip().zfill(6) for c in a.codes.split(",") if c.strip()]
        targets = [(c, str(a.year)) for c in codes]
        have_sample = []
    else:
        miss, have = load_missing(str(outpath))
        if not miss:
            print(f"❌ 누락 목록 없음(파일:{outpath}). --codes 로 지정하거나 재무상세_EBITDA.csv 확인."); return 1
        yr = str(a.year) if a.year else None
        pool = [k for k in miss if (yr is None or k[1] == yr)] or miss
        random.seed(42); random.shuffle(pool)
        targets = pool[:a.sample]
        # 대조군: depr 잡힌 종목 5개(정상 라벨 확인)
        random.seed(7); random.shuffle(have)
        have_sample = have[:5]
        print(f"누락 표본 {len(targets)}건 진단 + 대조군 {len(have_sample)}건 (전체 누락 {len(miss)}·보유 {len(have)})", flush=True)

    cls_count = {}; examples = {}; recover_labels = {}
    def probe(code, year, tag):
        cc = cmap.get(code)
        if not cc: return None
        lst, fs = fetch_annual_full(cc, int(year), key, req)
        r = analyze(lst)
        time.sleep(a.sleep)
        return r, fs

    print("\n── 누락 종목 진단 ──", flush=True)
    for i, (code, year) in enumerate(targets):
        out = probe(code, year, "miss")
        if out is None: continue
        r, fs = out
        cls_count[r["cls"]] = cls_count.get(r["cls"], 0) + 1
        if r["cls"] not in examples:
            examples[r["cls"]] = dict(code=code, year=year, fs=fs, sj=r["sj"],
                                      dep_lines=r["dep_lines"])
        for s, anm, v in r["dep_lines"]:
            recover_labels[anm] = recover_labels.get(anm, 0) + 1
        if (i + 1) % 10 == 0:
            print(f"  …{i+1}/{len(targets)}", flush=True)

    print("\n【 누락 원인 분류 】")
    tot = sum(cls_count.values()) or 1
    for cls in sorted(cls_count, key=lambda k: -cls_count[k]):
        print(f"  {cls:<28} {cls_count[cls]:>4}건 ({100*cls_count[cls]/tot:4.0f}%)")
    if recover_labels:
        print("\n【 회수가능(우리가 놓친 감가상각 계정명) 】 — extract()에 추가하면 잡힘")
        for lbl, n in sorted(recover_labels.items(), key=lambda kv: -kv[1])[:15]:
            print(f"  {n:>3}회  {lbl}")
    else:
        print("\n  회수가능 감가상각 라인 없음 → 누락은 데이터 부재(엔드포인트 한계).")

    print("\n【 분류별 예시 】")
    for cls, ex in examples.items():
        print(f"  [{cls}] {ex['code']}/{ex['year']} fs={ex['fs']} 제표={ex['sj']}")
        if ex["dep_lines"]:
            print(f"        감가라인: {[l[1] for l in ex['dep_lines']]}")

    if have_sample:
        print("\n── 대조군(감가상각 정상 종목) 라벨 확인 ──")
        for code, year in have_sample:
            out = probe(code, year, "have")
            if out is None: continue
            r, _ = out
            labs = [l[1] for l in r["dep_lines"]]
            print(f"  {code}/{year}: {labs if labs else '(라인없음?)'}")

    # 판정
    A = cls_count.get("A_CF미반환", 0)
    B = sum(v for k, v in cls_count.items() if k.startswith("B_"))
    C = sum(v for k, v in cls_count.items() if k.startswith("C_"))
    print("\n" + "=" * 70)
    print("판정")
    print("=" * 70)
    if C > tot * 0.3:
        print(f"  ▶ 회수가능(C) {100*C/tot:.0f}% — 매칭 규칙 보강으로 커버리지 개선 가능.")
        print("    위 '회수가능 계정명'을 dart_value_factors.py ITEMS/extract() 에 추가 후 재-rebuild.")
    else:
        print(f"  ▶ 회수불가 우세 — CF미반환(A) {100*A/tot:.0f}% + CF직접법/가산없음(B) {100*B/tot:.0f}%.")
        print("    fnlttSinglAcntAll 로는 한계. 대안: ①EV/EBITDA 접고 EV/EBIT·배당·E/P·B/P로 밸류축 확정")
        print("    ②감가상각이 필요없는 EBIT/FCF 중심 ③주석 파싱(고비용) — ①권장.")
    result = dict(n_targets=len(targets), cls_count=cls_count,
                  recover_labels=recover_labels, examples=examples,
                  verdict=dict(A_no_cf=A, B_cf_no_dep=B, C_recoverable=C))
    json.dump(result, open(BASE / "감가상각_진단_결과.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    print("\n  저장: 감가상각_진단_결과.json  (이 파일을 대화에 올리면 다음 조치 결정)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=40, help="누락 종목 표본 수")
    ap.add_argument("--year", type=int, default=2023, help="진단 대상 회계연도(누락 필터)")
    ap.add_argument("--codes", default=None, help="특정 종목만: 005930,000660")
    ap.add_argument("--sleep", type=float, default=0.06)
    a = ap.parse_args()
    return run(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
