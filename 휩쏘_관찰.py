# -*- coding: utf-8 -*-
r"""휩쏘_관찰.py — 탐지된 '출발점' 종목을 전진 추적하는 관찰 원장 (2026-08-01 · 다중 원장)

[왜] 탐색기는 종목의 '출발점'(2일째 바닥)을 찍는다. 거기서 끝내면 아무것도 안 남는다.
     출발점을 **누적 등록**하고 **매일 전진 추적**해 — 이후 얼마나 갔나·손절 지켰나·목표 닿았나를 기록.
     쌓이면 "이 자리가 진짜 얼마나 이기나"의 실증 근거가 된다.

[원장 분리]  --ledger 로 여러 원장을 따로 관리.
   · 휩쏘 트랙  : 휩쏘_관찰.csv     (탐색기가 자동 등록)
   · 조사 트랙  : 조사_관찰.csv     (오늘조사.py 로 수동 등록)  → py 휩쏘_관찰.py --ledger 조사 ...

[사용]
  py 휩쏘_관찰.py --add                     # 최신 휩쏘탐지_*.csv → 휩쏘 원장 등록 + 추적
  py 휩쏘_관찰.py --add --date 20260730
  py 휩쏘_관찰.py                            # 휩쏘 원장 전진 추적 → CSV·HTML
  py 휩쏘_관찰.py --ledger 조사 --codes 005930,000660   # 조사 원장에 수동 등록
  py 휩쏘_관찰.py --ledger 조사              # 조사 원장 추적

[상태] 관찰중 · 목표달성 · 손절 · 만료(N일) — 손절/목표/만료는 그 시점 수익으로 동결

[시장국면 도장]  각 종목은 **자기 출발일 시점의 시장국면**(실행/주의/관찰만)을 등록 때 도장으로 받는다.
   · 오늘 국면이 아니라 그 종목이 출발한 날의 국면 — 날짜가 달라지면 국면도 달라진다(30년 여러 모멘텀).
   · 근거: 30년 역사검정 — 시장 −12%↓·고변동이면 유리(+8.5%·승57%), 고점권·저변동이면 함정(−5.9%·승36%).
   · 원장이 쌓이면 국면별 성과가 따로 집계된다 → "게이트가 실전에서도 맞나"의 실증.
⚠️ 관찰·기록용. 매매 추천 아님.
"""
import os, sys, argparse, warnings, webbrowser, datetime, html as _h
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
EXPIRE_DEFAULT = 40


def paths(ledger):
    return (os.path.join(HERE, f"{ledger}_관찰.csv"),
            os.path.join(HERE, f"{ledger}_관찰_현황.html"))


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def load_daily():
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        p = _find(f"_일봉OHLCV_{m}_adj.csv")
        if p: fr.append(pd.read_csv(p, dtype={"code": str}))
    if not fr: return None
    D = pd.concat(fr, ignore_index=True); D["code"] = D["code"].str.zfill(6)
    amax = D["date"].max(); add = []
    for m in ("KOSPI", "KOSDAQ"):
        rp = _find(f"종목일봉_30년_{m}.csv")
        if not rp: continue
        try: raw = pd.read_csv(rp, dtype={"code": str})
        except Exception: continue
        if not {"date","code","high","low","close"}.issubset(raw.columns): continue
        raw = raw[raw["date"] > amax]
        if len(raw):
            raw = raw.copy(); raw["code"] = raw["code"].astype(str).str.zfill(6); add.append(raw)
    if add: D = pd.concat([D] + add, ignore_index=True)
    return D.drop_duplicates(["code","date"], keep="last").sort_values(["code","date"]).reset_index(drop=True)


def names_map():
    p = _find("종목명_맵.csv")
    if not p: return {}
    try:
        nm = pd.read_csv(p, dtype=str); return dict(zip(nm.iloc[:,0].str.zfill(6), nm.iloc[:,1]))
    except Exception: return {}


