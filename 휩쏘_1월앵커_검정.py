# -*- coding: utf-8 -*-
r"""휩쏘_1월앵커_검정.py — 열린 과제 #2.

질문: 9~10월 진입분에 대해 "일반 종목은 1월 강세에 정리 / 밸류 태그만 4월까지 연장"을
      카드에 명문화할 근거가 있는가?

[사전등록 · 정책 정의]  (신호·진입가·초기손절·목표는 전부 고정. 청산 달력만 바꾼다)
  B0  카드(현행)        : 목표/손절/트레일, 40봉 상한, 전량
  B0b 카드+2단(과제1)   : 목표시 50% 실현 + 잔여 트레일12%·본전스톱, 126봉 상한
  A2  2단 + 1월 데드라인 : 잔여를 '이듬해 1월 마지막 거래일' 종가까지
  A3  2단 + 4월 데드라인 : 잔여를 '이듬해 4월 마지막 거래일' 종가까지
  A4  2단 + 밸류분기     : 밸류태그 있으면 4월, 없으면 1월
  C1  달력보유 1월       : 목표 무시. 초기손절만 두고 1월 마지막 거래일 종가 청산
  C2  달력보유 4월       : 동일, 4월 마지막 거래일   ← 기존 기각(중앙 −10.8%) 재확인
  C3  달력보유 밸류분기
  D1  순수 달력보유 4월  : 손절조차 없음 — 기존 판정문 수치 재현용

⚠️ 표본이 작다(9~10월 진입 370건, 밸류태그 46건). CI를 반드시 함께 읽을 것.
"""
import os, sys, gc, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = "/home/claude/jq"; UP = "/mnt/user-data/uploads/진우퀀트"
MIN_BARS = 260


def era_limit(d): return 0.30 if d >= "2015-06-15" else 0.15


def back_adjust(o, h, l, c, dts):
    n = len(c); adj = np.ones(n); cum = 1.0
    for i in range(n - 1, 0, -1):
        p, q = c[i - 1], c[i]
        if p > 0 and q > 0:
            r = q / p; lim = era_limit(dts[i]) + 0.03
            if r < (1 - lim) or r > (1 + lim): cum *= r
        adj[i - 1] = cum
    return o * adj, h * adj, l * adj, c * adj


def line_series(dates, c):
    s = pd.Series(c, index=pd.to_datetime(dates))
    wk = s.resample("W-FRI").last().dropna(); mo = s.resample("ME").last().dropna()
    wkm = wk.rolling(60, min_periods=60).mean(); mom = mo.rolling(10, min_periods=10).mean()
    di = s.index
    return (wkm.reindex(di.union(wkm.index)).ffill().reindex(di).values,
            mom.reindex(di.union(mom.index)).ffill().reindex(di).values)


def two_stage(entry, target, stop0, trail, h, l, c, t, n, end, split=0.5, rtrail=0.12):
    """카드 1단 + (목표 도달 시) 잔여 트레일·본전스톱. end = 마지막 허용 봉 인덱스."""
    peak = entry; stop = stop0
    for j in range(t + 1, end + 1):
        if l[j] <= stop: return stop / entry - 1, "손절/트레일"
        if h[j] >= target:
            first = target / entry - 1
            if split >= 1.0: return first, "목표"
            rpeak = max(peak, h[j]); rstop = max(rpeak * (1 - rtrail), entry)
            for k in range(j + 1, end + 1):
                if l[k] <= rstop:
                    return split * first + (1 - split) * (rstop / entry - 1), "2단트레일"
                rpeak = max(rpeak, h[k]); rstop = max(rstop, max(rpeak * (1 - rtrail), entry))
            return split * first + (1 - split) * (c[end] / entry - 1), "2단데드라인"
        peak = max(peak, h[j]); stop = max(stop, peak * (1 - trail))
    return c[end] / entry - 1, "데드라인"


def two_stage_hold(entry, target, stop0, trail, h, l, c, t, n, end, split=0.5):
    """형의 문장에 가장 충실한 구현: 목표시 split 실현 → 잔여는 트레일 없이
       '본전 손절'만 두고 달력 데드라인까지 보유."""
    peak = entry; stop = stop0
    for j in range(t + 1, end + 1):
        if l[j] <= stop: return stop / entry - 1, "손절/트레일"
        if h[j] >= target:
            first = target / entry - 1
            for k in range(j + 1, end + 1):
                if l[k] <= entry:
                    return split * first + (1 - split) * 0.0, "본전이탈"
            return split * first + (1 - split) * (c[end] / entry - 1), "달력보유"
        peak = max(peak, h[j]); stop = max(stop, peak * (1 - trail))
    return c[end] / entry - 1, "데드라인"


