# -*- coding: utf-8 -*-
r"""jq_panel30.py — 30년 패널 + PIT(시점) 유니버스

★ 이것이 해결하는 것 (백테스트_결과.md §10 의 상위 4개)
  ① 유니버스 선택편향 : 종목시총_30년.csv = **월별 PIT 시총** -> 그 시점 기준으로만 뽑는다
  ② 생존편향        : 5,051종목 **상폐 포함** (날짜별 수집이라 그날 살아있던 종목 그대로)
  ③ 짧은 표본        : 6.5년 -> **30년**
  ④ 강세장 편중      : IMF(97) · 닷컴(00) · 금융위기(08) · 코로나(20) 포함

★ PIT 원칙 (절대)
  t 시점 유니버스는 **t 이전에 확정된 시총**으로만 정한다.
  '지금 시총 상위' 종목을 과거에 샀다고 가정하면 그게 look-ahead 다.
  -> 시총 스냅샷은 각 월말 확정치를 쓰고, **그 다음 달부터** 유효하다.

★ 메모리
  14.7M 행(675MB)을 통째로 올리면 터진다. PIT 유니버스에 **한 번이라도** 든
  종목의 봉만 선별 로드한다.

자가점검:  py jq_panel30.py
"""
import os
import numpy as np
import pandas as pd

try:
    from jq_paths import ROOT
except Exception:
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

F_KOSPI = "종목일봉_30년_KOSPI.csv"
F_KOSDAQ = "종목일봉_30년_KOSDAQ.csv"
F_MCAP = "종목시총_30년.csv"

# 유니버스 정의 (사전등록 — 원 Phase1 스펙 그대로)
TOP_KOSPI = 120
TOP_KOSDAQ = 40


def _p(f):
    return os.path.join(ROOT, f)


def market_codes():
    """{'KOSPI': set, 'KOSDAQ': set} — 어느 시장 종목인지.
    675MB CSV 를 코드 컬럼만 보려고 매번 파싱하면 20초씩 날린다 -> 캐시."""
    import tempfile, pickle
    cp = os.path.join(tempfile.gettempdir(), "jq_market_codes.pkl")
    sig = tuple(os.path.getmtime(_p(f)) for f in (F_KOSPI, F_KOSDAQ))
    if os.path.exists(cp):
        try:
            with open(cp, "rb") as fh:
                d = pickle.load(fh)
            if d.get("sig") == sig:
                return d["mc"]
        except Exception:
            pass
    out = {}
    for mk, f in (("KOSPI", F_KOSPI), ("KOSDAQ", F_KOSDAQ)):
        d = pd.read_csv(_p(f), encoding="utf-8-sig", usecols=["code"], dtype={"code": str})
        out[mk] = set(d["code"].unique())
    try:
        with open(cp, "wb") as fh:
            pickle.dump(dict(sig=sig, mc=out), fh, protocol=4)
    except Exception:
        pass
    return out


def load_mcap():
    d = pd.read_csv(_p(F_MCAP), encoding="utf-8-sig", dtype={"code": str})
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["mcap"] = pd.to_numeric(d["mcap"], errors="coerce")
    return d.dropna(subset=["date", "code", "mcap"])