# ── 시장국면 게이트 (시장국면.py 엔진 공유 · 없으면 조용히 건너뜀)
_RG_MOD = None
def _regime_mod():
    global _RG_MOD
    if _RG_MOD is None:
        p = _find("시장국면.py")
        if not p: _RG_MOD = False
        else:
            try:
                import importlib.util
                spec = importlib.util.spec_from_file_location("sjkm", p)
                m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
                _RG_MOD = m
            except Exception:
                _RG_MOD = False
    return _RG_MOD


def regime_stamp(start):
    """출발일 'YYYY-MM-DD' 시점의 국면 도장. (판정 짧은형, 시장낙폭%) — 오늘이 아니라 그날 기준."""
    m = _regime_mod()
    if not m: return "", np.nan
    try:
        r = m.regime_at(start)
        lab = str(r.get("판정", "")).split("(")[0]   # 실행 / 주의 / 관찰만
        mdd = r.get("mdd252")
        return lab, (round(mdd * 100, 1) if isinstance(mdd, float) and np.isfinite(mdd) else np.nan)
    except Exception:
        return "", np.nan


def _blank_row(start, code, name, typ, grade, px, key, line, stop, target, mcap,
               국면="", 시장낙폭=np.nan):
    return dict(출발일=start, code=code, name=name, 유형=typ, 등급=grade,
                국면=국면, 시장낙폭=시장낙폭, 출발가=round(px),
                핵심선=key, 선가=round(line), 손절가=round(stop), 목표가=round(target),
                시총=mcap, 상태="관찰중", 종료일="", 종료수익="", 최고수익="", 갱신일=start)


def _merge_save(new, master):
    if os.path.exists(master):
        old = pd.read_csv(master, dtype={"code": str}); old["code"] = old["code"].str.zfill(6)
        ko = set(zip(old["출발일"].astype(str), old["code"]))
        new = new[~new.apply(lambda x: (str(x["출발일"]), x["code"]) in ko, axis=1)]
        merged = pd.concat([old, new], ignore_index=True)
    else:
        merged = new
    merged.to_csv(master, index=False, encoding="utf-8-sig")
    return merged, len(new)


def add_from_detect(date, grade, ledger):
    """휩쏘탐지_YYYYMMDD.csv → 원장 등록. 손절·목표는 휩쏘 규칙."""
    import glob
    src = _find(f"휩쏘탐지_{date}.csv") if date else None
    if not src:
        fs = sorted(glob.glob(os.path.join(HERE, "휩쏘탐지_*.csv")))
        src = fs[-1] if fs else None
    if not src: sys.exit("휩쏘탐지_*.csv 없음 — 먼저 휩쏘_탐색기.py 실행")
    d0 = "".join(c for c in os.path.basename(src) if c.isdigit())[:8]
    start = f"{d0[:4]}-{d0[4:6]}-{d0[6:]}"
    det = pd.read_csv(src, dtype={"code": str}); det["code"] = det["code"].str.zfill(6)
    if "등급" in det.columns: det = det[det["등급"].isin(list(grade))]
    rg, rmdd = regime_stamp(start)      # 출발일 시점 국면 — 이 등록분 전체에 도장
    if rg:
        mark = {"실행": "🟢", "주의": "🟡", "관찰만": "🔴"}.get(rg, "")
        print(f"  {mark} 출발일 {start} 시장국면: {rg}"
              + (f" (시장 1년고점比 {rmdd:+.1f}%)" if np.isfinite(rmdd) else ""))
        if rg == "관찰만":
            print("     ⚠️ 역사검정상 함정 국면(−5.9%·승36%) — 기록은 하되 실제 진입은 재고.")
    rows = []
    for _, r in det.iterrows():
        px = float(r["종가"]); cum2 = float(r.get("2일누적", np.nan))
        dist = float(r.get("핵심선거리", np.nan)); key = str(r.get("핵심선", "-"))
        line = px / (1 + dist) if np.isfinite(dist) else px
        typ = str(r.get("유형", "A"))
        if typ == "B":
            stop, target = px * 0.97, px * 1.20
        else:
            base = line if line < px else px * 0.98
            stop = max(base * 0.95, px * 0.90)
            target = px + (px / (1 + cum2) - px) * 0.5 if (np.isfinite(cum2) and cum2 < 0) else px * 1.10
        rows.append(_blank_row(start, r["code"], str(r.get("name", r["code"])), typ,
                               str(r.get("등급", "")), px, key, line, stop, target, r.get("mcap", np.nan),
                               국면=rg, 시장낙폭=rmdd))
    merged, n = _merge_save(pd.DataFrame(rows), paths(ledger)[0])
    print(f"[{ledger}] 등록: {start} 탐지분 신규 {n}종 → 원장 총 {len(merged)}종")
    return merged


