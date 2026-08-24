# -*- coding: utf-8 -*-
r"""ca_guard.py — v2 (2026-07-27) · 기업행위(CA) 오염으로부터 '수익률 크기' 계산을 보호

배경(v1):
  월봉 캐시 CA 미조정 확정. 가격비율만으로 하는 자동 역조정은 그라운드트루스 검증에서
  큰불일치를 오히려 늘려('과조정') 배포 기각 → 레벨을 추정하지 말고 CA 의심 '월수익'만
  윈저/플래그해 크기 왜곡을 차단. rank-IC는 원래 강건하므로 손대지 않음.

v2 추가 배경(수정주가 재수집 이후):
  조정본을 확보했으나 **잔여 점프**가 남음(KOSPI 320건 · KOSDAQ 863건). 표본조사 결과
  KOSDAQ 441건 중 412건 영구(진짜 CA·조정본이 맞음) / 29건 되돌림(가짜·데이터 오류).
  → 따라서 v2의 원칙은 "전부 자르기"가 아니라 **되돌림만 결측 처리 + 나머지는 윈저**다.

v2 API:
  jump_ratios(px)                   전월대비 비율 계산(long: code,ym,close)
  flag_ca(ratio, tol)               정수배 점프 플래그 (v1 호환)
  classify_jumps(px, ...)           점프를 영구/되돌림으로 분류 → 진단 테이블
  winsor_returns(df, ...)           월별 [1%,99%] 윈저 (v1 호환, ret_col+"_w" 생성)
  guard_returns(df, ...)            되돌림 결측화 + 월별 윈저 동시 적용(권장 진입점)
  sensitivity(df, ...)              원본 vs 윈저 vs 가드 3원 비교(결론이 가드에 의존하는지)

⚠️ 이 모듈은 **레벨(수정주가)을 추정하지 않는다.** 진짜 조정은 벤더/거래소 팩터의 몫이고,
   여기는 "남은 오염이 크기 결론을 뒤집지 못하게" 막는 방어선이다.
⚠️ 오탐 주의: 조정본에서 r≈2.0은 '진짜 2배 상승'일 수도 있다(특히 R=2). 그래서 기본정책은
   삭제가 아니라 윈저이며, 결측화는 '되돌림 왕복'이 확인된 경우로 한정한다.
⚠️ 정보·검증용 · 투자자문 아님.
"""
import numpy as np, pandas as pd

# ────────────────────────────────────────────────── v1 호환 API
def flag_ca(ratio, tol=0.03):
    """비율 시리즈에서 정수배(R 또는 1/R, R=2..20) 근방을 True로."""
    r = pd.to_numeric(ratio, errors="coerce")
    f = pd.Series(False, index=r.index)
    for R in range(2, 21):
        f |= (r.sub(R).abs() < tol * R)
        f |= (r.sub(1.0 / R).abs() < tol * (1.0 / R))
    return f

def flag_suspect(ratio, tol=0.03, rmax=20, extreme=5.0):
    """CA 의심 플래그 v2 = 정수배(2..rmax) **또는** 극단배율(≥extreme, ≤1/extreme).

    왜 정수배만으론 부족한가(2026-07-27 실측):
      조정본 2015~ 창에서 최대 배율이 KOSPI 57.7배·KOSDAQ 153.8배였는데 v1의 R=2..20
      스캔이 이를 **놓쳤다**(감자·액면병합 의심). 게다가 R이 커지면 tol*R>1 이 되어
      "정수 근방" 판정 자체가 정보가 없어진다(R>33에서 무의미) — 정수성 대신 **크기**로
      잡고, 진짜/가짜는 되돌림 구조로 가려야 한다.
    """
    r = pd.to_numeric(ratio, errors="coerce")
    f = flag_ca(r, tol) if rmax >= 2 else pd.Series(False, index=r.index)
    if extreme:
        f |= (r >= extreme) | (r <= 1.0 / extreme)
    return f.fillna(False)

