#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""유니버스_규칙화_실행.py — 검증된 규칙의 '실행판': 현재 리스트 + 교체주기 민감도

검증 근거: 유니버스_규칙화_판정_2026-07-23.md (게이트 3/4, 낙폭제어 핵심).
규칙(고정): 시총 상위 pool100 중 12-1 모멘텀 상위 N(기본 30) EW + MA200 월간 방어(기본 50%현금).

  --now              현재(최근월) 편입 리스트 + 방어상태 산출 → 유니버스_규칙화_현재.csv
  --cadence-sweep    교체주기 1/2/3/6개월 × 방어 × 스왑캡 트레이드오프(30년)
  --N 30  --defense 50현금  --swap-cap 6

⚠️ 상폐포함 검증용·기계적 규칙 출력. 실현손익 아님. 투자자문 아님·책임 본인.
진우 스타일 메모: 월간이 규칙의 기본 엣지. '중장기 보유' 성향이면 분기교체+스왑캡으로
회전·세금을 낮추되(수익 일부 반납), MA200 방어는 월간 유지 권장(사이클 하강 보호).
"""
# §8-3(2026-07-27): tax 0.002→0.0015(실제 증권거래세) · slip 0.0005→0.002045(CS 실측 편도) → 왕복 0.300%→0.559%


# ── 경로 자립화 (2026-07-27) — 샌드박스 하드코딩 제거 ──────────────
import os as _os, glob as _glob
_JQ_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _jqroot():
    d = _JQ_HERE
    for _ in range(5):
        if _os.path.exists(_os.path.join(d, "종목시총_30년.csv")):
            return d
        d = _os.path.dirname(d)
    return _os.path.dirname(_JQ_HERE)


BASE = _os.environ.get("JQ_BASE", _jqroot())


def _jqfind(name):
    """이름으로 파일 자동탐색 (백업/보관 폴더 제외)."""
    for b in (BASE, _JQ_HERE, _os.getcwd()):
        hits = [h for h in _glob.glob(_os.path.join(b, "**", name), recursive=True)
                if not any(s in h for s in ("_백업", "_보관", "_archive", "__pycache__"))]
        if hits:
            return sorted(hits, key=len)[0]
    raise FileNotFoundError(f"{name} 를 못 찾음 (루트={BASE})")
# ────────────────────────────────────────────────────────────────

import os, sys, argparse, json, warnings
warnings.filterwarnings("ignore")  # pandas FutureWarning 등 무해한 경고 억제(계산 불변)
import numpy as np, pandas as pd
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None

def load_panel():
    frames = []
    for fn in ("_월봉종가캐시_KOSPI.csv", "_월봉종가캐시_KOSDAQ.csv"):
        p = _find(fn)
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6); frames.append(d)
    allc = pd.concat(frames, ignore_index=True)
    px = allc.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    return px, px.pct_change(fill_method=None).mask(lambda x: x.abs() > 1.0)

def load_mcap():
    p = _find("종목시총_30년.csv"); d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
    d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")

def load_ma200_regime():
    p = _find("kospi_index_daily.csv")
    if not p: return None
    d = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
    close = d["Close"]; sma = close.rolling(200).mean()
    above = (close >= sma); gap = (close / sma - 1)
    reg = pd.DataFrame({"above": above.resample("ME").last(), "gap": gap.resample("ME").last(),
                        "close": close.resample("ME").last(), "sma": sma.resample("ME").last()})
    reg.index = reg.index.strftime("%Y-%m")
    reg["sig"] = reg["above"].shift(1); reg["gap_prev"] = reg["gap"].shift(1)
    return reg

def name_map():
    m = {}
    p = _find("universe_rule30_latest.csv")
    if p:
        d = pd.read_csv(p, dtype=str)
        for _, r in d.iterrows(): m[str(r["code"]).zfill(6)] = r["name"]
    m.update({
        "005930":"삼성전자","000660":"SK하이닉스","005490":"POSCO홀딩스","015760":"한국전력","005380":"현대차",
        "000270":"기아","012330":"현대모비스","051910":"LG화학","373220":"LG에너지솔루션","006400":"삼성SDI",
        "207940":"삼성바이오로직스","068270":"셀트리온","035420":"NAVER","035720":"카카오","009540":"HD한국조선해양",
        "010140":"삼성중공업","042660":"한화오션","012450":"한화에어로","079550":"LIG넥스원","034020":"두산에너빌리티",
        "028260":"삼성물산","105560":"KB금융","055550":"신한지주","051900":"LG생활건강","090430":"아모레퍼시픽",
        "017670":"SK텔레콤","032830":"삼성생명","003550":"LG","096770":"SK이노베이션","010950":"S-Oil",
        "066570":"LG전자","011200":"HMM","247540":"에코프로비엠","086520":"에코프로","196170":"알테오젠",
        "042700":"한미반도체","033780":"KT&G","003230":"삼양식품","095340":"ISC","011070":"LG이노텍",
        "259960":"크래프톤","323410":"카카오뱅크","326030":"SK바이오팜","009150":"삼성전기","018260":"삼성에스디에스",
        "034220":"LG디스플레이","204320":"HL만도","329180":"HD현대중공업","267250":"HD현대","000100":"유한양행",
        "004020":"현대제철","097950":"CJ제일제당","139480":"이마트","069960":"현대백화점","267260":"HD현대일렉트릭",
        "278470":"에이피알","012510":"더존비즈온","010130":"고려아연","011790":"SKC","000810":"삼성화재",
        "086790":"하나금융지주","316140":"우리금융지주","024110":"기업은행","138040":"메리츠금융지주",
        "047810":"한국항공우주","064350":"현대로템","042670":"HD현대인프라코어","241560":"두산밥캣","034730":"SK",
        "353200":"대덕전자","402340":"SK스퀘어","298040":"효성중공업","240810":"원익IPS","005935":"삼성전자우",
        "000150":"두산","006800":"미래에셋증권","004170":"신세계","006260":"LS","950160":"코오롱티슈진",
        "277810":"레인보우로보틱스","007660":"이수페타시스","307950":"현대오토에버","036930":"주성엔지니어링",
        "028050":"삼성E&A","001440":"대한전선",
    })
    return m

def robust_mom(rets, i, codes, minobs=11):
    """12-1 모멘텀 = 클립된 월수익(±100%) 복리누적. 단일 오프린트 폭주 방지 + 이력필터."""
    w = rets.iloc[i - 13:i - 1]                    # t-13 ~ t-2 (12-1)
    w = w[[c for c in codes if c in w.columns]]
    cnt = w.count()                                 # 유효 월수
    mom = (1 + w).prod(min_count=minobs) - 1        # 이력 부족(minobs 미만)은 NaN
    mom = mom[cnt >= minobs].dropna()
    return mom

def leaders_at(px, rets, mcap, t, N=30):
    i = list(rets.index).index(t)
    if i < 13: return []
    mc = mcap.loc[t].dropna().sort_values(ascending=False); ranked = list(mc.index)
    rankpos = {c: r + 1 for r, c in enumerate(ranked)}
    pool = ranked[:max(100, 3 * N)]
    mom = robust_mom(rets, i, pool)
    sel = list(mom.sort_values(ascending=False).index[:N])
    return [(c, rankpos.get(c), float(mom.get(c))) for c in sel]

def now(px, rets, mcap, reg, nm, N=30, defense="50현금"):
    t = [m for m in rets.index if m in mcap.index][-1]
    picks = leaders_at(px, rets, mcap, t, N)
    row = reg.loc[t] if (reg is not None and t in reg.index) else None
    on = bool(row["sig"]) if (row is not None and pd.notna(row["sig"])) else True
    gap = row["gap_prev"] if row is not None else np.nan
    s = 1.0 if on else (0.5 if defense == "50현금" else (0.0 if defense == "완전현금" else 1.0))
    print("=" * 74)
    print(f"현재 동적 리더십 유니버스 — {t} 기준 (규칙: pool100·12-1모멘텀·상위{N}·EW)")
    print("=" * 74)
    dstate = "지수≥MA200 → 정상투자" if on else "지수<MA200 → 방어발동"
    print(f"  MA200 방어상태: {dstate} (전월말 지수/MA200 이격 {gap*100:+.1f}%) → 투자스칼라 s={s} ({defense})")
    if pd.notna(gap) and gap > 0.20:
        print(f"  ⚠️ 이격 {gap*100:+.0f}%는 과열권(late-cycle). 모멘텀 리더 12-1이 수백% = 파라볼릭 구간 → 모멘텀 크래시 위험 큼.")
        print(f"     MA200는 '하강 전환' 후에야 방어 발동(후행) → 신규 진입은 분할·리스크예산 축소 권장.")
    top_mom = np.mean([m for _, _, m in picks[:10]]) * 100 if picks else 0
    print(f"  → 규칙 편입 {len(picks)}종 · 각 EW {100.0/max(len(picks),1)*s:.1f}% (방어반영), 현금 {100*(1-s):.0f}%\n")
    print(f"  {'#':>3} {'코드':>7} {'종목명':<16}{'시총순위':>7}{'12-1모멘텀':>11}")
    rows = []
    for k, (c, rk, mo) in enumerate(picks, 1):
        name = nm.get(c, "")
        print(f"  {k:>3} {c:>7} {name:<16}{rk:>7}{mo*100:>10.0f}%")
        rows.append(dict(rank=k, code=c, name=name, mcap_rank=rk, mom_12_1=round(mo*100, 1)))
    out = pd.DataFrame(rows)
    out["ym"] = t; out["defense"] = defense; out["scalar_s"] = s; out["ew_weight_pct"] = round(100.0/max(len(picks),1)*s, 2)
    p = os.path.join(BASE, "유니버스_규칙화_현재.csv"); out.to_csv(p, index=False, encoding="utf-8-sig")
    print(f"\n  저장: 유니버스_규칙화_현재.csv ({len(picks)}종)")
    print("  ⚠️ 기계적 규칙 출력. 실전 집중은 리스크예산(5~7종·1%/트레이드)으로 별도. 투자자문 아님·책임 본인.")
    return rows, t, s

def stats(x, ann=12):
    x = pd.Series(x).dropna()
    if len(x) < 12: return None
    c = (1 + x).cumprod()
    return dict(CAGR=(1 + x).prod() ** (ann / len(x)) - 1, Sharpe=x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan,
                MDD=(c/c.cummax()-1).min(), n=len(x))

def cadence_bt(px, rets, mcap, reg, N=30, every=1, defense="50현금", swap_cap=None, tax=0.0015, slip=0.002045):
    months = [m for m in rets.index if m in mcap.index]
    held = []; prev_s = 0.0; last_sel = None; step = 0
    out = []; kept = []; turns = []
    for t in months:
        i = list(rets.index).index(t)
        if i < 13: continue
        do_resel = (last_sel is None) or (step % every == 0)
        if do_resel:
            picks = [c for c, _, _ in leaders_at(px, rets, mcap, t, N)]
            if swap_cap and last_sel:
                dropped = [c for c in last_sel if c not in picks]     # 신규선정에서 빠진 보유
                incoming = [c for c in picks if c not in last_sel]    # 새 후보
                to_remove = dropped[:swap_cap]                        # 최대 swap_cap만 교체
                to_add = incoming[:len(to_remove)]
                sel = [c for c in last_sel if c not in to_remove] + to_add
                # 규모 부족 시(상폐 등) 신규선정에서 보충
                for c in picks:
                    if len(sel) >= N: break
                    if c not in sel: sel.append(c)
                last_sel = sel[:N]
            else:
                last_sel = picks
        step += 1
        sel = last_sel
        cur = rets.loc[t]; names = [c for c in sel if pd.notna(cur.get(c))]
        if len(names) < N // 2: continue
        row = reg.loc[t] if (reg is not None and t in reg.index) else None
        on = bool(row["sig"]) if (row is not None and pd.notna(row["sig"])) else True
        s = 1.0 if (defense == "무방어" or on) else (0.5 if defense == "50현금" else 0.0)
        nn = set(names); f_mem = 1 - len(nn & set(held)) / len(nn) if held else 1.0
        turn = abs(s - prev_s) + s * f_mem
        out.append(s * cur[names].mean() - turn * (tax + 2 * slip)); kept.append(t); turns.append(s * f_mem)
        held = names; prev_s = s
    return pd.Series(out, index=kept), (np.mean(turns) if turns else 0) * 12

def cadence_sweep(px, rets, mcap, reg, N=30):
    print("=" * 88)
    print(f"교체주기 민감도 — 진우 다호라이즌(월·수개월 교체) 트레이드오프 (동적 TOP{N}·다올 비용후·30년)")
    print("=" * 88)
    print(f"  {'구성':<34}{'회전/년':>8}{'순 CAGR':>10}{'Sharpe':>9}{'MDD':>9}{'세금드래그≈':>11}")
    combos = [
        ("월간교체·무방어", 1, "무방어", None),
        ("월간교체·50%현금방어", 1, "50현금", None),
        ("2개월교체·50%현금", 2, "50현금", None),
        ("분기교체·50%현금", 3, "50현금", None),
        ("분기교체·50%현금·스왑캡6", 3, "50현금", 6),
        ("반기교체·50%현금", 6, "50현금", None),
        ("분기교체·완전현금·스왑캡6", 3, "완전현금", 6),
    ]
    res = {}
    for label, every, dfn, cap in combos:
        s, turn = cadence_bt(px, rets, mcap, reg, N=N, every=every, defense=dfn, swap_cap=cap)
        st = stats(s)
        if st:
            tax_drag = turn * 0.002 * 100  # 연 세금 근사(세금0.2%×회전)
            res[label] = dict(cagr=round(st["CAGR"]*100,1), sharpe=round(st["Sharpe"],2), mdd=round(st["MDD"]*100,1),
                              turn=round(turn,1), tax_drag=round(tax_drag,2))
            print(f"  {label:<34}{turn:>7.1f}x{st['CAGR']*100:>9.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%{tax_drag:>9.1f}%")
    print("\n  ── 해석 (중요) ──")
    print("  · 이 규칙은 '월간 회전 엣지'다: 월간 20.7%/0.88 → 2개월 13.6%/0.63 → 분기 12.0%/0.59로 급감.")
    print("    12-1 모멘텀 리더십은 오래 들면 반전으로 붕괴(무기후보_등록부 메모와 일치) → 느린 교체는 부적합.")
    print("  · 스왑캡6(분기)은 오히려 더 나빠짐(6.8%/0.40) — 급변 장에서 새 리더로 못 갈아타면 stale.")
    print("  · 함의: '중장기 보유·사이클' 성향은 이 모멘텀 슬리브가 아니라 별도 슬리브(코어 MA200+등급 · 딥밸류)로.")
    print("    이 모멘텀-리더십 슬리브는 월간 유지 + MA200 50%현금 방어가 정답. 슬리브 분리·리스크예산 배분이 핵심.")
    print("  ⚠️ EW·단순 모멘텀 근사. 실현손익 아님. 투자자문 아님·책임 본인.")
    json.dump(res, open(os.path.join(BASE, "유니버스_규칙화_주기민감도_결과.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return res

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--now", action="store_true"); ap.add_argument("--cadence-sweep", action="store_true")
    ap.add_argument("--N", type=int, default=30); ap.add_argument("--defense", default="50현금")
    a = ap.parse_args()
    px, rets = load_panel(); mcap = load_mcap(); reg = load_ma200_regime(); nm = name_map()
    if a.cadence_sweep: cadence_sweep(px, rets, mcap, reg, N=a.N)
    if a.now or not a.cadence_sweep: now(px, rets, mcap, reg, nm, N=a.N, defense=a.defense)

if __name__ == "__main__":
    main()
