"""
jq_v372_bridge.py  —  진우퀀트 실제 점수 체계(score_v37_2) ↔ stats_v1/regime_overlay 브리지
=============================================================================================
score_v37_2.py 의 산출물(v37_2_scores_latest.csv)과 '포인트 합 + 등급 선택 + cap 동일가중'
방식을 그대로 재현. 개별 팩터 컬럼(Mom12·BAB·Echo…)이 있으므로 regime 재점수화·leave-one-out 가능.

production 공식(원본과 동일):
  체력_최종 = 체력_12점 + ModF + FAR + Sloan + Mom12 + BAB + NOA + Echo
  grade: ≥14 S+, ≥12 S, ≥9 A, ≥6 B, ≥3 C, ≥0 D, else F
  비중: S+/S/A 동일가중 → 종목 cap 15% → 섹터 cap 35% → 정규화
의존성: pandas, numpy
"""
import numpy as np
import pandas as pd

# score_v37.py JINWOO_v37 와 동일 (종목→코드·산업)
JINWOO_UNIVERSE = {
    "삼성전자":("005930","반도체"), "SK하이닉스":("000660","반도체"), "한미반도체":("042700","반도체"),
    "알테오젠":("196170","바이오"), "기아":("000270","자동차"), "NAVER":("035420","인터넷"),
    "카카오":("035720","인터넷"), "한화에어로":("012450","방산"), "LIG넥스원":("079550","방산"),
    "KB금융":("105560","금융"), "KT&G":("033780","필수소비재"), "삼성SDI":("006400","2차전지"),
    "아모레퍼시픽":("090430","화장품"), "삼성물산":("028260","종합상사"), "삼양식품":("003230","식품"),
    "ISC":("095340","반도체"), "두산에너빌리티":("034020","원전"), "NH투자증권":("005940","금융"),
}
UNIVERSE_18 = list(JINWOO_UNIVERSE)
FACTOR_COLS = ["ModF", "FAR", "Sloan", "Mom12", "BAB", "NOA", "Echo"]   # 체력_12점에 더해지는 항
TARGET_GRADES = {"S+", "S", "A"}

def grade(score):
    if score >= 14: return "S+"
    if score >= 12: return "S"
    if score >= 9:  return "A"
    if score >= 6:  return "B"
    if score >= 3:  return "C"
    if score >= 0:  return "D"
    return "F"

def load_scores_csv(path):
    """v37_2_scores_latest.csv → DataFrame (종목 index)."""
    df = pd.read_csv(path)
    return df.set_index("종목")

def recompute_total(df):
    """체력_12점 + 모든 팩터 → 체력_최종·등급 재계산 (원본 공식 검증/재현용)."""
    df = df.copy()
    df["체력_최종"] = df["체력_12점"] + df[FACTOR_COLS].sum(axis=1)
    df["등급"] = df["체력_최종"].apply(grade)
    return df

def rescore_regime(df, echo_w=1.2, bab_mult=1.0, cur_echo_w=1.0):
    """
    ① C1: regime ON 시 Echo 가중↑·BAB 가중↓ 후 재점수화.
    Echo 컬럼은 이미 cur_echo_w(기본 1.0)로 저장됨 → echo_w 로 환산.
    """
    df = df.copy()
    df["Echo"] = df["Echo"] * (echo_w / cur_echo_w)
    df["BAB"]  = df["BAB"] * bab_mult
    return recompute_total(df)

def leave_one_out(df, drop_factor):
    """② 단순화: 한 팩터를 빼고 재점수화 → 한계기여 측정용."""
    df = df.copy()
    df[drop_factor] = 0.0
    return recompute_total(df)

def to_weights(df, stock_cap=0.15, sector_cap=0.35, sector_col="산업"):
    """S+/S/A 동일가중 → 종목·섹터 cap → 정규화 (원본 apply_weight_caps 재현). 반환 Series(비중)."""
    picks = df.index[df["등급"].isin(TARGET_GRADES)].tolist()
    if not picks:
        return pd.Series(dtype=float)
    raw = 1.0/len(picks)
    w = {p: min(raw, stock_cap) for p in picks}
    sec_tot = {}
    for p in picks:
        s = df.loc[p, sector_col]; sec_tot[s] = sec_tot.get(s, 0) + w[p]
    for s, tot in sec_tot.items():
        if tot > sector_cap:
            sc = sector_cap/tot
            for p in picks:
                if df.loc[p, sector_col] == s: w[p] *= sc
    tot = sum(w.values())
    return pd.Series({k: v/tot for k, v in w.items()}) if tot > 0 else pd.Series(w)

# ============ self-test (합성 — 실제 CSV 스키마 모사) ============
if __name__ == "__main__":
    rng = np.random.default_rng(0)
    rows = []
    for nm,(code,sec) in JINWOO_UNIVERSE.items():
        rows.append({"종목":nm,"코드":code,"산업":sec,
                     "체력_12점":round(rng.uniform(3,11),2),"ModF":int(rng.integers(-3,4)),
                     "FAR":int(rng.choice([-2,-1,0,1,2])),"Sloan":int(rng.integers(-2,2)),
                     "Mom12":int(rng.choice([-2,-1,0,1,2])),"BAB":int(rng.choice([-2,-1,0,1,2])),
                     "NOA":int(rng.integers(-2,3)),"Echo":int(rng.choice([-1,0,1]))})
    df = pd.DataFrame(rows).set_index("종목")
    df = recompute_total(df)
    print("=== 재점수화 검증 ===")
    print(f"종목수={len(df)} | 등급분포={df['등급'].value_counts().to_dict()}")
    w0 = to_weights(df); print(f"baseline 비중합={w0.sum():.3f} 최대종목={w0.max()*100:.1f}% 종목수={len(w0)}")
    sec_sum = w0.groupby(df.loc[w0.index,'산업']).sum()
    print(f"최대 섹터비중={sec_sum.max()*100:.1f}% (cap 35%)")

    print("\n=== ① regime ON 재점수화 (Echo 1.0→1.5, BAB×0) ===")
    dON = rescore_regime(df, echo_w=1.5, bab_mult=0.0)
    moved = (dON['등급'] != df['등급']).sum()
    print(f"등급 변동 종목수={moved} | ON 비중합={to_weights(dON).sum():.3f}")

    print("\n=== ② leave-one-out (BAB 제거) ===")
    dB = leave_one_out(df, "BAB")
    d_avg=float((dB["체력_최종"]-df["체력_최종"]).mean()); n_chg=int((dB["등급"]!=df["등급"]).sum())
    print(f"Δ체력 평균={d_avg:.2f} | 등급변동={n_chg}")
    print("\n[OK] jq_v372_bridge self-test 완료")