def winsor_returns(df, ret_col="fwd_ret", by="ym", lo=0.01, hi=0.99):
    """월별 횡단면 [lo,hi] 분위 윈저. 새 컬럼 ret_col+'_w' 추가(원본 보존)."""
    df = df.copy()
    def w(s):
        l, h = s.quantile([lo, hi])
        return s.clip(l, h)
    df[ret_col + "_w"] = df.groupby(by)[ret_col].transform(w)
    return df

# ────────────────────────────────────────────────── v2: 점프 진단
def jump_ratios(px, code_col="code", ym_col="ym", px_col="close"):
    """long 가격패널 → 전월대비 비율(ratio) 컬럼 추가. 결측·0 가격은 NaN."""
    d = px[[code_col, ym_col, px_col]].copy()
    d[px_col] = pd.to_numeric(d[px_col], errors="coerce").replace(0, np.nan)
    d = d.dropna(subset=[px_col]).sort_values([code_col, ym_col])
    d["ratio"] = d.groupby(code_col)[px_col].transform(lambda s: s / s.shift(1))
    return d

def classify_jumps(px, code_col="code", ym_col="ym", px_col="close",
                   tol=0.03, revert_tol=0.10, extreme=5.0):
    """정수배 점프를 '영구(permanent)' vs '되돌림(reverting)'으로 분류.

    되돌림 = 왕복. 다음 달 비율과 곱이 ≈1 (앞다리) **또는** 전월 비율과 곱이 ≈1 (뒷다리).
             → 두 다리를 모두 reverting으로 표시하므로, 오염된 '두 달'이 그대로 키가 된다.
    영구  = 점프 후 되돌아오지 않음 → 벤더가 back-adjust 하지 않은 진짜 CA(또는 진짜 급등락).
    반환: DataFrame[code, ym, ratio, prev_ratio, next_ratio, kind]
    """
    d = jump_ratios(px, code_col, ym_col, px_col)
    d["next_ratio"] = d.groupby(code_col)["ratio"].shift(-1)
    d["prev_ratio"] = d.groupby(code_col)["ratio"].shift(1)
    j = d[flag_suspect(d["ratio"], tol, extreme=extreme)].copy()
    cols = [code_col, ym_col, "ratio", "prev_ratio", "next_ratio", "kind"]
    if not len(j):
        return j.assign(kind=pd.Series(dtype=str))[cols]
    fwd_rt = (j["ratio"] * j["next_ratio"]).sub(1.0).abs() < revert_tol   # 앞다리
    bwd_rt = (j["ratio"] * j["prev_ratio"]).sub(1.0).abs() < revert_tol   # 뒷다리
    j["kind"] = np.where(fwd_rt.fillna(False) | bwd_rt.fillna(False),
                         "reverting", "permanent")      # 판정불가(끝단)는 보수적으로 permanent
    return j[cols].reset_index(drop=True)

def contaminated_keys(jumps, code_col="code", ym_col="ym", convention="ret", months=None):
    """되돌림 점프 → 오염된 (code, 수익률월) 키. 수익률 컬럼의 시간규약을 맞추는 어댑터.

    convention="ret" : ret(ym) = close(ym)/close(ym-1)-1  → 점프월이 그대로 오염월
    convention="fwd" : ret(ym) = close(ym+1)/close(ym)-1  → 점프월의 **한 달 전**이 오염월
    months: 전체 월 정렬 목록(미지정 시 jumps 안의 월만 사용)
    """
    r = jumps[jumps["kind"] == "reverting"][[code_col, ym_col]].copy()
    if not len(r):
        return r
    if convention == "ret":
        return r.reset_index(drop=True)
    order = sorted(set(months) if months is not None else set(jumps[ym_col]))
    pos = {m: i for i, m in enumerate(order)}
    out = []
    for c, m in zip(r[code_col].astype(str), r[ym_col].astype(str)):
        i = pos.get(m)
        if i is not None and i - 1 >= 0:
            out.append((c, order[i - 1]))
    return pd.DataFrame(out, columns=[code_col, ym_col])