def add_manual(codes, date, ledger, stop_pct=8.0, target_pct=15.0):
    """임의 종목을 출발일 종가로 등록(조사 트랙). 손절/목표는 일반 규칙(−8%/+15%)."""
    D = load_daily()
    if D is None: sys.exit("_일봉OHLCV_*_adj.csv 없음")
    nm = names_map(); n2c = {str(v).replace(" ", ""): k for k, v in nm.items()}
    start = date if date else D["date"].max()
    if len(start) == 8: start = f"{start[:4]}-{start[4:6]}-{start[6:]}"
    rg, rmdd = regime_stamp(start)      # 출발일 시점 국면 도장
    if rg:
        mark = {"실행": "🟢", "주의": "🟡", "관찰만": "🔴"}.get(rg, "")
        print(f"  {mark} 출발일 {start} 시장국면: {rg}"
              + (f" (시장 1년고점比 {rmdd:+.1f}%)" if np.isfinite(rmdd) else ""))
    def resolve(tok):
        tok = tok.strip()
        if tok.isascii() and 5 <= len(tok) <= 6 and tok.isalnum() and any(ch.isdigit() for ch in tok):
            return tok.zfill(6)
        return n2c.get(tok.replace(" ", ""))
    rows, miss = [], []
    for tok in codes:
        c = resolve(tok)
        if not c: miss.append(tok); continue
        g = D[(D["code"] == c) & (D["date"] <= start)]
        if len(g) == 0: miss.append(tok); continue
        px = float(g["close"].iloc[-1])
        rows.append(_blank_row(start, c, nm.get(c, c), "조사", "", px, "-", px,
                               px * (1 - stop_pct/100), px * (1 + target_pct/100), np.nan,
                               국면=rg, 시장낙폭=rmdd))
    if miss: print(f"  ⚠️ 못 찾음: {', '.join(miss)}")
    if not rows: sys.exit("등록할 종목 없음")
    merged, n = _merge_save(pd.DataFrame(rows), paths(ledger)[0])
    print(f"[{ledger}] 수동 등록: {start} 신규 {n}종 → 원장 총 {len(merged)}종")
    return merged


