# -*- coding: utf-8 -*-
"""운용사양_백테.py 이중창 패치 검증 — 특히 '기본 동작이 안 바뀌었나'.

    py _이중창_점검.py
"""
import glob, io, os, sys
import numpy as np, pandas as pd
sys.argv = [sys.argv[0]]                      # argparse 오염 방지
import importlib.util
spec = importlib.util.spec_from_file_location("bt", "운용사양_백테.py")
bt = importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)

ok = []
def t(n, c): ok.append((n, bool(c)))

# ── ① apply_mask: 지정 셀만 NaN
PX = pd.DataFrame({"000001": [100.0, 110.0, 120.0], "000002": [50.0, 55.0, 60.0]},
                  index=["2020-01", "2020-02", "2020-03"])
P2, n = bt.apply_mask(PX.copy(), {("000001", "2020-02")})
t("① 1셀 결측화", n == 1 and np.isnan(P2.loc["2020-02", "000001"]))
t("② 다른 셀 보존", P2.loc["2020-01", "000001"] == 100.0 and P2.loc["2020-02", "000002"] == 55.0)

# ── ③ 수익률 사슬이 끊기는가 (이게 마스크의 존재 이유)
R = P2.pct_change(fill_method=None)["000001"]
t("③ 마스크월 수익 NaN", np.isnan(R.loc["2020-02"]))
t("④ 다음달 수익도 NaN", np.isnan(R.loc["2020-03"]))

# ── ⑤ 없는 코드/월은 조용히 무시
_, n2 = bt.apply_mask(PX.copy(), {("999999", "2020-01"), ("000001", "1990-01")})
t("⑤ 미존재 키 무시", n2 == 0)

# ── ⑥ 빈 마스크는 원본 그대로
P3, n3 = bt.apply_mask(PX.copy(), set())
t("⑥ 빈 마스크 무해", n3 == 0 and P3.equals(PX))

# ── ⑦ 이미 NaN 인 셀은 두 번 세지 않는다
PX2 = PX.copy(); PX2.loc["2020-02", "000001"] = np.nan
_, n4 = bt.apply_mask(PX2, {("000001", "2020-02")})
t("⑦ NaN 중복 안 셈", n4 == 0)

# ── ⑧ 원천 목록이 실제로 존재하는가
for src, files in bt.PX_SOURCES.items():
    for nm in files:
        t("⑧ 파일 존재 %s/%s" % (src, nm), bt.find(nm) is not None)

# ── ⑨⑩ 회귀: 기본값(full, 마스크 없음) 이 패치 전과 완전히 같은가
def load_px_OLD():
    fr = []
    for mkt in ("KOSPI", "KOSDAQ"):
        p = bt.find(f"_월봉종가캐시_{mkt}_full.csv") or bt.find(f"_월봉종가캐시_{mkt}.csv")
        d = pd.read_csv(p, dtype={"code": str})
        d["code"] = d["code"].str.zfill(6)
        fr.append(d[["code", "ym", "close"]])
    return (pd.concat(fr, ignore_index=True)
            .pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index())

A = load_px_OLD(); B = bt.load_px("full", [])
t("⑨ 회귀: 모양 동일", A.shape == B.shape)
t("⑩ 회귀: 값 동일", A.equals(B))

# ── ⑪ kis 원천이 읽히고 기간이 맞는가
K = bt.load_px("kis", [])
t("⑪ kis 기간 1996~2026", K.index.min() == "1996-01" and K.index.max() >= "2026-01")

# ── ⑫ 마스크 파일이 실제로 걸리는가
M = bt.load_px("kis", ["_패널마스크_v1.csv", "_출처불일치_v1.csv"])
t("⑫ 마스크로 셀이 줄어든다", int(M.notna().sum().sum()) < int(K.notna().sum().sum()))

n = sum(1 for _, b in ok if b)
for name, b in ok: print(("  ✓ " if b else "  ✗ ") + name)
print("검증 %d/%d %s" % (n, len(ok), "PASS" if n == len(ok) else "FAIL"))
sys.exit(0 if n == len(ok) else 1)