# ────────────────────────────────────────────────── v2: 통합 가드
def guard_returns(df, ret_col="fwd_ret", by="ym", code_col="code",
                  lo=0.01, hi=0.99, bad_pairs=None, hard_cap=None):
    """되돌림 구간 결측화 + 월별 윈저를 한 번에. 새 컬럼 ret_col+'_g' 생성.

    bad_pairs: 오염된 (code, 수익률월) 목록 — contaminated_keys()로 시간규약을 맞춘 것.
               해당 셀의 수익률을 **결측 처리**(임의 대체 금지 원칙).
    hard_cap : 예 3.0 → |1+r| 이 3배 넘는 월수익을 결측(선택, 기본 미사용).
    """
    d = df.copy()
    d[ret_col] = pd.to_numeric(d[ret_col], errors="coerce")
    d["ca_dropped"] = False
    if bad_pairs is not None and len(bad_pairs):
        bp = bad_pairs[[code_col, by]].copy() if isinstance(bad_pairs, pd.DataFrame) \
             else pd.DataFrame(list(bad_pairs), columns=[code_col, by])
        allbad = set(zip(bp[code_col].astype(str), bp[by].astype(str)))
        mask = pd.Series(list(zip(d[code_col].astype(str), d[by].astype(str))),
                         index=d.index).isin(allbad)
        d.loc[mask, "ca_dropped"] = True
        d.loc[mask, ret_col] = np.nan
    if hard_cap:
        cap = d[ret_col].abs() > (hard_cap - 1.0)
        d.loc[cap, "ca_dropped"] = True
        d.loc[cap, ret_col] = np.nan
    def w(s):
        l, h = s.quantile([lo, hi])
        return s.clip(l, h)
    d[ret_col + "_g"] = d.groupby(by)[ret_col].transform(w)
    return d

def sensitivity(df, ret_col="fwd_ret", by="ym", code_col="code", bad_pairs=None,
                lo=0.01, hi=0.99):
    """원본 · 윈저만 · 가드(되돌림결측+윈저) 3원 비교표. 결론이 가드에 의존하는지 본다."""
    a = pd.to_numeric(df[ret_col], errors="coerce")
    w = winsor_returns(df, ret_col, by, lo, hi)[ret_col + "_w"]
    g = guard_returns(df, ret_col, by, code_col, lo, hi, bad_pairs)[ret_col + "_g"]
    def stat(s, name):
        s = pd.Series(s).dropna()
        return {"기준": name, "n": len(s), "월평균%": round(s.mean() * 100, 3),
                "표준편차%": round(s.std(ddof=0) * 100, 2),
                "왜도": round(s.skew(), 2), "최대%": round(s.max() * 100, 1),
                "최소%": round(s.min() * 100, 1)}
    return pd.DataFrame([stat(a, "원본"), stat(w, "윈저만"), stat(g, "가드(되돌림결측+윈저)")])

# ────────────────────────────────────────────────── 적재 가드 (2026-07-27 신설)
# 사고 기록: 파일명은 `_월봉종가캐시_KOSPI_adj.csv`인데 **내용은 미조정 raw**였다.
# 파일명·경로·수정시각 어느 것도 내용을 보증하지 않는다. 그래서 적재 즉시 카나리로 검증한다.
# 카나리는 '조정본이면 반드시 이 값 근처'인 실측 셀이다(2026-07-27 PC 재수집본 기준):
#   KOSPI  005930 2018-04 → 조정 53,000원 / 미조정 2,650,000원 (50:1 액면분할)
#   ⛔ 2026-07-28 폐기 — KOSDAQ 064550 (조정 12,750 / 미조정 51,000 "4:1")
#      51,000원은 **어디서도 관측되지 않은 계산값**이었다: ca_flags 의 ×2 두 건(2021-08·2023-02)을
#      곱해 12,750×4 로 채운 것. 그런데 2021-08 은 일별로 35,000→74,000 연속 상승한 **진짜 랠리**
#      (가격비율 휴리스틱 오탐)이고, 2018-04-30 실제 거래 종가는 원주가 일봉·미조정 월봉·KIS 양쪽
#      플래그 **모두 12,750** 이었다. 즉 raw == adj 인 셀이어서 **조정/미조정을 판별할 수 없었고**,
#      max_close 25,000 은 미조정 KOSDAQ 패널도 그대로 통과시키는 **거짓음성 구멍**이었다.
#   KOSDAQ 098460(고영) 2018-04 → 조정 20,360원 / 미조정 101,800원 (5:1, 2021-04-13 액면분할)
#      두 값 모두 실측: 미조정=종목일봉_30년_KOSDAQ.csv 2018-04-30 종가, 조정=_월봉종가캐시_KOSDAQ_adj.csv
#      일봉에 121,500 → 28,300 단일일 불연속 확인(랠리가 아니라 진짜 자본이벤트)
# 임계값은 두 값 사이에 둔다. 카나리가 패널에 없으면 '검증 불가'이지 '통과'가 아니다.
ADJ_CANARY = {
    "KOSPI":  {"code": "005930", "ym": "2018-04", "max_close": 100_000, "adj": 53_000, "raw": 2_650_000},
    "KOSDAQ": {"code": "098460", "ym": "2018-04", "max_close":  45_000, "adj": 20_360, "raw":   101_800},
}