def track(days_expire, noopen, ledger):
    master, html = paths(ledger)
    if not os.path.exists(master):
        sys.exit(f"{os.path.basename(master)} 없음 — 먼저 --add 또는 --codes 로 등록")
    M = pd.read_csv(master, dtype={"code": str}); M["code"] = M["code"].str.zfill(6)
    # 국면 컬럼 소급: 기존 행도 '자기 출발일' 기준으로 도장 (오늘 국면으로 덮지 않는다)
    if "국면" not in M.columns: M["국면"] = ""
    if "시장낙폭" not in M.columns: M["시장낙폭"] = np.nan
    _rg_cache = {}
    for i, r in M.iterrows():
        cur_rg = str(r.get("국면", "")).strip()
        if cur_rg in ("", "nan"):
            s = str(r["출발일"])
            if s not in _rg_cache: _rg_cache[s] = regime_stamp(s)
            M.at[i, "국면"], M.at[i, "시장낙폭"] = _rg_cache[s]
    D = load_daily()
    if D is None: sys.exit("_일봉OHLCV_*_adj.csv 없음")
    last = D["date"].max(); bdays = np.array(sorted(D["date"].unique()))
    for i, r in M.iterrows():
        g = D[(D["code"] == r["code"]) & (D["date"] > str(r["출발일"]))]
        cur = float(g["close"].iloc[-1]) if len(g) else np.nan
        ndays = int((bdays > str(r["출발일"])).sum())
        M.at[i, "_현재가"] = cur
        M.at[i, "_현재수익"] = round((cur / r["출발가"] - 1) * 100, 1) if np.isfinite(cur) else np.nan
        M.at[i, "_경과"] = ndays
        if r["상태"] in ("손절", "목표달성", "만료") or len(g) == 0:
            M.at[i, "갱신일"] = last; continue
        hi, lo = float(g["high"].max()), float(g["low"].min())
        M.at[i, "최고수익"] = round((hi / r["출발가"] - 1) * 100, 1)
        stop, tgt = float(r["손절가"]), float(r["목표가"])
        if lo <= stop:      st, er = "손절", stop / r["출발가"] - 1
        elif hi >= tgt:     st, er = "목표달성", tgt / r["출발가"] - 1
        elif ndays >= days_expire: st, er = "만료", cur / r["출발가"] - 1
        else:               st, er = "관찰중", None
        M.at[i, "상태"] = st; M.at[i, "갱신일"] = last
        if st != "관찰중":
            M.at[i, "종료일"] = last; M.at[i, "종료수익"] = round(er * 100, 1)
    save = M[[c for c in M.columns if not c.startswith("_")]]
    save.to_csv(master, index=False, encoding="utf-8-sig")

    print("=" * 92)
    print(f" {ledger} 관찰 원장 — 갱신 {last} · 총 {len(M)}종")
    print("=" * 92)
    for st in ("관찰중", "목표달성", "손절", "만료"):
        sub = M[M["상태"] == st]
        if len(sub) == 0: continue
        col = "_현재수익" if st == "관찰중" else "종료수익"
        v = pd.to_numeric(sub[col], errors="coerce").dropna()
        print(f"  {st:<6} {len(sub):>3}종   {'평균 %+.1f%%' % v.mean() if len(v) else ''}")
    lr = pd.to_numeric(M["_현재수익"], errors="coerce").dropna()
    if len(lr):
        print(f"\n  현재 평균수익 {lr.mean():+.1f}% · 플러스 {int((lr>0).sum())}/{len(lr)}종 ({(lr>0).mean()*100:.0f}%)")

    # ── 국면별 성과 (출발일 도장 기준 — 30년 여러 모멘텀이 갈라 담긴다)
    if M["국면"].astype(str).str.strip().replace("nan", "").ne("").any():
        print("\n  ── 국면별 (출발일 시점 도장 기준)")
        for rg in ("실행", "주의", "관찰만"):
            sub = M[M["국면"].astype(str) == rg]
            if len(sub) == 0: continue
            v = pd.to_numeric(sub["_현재수익"], errors="coerce").dropna()
            mark = {"실행": "🟢", "주의": "🟡", "관찰만": "🔴"}[rg]
            s = f"  {mark} {rg:<4} {len(sub):>3}종"
            if len(v): s += f"   평균 {v.mean():+.1f}% · 플러스 {(v>0).mean()*100:.0f}%"
            print(s)
        n_red = int((M["국면"].astype(str) == "관찰만").sum())
        if n_red:
            print(f"     ⚠️ 관찰만 국면 등록분 {n_red}종 — 역사검정상 함정 국면. 성과가 갈리는지 지켜본다.")
    _write_html(M, last, days_expire, ledger, html)
    print(f"\n저장: {os.path.basename(master)} · {os.path.basename(html)}")
    if not noopen:
        try: webbrowser.open("file://" + os.path.abspath(html))
        except Exception: pass