def build_pit_universe(mode="top", mcap=None, mkc=None):
    """
    월별 PIT 유니버스.
      mode='top'  : 원 스펙 — 코스피 시총 상위 120 + 코스닥 상위 40
      mode='smid' : 확장 — 위 + 시장전체 시총 3분위의 '소·중' 중 시총 상위
                     (하순 필터의 유효 대상을 유니버스에 넣기 위함)
    반환 (pit, members)
      pit     : {(year,month): {code: market}}   ← 그 달에 진입 가능한 종목
      members : 한 번이라도 편입된 전 종목 {code: market}
    ★ 시총 스냅샷은 그 달 말 확정치 -> **다음 달**부터 적용 (look-ahead 차단)
    """
    mcap = load_mcap() if mcap is None else mcap
    mkc = market_codes() if mkc is None else mkc
    kospi, kosdaq = mkc["KOSPI"], mkc["KOSDAQ"]

    pit, members = {}, {}
    for snap_date, g in mcap.groupby("date"):
        eff = (pd.Timestamp(snap_date) + pd.offsets.MonthBegin(1))   # 다음 달부터 유효
        key = (eff.year, eff.month)
        sel = {}

        gk = g[g["code"].isin(kospi)].nlargest(TOP_KOSPI, "mcap")
        gq = g[g["code"].isin(kosdaq)].nlargest(TOP_KOSDAQ, "mcap")
        for c in gk["code"]:
            sel[c] = "KOSPI"
        for c in gq["code"]:
            sel[c] = "KOSDAQ"

        if mode == "smid":
            # 시장 전체 3분위의 소·중 -> 그 안에서 시총 상위 (유동성 근사)
            q1, q2 = g["mcap"].quantile([1 / 3, 2 / 3])
            sm = g[g["mcap"] < q2]
            for c, v in zip(sm.nlargest(TOP_KOSPI, "mcap")["code"],
                            sm.nlargest(TOP_KOSPI, "mcap")["mcap"]):
                if c in kospi:
                    sel.setdefault(c, "KOSPI")
                elif c in kosdaq:
                    sel.setdefault(c, "KOSDAQ")
            sq = sm[sm["code"].isin(kosdaq)].nlargest(TOP_KOSDAQ * 2, "mcap")
            for c in sq["code"]:
                sel.setdefault(c, "KOSDAQ")

        pit[key] = sel
        members.update(sel)
    return pit, members


def load_bars(members):
    """PIT 유니버스에 든 종목의 일봉만 선별 로드 (메모리 방어)."""
    frames = []
    for mk, f in (("KOSPI", F_KOSPI), ("KOSDAQ", F_KOSDAQ)):
        want = {c for c, m in members.items() if m == mk}
        if not want:
            continue
        chunks = []
        for ch in pd.read_csv(_p(f), encoding="utf-8-sig", dtype={"code": str},
                              chunksize=2_000_000):
            chunks.append(ch[ch["code"].isin(want)])
        d = pd.concat(chunks, ignore_index=True)
        d["market"] = mk
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("open", "high", "low", "close"):
        d[c] = pd.to_numeric(d[c], errors="coerce", downcast="float")
    d = d.dropna(subset=["date", "high", "low", "close"])
    return d[d["close"] > 0].sort_values(["code", "date"]).reset_index(drop=True)


def _self_test():
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1
        ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    for f in (F_KOSPI, F_KOSDAQ, F_MCAP):
        chk(f"{f} 존재", os.path.exists(_p(f)))

    m = load_mcap()
    chk(f"시총 로딩 ({len(m):,}행 · {m.code.nunique():,}종목)", len(m) > 100_000)
    chk(f"기간 {m.date.min().date()}~{m.date.max().date()} (30년)",
        (m.date.max() - m.date.min()).days > 10_000)

    mkc = market_codes()
    chk(f"시장 구분 KOSPI {len(mkc['KOSPI']):,} / KOSDAQ {len(mkc['KOSDAQ']):,}",
        len(mkc["KOSPI"]) > 500 and len(mkc["KOSDAQ"]) > 500)

    pit, mem = build_pit_universe("top", m, mkc)
    chk(f"PIT 유니버스 {len(pit)}개월 · 연인원 {len(mem):,}종목", len(pit) > 300)
    ks = [k for k in sorted(pit) if k[0] in (1998, 2010, 2025)]
    for k in ks:
        n = len(pit[k])
        print(f"      {k[0]}-{k[1]:02d}: {n}종목")
    chk("월별 유니버스 크기 <= 160 (top120+40)",
        all(len(v) <= TOP_KOSPI + TOP_KOSDAQ for v in pit.values()))

    # ★ PIT 검증: 유니버스가 시간에 따라 실제로 바뀌는가 (안 바뀌면 스냅샷 편향)
    a = set(pit[sorted(pit)[24]])          # 초기
    b = set(pit[sorted(pit)[-1]])          # 최근
    over = len(a & b) / max(len(a), 1)
    chk(f"초기 vs 최근 유니버스 중복률 {over*100:.0f}% (<60%면 PIT 작동)", over < 0.6)

    # ★ 생존편향: 상폐(중도소멸) 종목이 유니버스에 실제로 있는가
    last_m = m[m.date == m.date.max()]
    alive = set(last_m.code)
    dead = [c for c in mem if c not in alive]
    chk(f"과거 유니버스에 든 상폐/소멸 종목 {len(dead):,}개 포함 (생존편향 차단)",
        len(dead) > 20)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


if __name__ == "__main__":
    _self_test()