def assert_adjusted(px, market, code_col="code", ym_col="ym", px_col="close",
                    where="", strict=True):
    """조정본이라고 주장하는 패널이 정말 조정본인지 카나리 셀로 확인한다.

    반환: (통과여부, 메시지). strict=True면 실패 시 AssertionError.
    카나리가 패널에 없으면 통과로 치지 않고 경고만 남긴다(창을 좁게 잘랐을 때 정상).
    """
    tag = f"[{market}]{(' ' + where) if where else ''}"
    c = ADJ_CANARY.get(str(market).upper())
    if c is None:
        return True, f"{tag} 카나리 미정의 — 검증 생략"
    code = px[code_col].astype(str).str.zfill(6)
    hit = px[(code == c["code"]) & (px[ym_col].astype(str) == c["ym"])][px_col]
    hit = pd.to_numeric(hit, errors="coerce").dropna()
    if hit.empty:
        msg = (f"⚠️ {tag} 조정본 카나리 {c['code']} {c['ym']} 없음 — "
               f"**검증 불가**(통과 아님). 창을 좁게 잘랐다면 정상.")
        print(msg); return None, msg
    v = float(hit.iloc[0])
    if v >= c["max_close"]:
        msg = (f"⛔ {tag} 조정본이 아니다 — {c['code']} {c['ym']} 종가 {v:,.0f}원 "
               f"(조정본이면 ≈{c['adj']:,}원, 미조정이면 ≈{c['raw']:,}원). "
               f"파일명이 `_adj`여도 내용은 미조정이다. 2026-07-26 캐시 오염 사고와 동일 유형.")
        print(msg)
        if strict: raise AssertionError(msg)
        return False, msg
    msg = f"✅ {tag} 조정본 확인 — {c['code']} {c['ym']} {v:,.0f}원 (< {c['max_close']:,})"
    print(msg); return True, msg