def _write_html(M, last, days_expire, ledger, html_path):
    esc = _h.escape
    def num(v):
        v = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
        return "-" if pd.isna(v) else f"{v:+.1f}%"
    labels = {"관찰중": "var(--a)", "목표달성": "var(--good)", "손절": "var(--bad)", "만료": "var(--mut)"}
    M = M.assign(_r=pd.to_numeric(M["_현재수익"], errors="coerce"))
    blocks = ""
    for st, cl in labels.items():
        sub = M[M["상태"] == st].sort_values("_r", ascending=False)
        if len(sub) == 0: continue
        rows = ""
        for _, r in sub.iterrows():
            cur = r.get("_현재가")
            rg = str(r.get("국면", "") or "").strip()
            rgchip = {"실행": "<span class='rg rgG'>실행</span>",
                      "주의": "<span class='rg rgY'>주의</span>",
                      "관찰만": "<span class='rg rgR'>관찰만</span>"}.get(rg, "<span class=c>-</span>")
            curtd = f"{float(cur):,.0f}" if pd.notna(cur) else "-"
            rows += ("<tr>"
                     f"<td>{r['출발일']}</td>"
                     f"<td>{esc(str(r['name']))} <span class=c>{r['code']}</span></td>"
                     f"<td><span class='b b{esc(str(r['유형'])[:1])}'>{esc(str(r['유형'])[:1])}</span>{esc(str(r.get('등급','')))}</td>"
                     f"<td>{rgchip}</td>"
                     f"<td class=n>{float(r['출발가']):,.0f}</td>"
                     f"<td class=n>{curtd}</td>"
                     f"<td class=n><b>{num(r['_현재수익'])}</b></td>"
                     f"<td class=n>{num(r['최고수익'])}</td>"
                     f"<td class=n>{int(r['_경과']) if pd.notna(r.get('_경과')) else '-'}일</td>"
                     f"<td class=n>{float(r['손절가']):,.0f}</td>"
                     f"<td class=n>{float(r['목표가']):,.0f}</td></tr>")
        v = pd.to_numeric(sub["_현재수익"], errors="coerce").dropna()
        avg = f" · 평균 {v.mean():+.1f}%" if len(v) else ""
        blocks += (f"<h3 style='color:{cl}'>{st} · {len(sub)}종{avg}</h3>"
                   "<table><tr><th>출발일</th><th>종목</th><th>유형</th><th>국면</th><th>출발가</th><th>현재가</th>"
                   "<th>현재수익</th><th>최고</th><th>경과</th><th>손절</th><th>목표</th></tr>"
                   f"{rows}</table>")
    lr = pd.to_numeric(M["_현재수익"], errors="coerce").dropna()
    summ = (f"전체 {len(M)}종 · 현재 평균 {lr.mean():+.1f}% · 플러스 {int((lr>0).sum())}/{len(lr)} "
            f"({(lr>0).mean()*100:.0f}%)") if len(lr) else f"전체 {len(M)}종"

    # 오늘 국면 배너 + 국면별 성과 (출발일 도장 기준)
    ban = ""
    trg, tmdd = regime_stamp(last)
    if trg:
        bc = {"실행": "var(--good)", "주의": "var(--b)", "관찰만": "var(--bad)"}.get(trg, "var(--mut)")
        ban = (f"<p class=ban style='border-left-color:{bc}'>오늘({last}) 시장국면 <b style='color:{bc}'>{trg}</b>"
               + (f" · 시장 1년고점比 {tmdd:+.1f}%" if pd.notna(tmdd) else "")
               + " — 신규 등록분은 이 도장을 받는다</p>")
    rgblock = ""
    if M["국면"].astype(str).str.strip().replace("nan", "").ne("").any():
        rrows = ""
        for rg, chip in (("실행", "rgG"), ("주의", "rgY"), ("관찰만", "rgR")):
            sub = M[M["국면"].astype(str) == rg]
            if len(sub) == 0: continue
            v = pd.to_numeric(sub["_현재수익"], errors="coerce").dropna()
            rrows += (f"<tr><td><span class='rg {chip}'>{rg}</span></td><td class=n>{len(sub)}</td>"
                      f"<td class=n>{f'{v.mean():+.1f}%' if len(v) else '-'}</td>"
                      f"<td class=n>{f'{(v>0).mean()*100:.0f}%' if len(v) else '-'}</td></tr>")
        if rrows:
            rgblock = ("<h3>국면별 성과 — 출발일 시점 도장 기준 (여러 모멘텀이 갈라 담긴다)</h3>"
                       "<table style='max-width:430px'><tr><th>국면</th><th>종수</th><th>평균수익</th><th>플러스</th></tr>"
                       f"{rrows}</table>"
                       "<p class=warn style='margin-top:4px;border:0;padding:0'>역사검정 예측: 실행 국면 등록분이 이기고, 관찰만 국면 등록분이 진다 — 원장이 그걸 실증한다.</p>")
    doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{ledger} 관찰 원장 {last}</title><style>