def cal_hold(entry, stop0, l, c, t, end, use_stop=True):
    """달력 보유: 목표 없음. use_stop이면 초기손절만 유지."""
    for j in range(t + 1, end + 1):
        if use_stop and l[j] <= stop0: return stop0 / entry - 1, "손절"
    return c[end] / entry - 1, "달력"


def main():
    L9 = pd.read_csv(os.path.join(UP, "휩쏘_910_리스트.csv"), dtype={"code": str})
    L9.columns = [x.strip().lstrip("﻿") for x in L9.columns]
    L9["code"] = L9["code"].str.zfill(6); L9["출발일"] = L9["출발일"].astype(str)
    L9["밸류"] = L9["밸류"].fillna("")
    key = {(r["code"], r["출발일"]): r for _, r in L9.iterrows()}
    targets = L9.groupby("code")["출발일"].apply(set).to_dict()
    print(f"9~10월 진입 {len(L9)}건 · 종목 {len(targets)} · 밸류태그 {(L9['밸류']!='').sum()}건", flush=True)

    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    rows = []
    for mk in ("KOSPI", "KOSDAQ"):
        D = pd.read_csv(os.path.join(HERE, f"종목일봉_30년_{mk}.csv"), dtype=dt)
        D.columns = [x.strip().lstrip("﻿") for x in D.columns]
        D["code"] = D["code"].str.zfill(6)
        D = D[D["code"].isin(targets.keys())]
        for code, g in D.groupby("code", sort=False):
            want = targets.get(code)
            if not want: continue
            g = g.sort_values("date").reset_index(drop=True)
            g = g[~((g["open"] == 0) & (g["volume"] == 0))].reset_index(drop=True)
            if len(g) < MIN_BARS: continue
            dts = g["date"].values.astype(str)
            o = g["open"].values.astype(float); h = g["high"].values.astype(float)
            l = g["low"].values.astype(float); c = g["close"].values.astype(float)
            o, h, l, c = back_adjust(o, h, l, c, dts)
            n = len(c); cs = pd.Series(c)
            ma240 = cs.rolling(240, min_periods=240).mean().values
            w60, m10 = line_series(g["date"].values, c)
            lines = np.vstack([w60, m10, ma240])
            pos = {d: i for i, d in enumerate(dts)}
            for d in want:
                t = pos.get(d)
                if t is None or t + 1 >= n or not (np.isfinite(c[t]) and c[t] > 0): continue
                r0 = key[(code, d)]
                cum2 = c[t] / c[t - 2] - 1
                lv = lines[:, t]; dist = c[t] / lv - 1; fin = np.isfinite(dist)
                if not fin.any(): continue
                ki = int(np.nanargmin(np.where(fin, np.abs(dist), np.inf))); keyv = lv[ki]
                entry = c[t]
                if r0["유형"] == "A":
                    pre = c[t] / (1 + cum2); target = entry + (pre - entry) * 0.5
                    below = keyv if (np.isfinite(keyv) and keyv < entry) else l[t]
                    stop0 = below * 0.95; trail = 0.12
                else:
                    target = float(np.max(h[max(0, t - 59):t + 1]))
                    below = keyv if (np.isfinite(keyv) and keyv < entry) else l[t]
                    stop0 = below * 0.97; trail = 0.15

                ny = int(d[:4]) + 1
                def last_idx(limit):
                    ii = np.where(dts <= limit)[0]
                    return int(ii[-1]) if len(ii) else None
                i_jan = last_idx(f"{ny}-01-31"); i_apr = last_idx(f"{ny}-04-30")
                done_jan = i_jan is not None and dts[-1] >= f"{ny}-01-31"
                done_apr = i_apr is not None and dts[-1] >= f"{ny}-04-30"
                if not (done_jan and done_apr):
                    continue
                is_val = bool(str(r0["밸류"]))
                e40 = min(t + 40, n - 1); e126 = min(t + 126, n - 1)
                rec = dict(출발일=d, code=code, name=r0["name"], 유형=r0["유형"], 국면=r0["국면"],
                           밸류=str(r0["밸류"]), 밸류여부=is_val,
                           봉_1월=i_jan - t, 봉_4월=i_apr - t)
                rec["B0_카드"], _ = two_stage(entry, target, stop0, trail, h, l, c, t, n, e40, split=1.0)
                rec["B0b_2단126"], rec["B0b_how"] = two_stage(entry, target, stop0, trail, h, l, c, t, n, e126)
                rec["A2_2단1월"], _ = two_stage(entry, target, stop0, trail, h, l, c, t, n, i_jan)
                rec["A3_2단4월"], _ = two_stage(entry, target, stop0, trail, h, l, c, t, n, i_apr)
                rec["A4_2단밸류분기"] = rec["A3_2단4월"] if is_val else rec["A2_2단1월"]
                rec["E1_잔여보유1월"], rec["E1_how"] = two_stage_hold(entry, target, stop0, trail, h, l, c, t, n, i_jan)
                rec["E2_잔여보유4월"], _ = two_stage_hold(entry, target, stop0, trail, h, l, c, t, n, i_apr)
                rec["E3_잔여보유밸류분기"] = rec["E2_잔여보유4월"] if is_val else rec["E1_잔여보유1월"]
                rec["C1_달력1월"], _ = cal_hold(entry, stop0, l, c, t, i_jan, True)
                rec["C2_달력4월"], _ = cal_hold(entry, stop0, l, c, t, i_apr, True)
                rec["C3_달력밸류분기"] = rec["C2_달력4월"] if is_val else rec["C1_달력1월"]
                rec["D1_순수4월"], _ = cal_hold(entry, stop0, l, c, t, i_apr, False)
                rec["D0_순수1월"], _ = cal_hold(entry, stop0, l, c, t, i_jan, False)
                rows.append(rec)
        del D; gc.collect()
        print(f"  {mk} 누적 {len(rows)}", flush=True)

    R = pd.DataFrame(rows)
    R.to_csv(os.path.join(HERE, "휩쏘_1월앵커_이벤트.csv"), index=False, encoding="utf-8-sig")
    print(f"\n저장: 휩쏘_1월앵커_이벤트.csv ({len(R)}건 · 1월·4월 창 완결분만)")

    POL = ["B0_카드", "B0b_2단126", "A2_2단1월", "A3_2단4월", "A4_2단밸류분기",
           "E1_잔여보유1월", "E2_잔여보유4월", "E3_잔여보유밸류분기",
           "C1_달력1월", "C2_달력4월", "C3_달력밸류분기", "D0_순수1월", "D1_순수4월"]
    R["연"] = R["출발일"].str[:4].astype(int)

    def boot(a, b, yrs, n=6000, seed=23):
        rng = np.random.default_rng(seed); ys = np.array(sorted(set(yrs)))
        ix = {y: np.where(yrs == y)[0] for y in ys}; out = np.empty(n)
        for i in range(n):
            p = rng.choice(ys, size=len(ys), replace=True)
            s = np.concatenate([ix[y] for y in p])
            out[i] = np.nanmean(a[s]) - np.nanmean(b[s])
        return (*np.percentile(out, [2.5, 97.5]) * 100, float((out > 0).mean()))

    def block(sub, title, base="B0b_2단126"):
        if len(sub) < 15: return
        print("\n" + "=" * 78); print(f"[{title}] n={len(sub)}  (기준={base})")
        print(f"{'정책':<18}{'평균':>8}{'중앙':>8}{'승률':>8}{'표준편차':>9}{'Δ평균':>8}{'   부트95%CI':>20}{'P(Δ>0)':>8}")
        bv = sub[base].values
        for p in POL:
            s = sub[p].dropna()
            if p == base:
                print(f"{p:<18}{s.mean()*100:>+8.2f}{s.median()*100:>+8.2f}{(s>0).mean()*100:>7.1f}%{s.std()*100:>9.1f}{'기준':>8}")
                continue
            lo, hi, pg = boot(sub[p].values, bv, sub["연"].values)
            mark = " ★" if lo > 0 else (" ✗" if hi < 0 else "")
            print(f"{p:<18}{s.mean()*100:>+8.2f}{s.median()*100:>+8.2f}{(s>0).mean()*100:>7.1f}%{s.std()*100:>9.1f}"
                  f"{s.mean()*100-np.nanmean(bv)*100:>+8.2f}   [{lo:+6.2f},{hi:+6.2f}]{pg:>8.1%}{mark}")

    block(R, "9~10월 진입 전체")
    block(R[R["국면"] == "실행"], "🟢실행 국면만")
    block(R[R["밸류여부"]], "밸류태그 보유분")
    block(R[~R["밸류여부"]], "밸류태그 없음")
    print("\n[보유기간] 1월 데드라인까지 중앙 %.0f봉 · 4월까지 중앙 %.0f봉"
          % (R["봉_1월"].median(), R["봉_4월"].median()))
    print("[2단 종료유형]", dict(R["B0b_how"].value_counts()))
    print("[E1 잔여보유 종료유형]", dict(R["E1_how"].value_counts()))
    hit = R[R["B0b_how"] == "2단트레일"]
    print(f"[데드라인 구속력] 2단 잔여가 살아있는 {len(hit)}건 중, 트레일이 1월 데드라인보다 먼저 발동한 비율: "
          f"{(R['B0b_how']!='2단데드라인').mean()*100:.1f}% (데드라인 발동 {int((R['B0b_how']=='2단데드라인').sum())}건)")


if __name__ == "__main__":
    main()