# ────────────────────────────────────────────────── 셀프테스트
def _selftest():
    ok = True
    # ① 되돌림 vs 영구 분류: A=영구 4배 점프, B=왕복(가짜), C=정상
    rows = []
    for m, p in zip(["2020-01", "2020-02", "2020-03", "2020-04"], [100, 400, 410, 405]):
        rows.append(("A", m, p))                     # 영구
    for m, p in zip(["2020-01", "2020-02", "2020-03", "2020-04"], [100, 300, 101, 103]):
        rows.append(("B", m, p))                     # 왕복(가짜)
    for m, p in zip(["2020-01", "2020-02", "2020-03", "2020-04"], [100, 105, 110, 108]):
        rows.append(("C", m, p))                     # 정상
    px = pd.DataFrame(rows, columns=["code", "ym", "close"])
    cj = classify_jumps(px)
    got = {(c, m): k for c, m, k in zip(cj["code"], cj["ym"], cj["kind"])}
    want = {("A", "2020-02"): "permanent",              # 4배 후 유지 → 진짜 CA
            ("B", "2020-02"): "reverting",              # 왕복 앞다리
            ("B", "2020-03"): "reverting"}              # 왕복 뒷다리
    t1 = got == want                                     # C(정상)는 아예 안 잡혀야 함
    print(f"  ① 점프분류 영구/왕복양다리/정상무시: {'PASS' if t1 else 'FAIL'} ({got})")
    ok &= t1
    # ② 시간규약 어댑터: ret 규약은 점프월, fwd 규약은 한 달 전
    months = ["2020-01", "2020-02", "2020-03", "2020-04"]
    k_ret = contaminated_keys(cj, convention="ret")
    k_fwd = contaminated_keys(cj, convention="fwd", months=months)
    s_ret = set(zip(k_ret["code"], k_ret["ym"])); s_fwd = set(zip(k_fwd["code"], k_fwd["ym"]))
    t2 = s_ret == {("B", "2020-02"), ("B", "2020-03")} and s_fwd == {("B", "2020-01"), ("B", "2020-02")}
    print(f"  ② 규약 어댑터 ret/fwd: {'PASS' if t2 else 'FAIL'} (ret={sorted(s_ret)} fwd={sorted(s_fwd)})")
    ok &= t2
    # ③ 결측화가 지정 셀만 정확히 지우는지 (fwd 규약 패널)
    ret = pd.DataFrame({"code": ["B", "B", "B", "C", "C", "C"],
                        "ym": ["2020-01", "2020-02", "2020-03"] * 2,
                        "fwd_ret": [2.0, -0.663, 0.02, 0.05, 0.05, -0.02]})
    g = guard_returns(ret, bad_pairs=k_fwd)
    dropped = set(zip(g.loc[g["ca_dropped"], "code"], g.loc[g["ca_dropped"], "ym"]))
    t3 = dropped == {("B", "2020-01"), ("B", "2020-02")} and g["fwd_ret_g"].isna().sum() == 2
    print(f"  ③ 오염 셀만 결측화: {'PASS' if t3 else 'FAIL'} ({sorted(dropped)})")
    ok &= t3
    # ④ 윈저가 원본을 파괴하지 않고 새 컬럼으로만 들어가는지
    w = winsor_returns(ret)
    t4 = "fwd_ret_w" in w.columns and w["fwd_ret"].equals(ret["fwd_ret"])
    print(f"  ④ 원본 보존 + 윈저 컬럼 생성: {'PASS' if t4 else 'FAIL'}")
    ok &= t4
    # ⑤ 민감도표 3행 + 가드가 가짜점프(+200%)를 실제로 죽였는지
    s = sensitivity(ret, bad_pairs=k_fwd)
    t5 = len(s) == 3 and s["월평균%"].notna().all() and s.loc[2, "최대%"] < s.loc[0, "최대%"]
    print(f"  ⑤ 민감도 3원 + 가드효과: {'PASS' if t5 else 'FAIL'} (원본최대 {s.loc[0,'최대%']}% → 가드 {s.loc[2,'최대%']}%)")
    ok &= t5
    # ⑥ 적재 가드: 미조정본을 조정본이라 주장하면 반드시 걸려야 한다
    good = pd.DataFrame([("005930", "2018-04", 53000.0)], columns=["code", "ym", "close"])
    bad  = pd.DataFrame([("005930", "2018-04", 2650000.0)], columns=["code", "ym", "close"])
    none = pd.DataFrame([("000660", "2018-04", 80000.0)], columns=["code", "ym", "close"])
    t6a = assert_adjusted(good, "KOSPI", where="셀프테스트")[0] is True
    try:
        assert_adjusted(bad, "KOSPI", where="셀프테스트"); t6b = False
    except AssertionError:
        t6b = True
    t6c = assert_adjusted(none, "KOSPI", where="셀프테스트")[0] is None   # 없으면 '통과' 아님
    t6 = t6a and t6b and t6c
    print(f"  ⑥ 적재 카나리(조정 PASS/미조정 차단/부재는 미판정): {'PASS' if t6 else 'FAIL'}")
    ok &= t6
    print("ca_guard v2 셀프테스트:", "전부 PASS ✅" if ok else "실패 있음 ❌")
    return ok

if __name__ == "__main__":
    print("ca_guard v2 — 레벨 추정 없이 CA 잔여 오염의 '크기 왜곡'만 차단")
    _selftest()
