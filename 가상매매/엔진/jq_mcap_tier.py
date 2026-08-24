# -*- coding: utf-8 -*-
r"""jq_mcap_tier.py — 시가총액 tier(소/중/대) 판정

★ 왜 필요한가
  하순 필터는 30년 패널 검정에서 **소·중형만 채택**됐다.
  대형주는 OOS p=0.1211 로 **기각**됐다(차익거래로 소진된 것으로 보임).
  그런데 엔진이 tier 를 안 넘겨서 **기각된 규칙을 대형주에 적용**하고 있었다.
  → 이 모듈이 tier 를 공급한다.

★ 기준 (중요)
  tier 는 **시장 전체(코스피+코스닥) 시총 3분위**로 정한다.
  유니버스 내부 분위가 아니다 — 검정이 시장 전체 3분위로 했기 때문이다.
  같은 기준을 쓰지 않으면 라벨이 달라져서 규칙이 다른 대상에 걸린다.

  경계는 `종목시총_30년.csv`(월별 PIT 시총)의 **가장 최근 월** 기준.
  백테스트에서는 as_of 를 넘기면 **그 시점 기준**으로 판정한다(look-ahead 차단).

자가점검:  py jq_mcap_tier.py
"""
import os
import pandas as pd

try:
    from jq_paths import ROOT
except Exception:
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MCAP_FILE = "종목시총_30년.csv"
_CACHE = {}


def _load():
    if "df" not in _CACHE:
        p = os.path.join(ROOT, MCAP_FILE)
        if not os.path.exists(p):
            _CACHE["df"] = None
            return None
        d = pd.read_csv(p, encoding="utf-8-sig", dtype={"code": str})
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d["mcap"] = pd.to_numeric(d["mcap"], errors="coerce")
        _CACHE["df"] = d.dropna(subset=["date", "mcap", "code"])
    return _CACHE["df"]


def tier_map(as_of=None):
    """{code: '소'/'중'/'대'} — as_of 이하 가장 최근 월의 시장 전체 3분위.
    데이터 없으면 None (호출부는 tier=None 으로 보수 동작)."""
    d = _load()
    if d is None or not len(d):
        return None
    key = str(pd.Timestamp(as_of).date()) if as_of is not None else "latest"
    if key in _CACHE:
        return _CACHE[key]

    x = d if as_of is None else d[d["date"] <= pd.Timestamp(as_of)]
    if not len(x):
        return None
    snap = x[x["date"] == x["date"].max()]
    if len(snap) < 30:
        return None
    q1, q2 = snap["mcap"].quantile([1 / 3, 2 / 3])
    m = {c: ("소" if v < q1 else ("중" if v < q2 else "대"))
         for c, v in zip(snap["code"], snap["mcap"])}
    _CACHE[key] = m
    return m


def tier_of(code, as_of=None):
    """종목 tier. 모르면 None → 호출부에서 보수적으로 처리."""
    m = tier_map(as_of)
    return m.get(str(code)) if m else None


def _self_test():
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1
        ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    m = tier_map()
    chk(f"tier_map 로딩 ({len(m) if m else 0}종목)", m is not None and len(m) > 500)
    if m:
        from collections import Counter
        c = Counter(m.values())
        chk(f"3분위 균등 분할 {dict(c)}",
            abs(c["소"] - c["대"]) <= max(3, len(m) * 0.02))
        chk("삼성전자(005930) = 대", m.get("005930") == "대")
        chk("모르는 코드 → None", tier_of("999999") is None)

    # look-ahead 차단: 과거 시점 기준 tier 는 그 시점 데이터만 사용
    old = tier_map("2005-06-30")
    chk(f"과거 시점(2005-06) tier 산출 ({len(old) if old else 0}종목)",
        old is not None and len(old) > 100)
    chk("과거 시점 종목수 < 현재 종목수 (시장이 커졌다)",
        old is not None and m is not None and len(old) < len(m))

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


if __name__ == "__main__":
    _self_test()