:root{{color-scheme:light;--bg:#f6f6f4;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b;--bad:#c0342f}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111110;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c;--bad:#e66767}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14px;line-height:1.6}}
.w{{max-width:940px;margin:0 auto;padding:34px 20px 70px}}h1{{font-size:23px;margin:0 0 4px}}
.sub{{color:var(--ink2);margin:0}}.summ{{margin:8px 0 0;font-size:13px;color:var(--ink2)}}
h3{{font-size:15px;margin:26px 0 8px}}table{{width:100%;border-collapse:collapse;margin:2px 0 8px;font-size:13px}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--bd)}}th{{color:var(--ink2);font-size:11.5px;font-weight:650}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}.c{{color:var(--mut);font-size:11px}}
.b{{display:inline-block;width:18px;height:18px;border-radius:5px;text-align:center;line-height:18px;font-size:11px;font-weight:700;color:#fff;margin-right:4px}}
.bA{{background:var(--a)}}.bB{{background:var(--b)}}.b조{{background:var(--mut)}}
.rg{{display:inline-block;padding:1px 7px;border-radius:20px;font-size:11px;font-weight:700;color:#fff}}
.rgG{{background:var(--good)}}.rgY{{background:var(--b)}}.rgR{{background:var(--bad)}}
.ban{{margin:10px 0 0;padding:8px 12px;background:color-mix(in srgb,var(--bd) 40%,transparent);border-left:3px solid var(--mut);border-radius:6px;font-size:13px}}
.warn{{color:var(--mut);font-size:12px;margin-top:22px;border-top:1px solid var(--bd);padding-top:12px}}
</style></head><body><div class=w>
<h1>{ledger} 관찰 원장 · {last}</h1>
<p class=sub>출발점 전진 추적 — 손절/목표/만료({days_expire}일)는 그 시점 수익으로 동결</p>
<p class=summ>{summ}</p>
{ban}
{rgblock}
{blocks}
<p class=warn>⚠️ 관찰·기록용. 이 원장이 쌓이면 '이 자리'의 실제 승률·기대값을 볼 수 있다.</p>
</div></body></html>"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="휩쏘", help="원장 이름 (기본 휩쏘 · 조사 등)")
    ap.add_argument("--add", action="store_true", help="휩쏘탐지 CSV를 원장에 등록")
    ap.add_argument("--codes", default=None, help="수동 등록 코드/종목명 (쉼표)")
    ap.add_argument("--date", default=None, help="등록 날짜 YYYYMMDD (기본 최신)")
    ap.add_argument("--grade", default="ABC", help="탐지 등록 등급 (기본 ABC)")
    ap.add_argument("--days", type=int, default=EXPIRE_DEFAULT, help="만료 거래일 (기본 40)")
    ap.add_argument("--noopen", action="store_true")
    a = ap.parse_args()
    if a.codes:
        add_manual([x for x in a.codes.split(",")], a.date, a.ledger)
    elif a.add:
        add_from_detect(a.date, a.grade, a.ledger)
    track(a.days, a.noopen, a.ledger)


if __name__ == "__main__":
    main()
