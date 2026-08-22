# -*- coding: utf-8 -*-
r"""휩쏘_910리스트.py — 9~10월 눌림(휩쏘) 종목 전량 리스트 + 이듬해 1월·4월 고점까지 상승률.
   형 사이클 앵커(고점 1월·4월 쌍봉) 기준: 1년 창 최고가 아니라
   '눌린 가격 → 이듬해 1월 최고가'와 '→ 이듬해 4월 최고가'를 각각 계산.
   산출: 휩쏘_910_리스트.csv · 휩쏘_910_리스트.html (전량 주르륵 + 요약)
⚠️ 1월/4월 상승률은 '그때까지 계속 들고 있었다면'의 신의 시점 수치 — 실현치 아님. 규칙 비교 기준선.
"""
import os, sys, gc, importlib.util, warnings, html as H
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def _load_mod(fn, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def main():
    hz = _load_mod("휩쏘_역사검정.py", "hz")
    B1 = _load_mod("휩쏘_케이스빌더.py", "b1")
    FIN = B1.load_fin()
    G = pd.read_csv(os.path.join(HERE, "휩쏘_고점_이벤트.csv"), dtype={"code": str})
    G["code"] = G["code"].str.zfill(6)
    SO = G[pd.to_datetime(G["출발일"]).dt.month.isin([9, 10])].copy()
    targets = SO.groupby("code")["출발일"].apply(list).to_dict()
    print(f"9~10월 진입 이벤트 {len(SO)}건 · 종목 {len(targets)}")

    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    rows = []
    for mk in ("KOSPI", "KOSDAQ"):
        D = pd.read_csv(os.path.join(DATA, f"종목일봉_30년_{mk}.csv"), dtype=dt)
        D.columns = [x.strip().lstrip("﻿") for x in D.columns]
        D["code"] = D["code"].str.zfill(6)
        D = D[D["code"].isin(targets.keys())]
        for code, g in D.groupby("code", sort=False):
            want = targets.get(code)
            if not want: continue
            g = g.sort_values("date").reset_index(drop=True)
            g = g[~((g["open"] == 0) & (g["volume"] == 0))].reset_index(drop=True)
            if len(g) < 3: continue
            dts = g["date"].values.astype(str)
            o = g["open"].values.astype(float); h = g["high"].values.astype(float)
            l = g["low"].values.astype(float); c = g["close"].values.astype(float)
            v = g["volume"].values.astype(float)
            o, h, l, c, _ = hz.back_adjust(o, h, l, c, v, dts)
            pos = {d: i for i, d in enumerate(dts)}
            for d0 in want:
                t = pos.get(d0)
                if t is None or c[t] <= 0: continue
                yr = int(d0[:4]); ny = yr + 1
                def seg_max(a, b):
                    m = (dts >= a) & (dts <= b)
                    i = np.where(m)[0]
                    return (float(np.nanmax(h[i])) / c[t] - 1) * 100 if len(i) else np.nan
                jan = seg_max(f"{ny}-01-01", f"{ny}-01-31")
                apr = seg_max(f"{ny}-04-01", f"{ny}-04-30")
                full = seg_max(d0, f"{ny}-05-31")          # 참고: 진입~5월말 전체 최고
                done = dts[-1] >= f"{ny}-05-31"
                rows.append(dict(출발일=d0, code=code, 상승1월=jan, 상승4월=apr,
                                 전체최고=full, 완결=done))
        del D; gc.collect()

    X = pd.DataFrame(rows)
    M = SO.merge(X, on=["출발일", "code"], how="left")
    # 밸류 태그
    def vtag(r):
        f = B1.fin_asof(FIN, r["code"], str(r["출발일"]))
        if not f or str(r["출발일"]) < "2002-02": return ""
        tags = []
        if np.isfinite(f["PBR"]) and 0 < f["PBR"] < 0.8: tags.append("저PBR")
        if np.isfinite(f["PER"]) and 0 < f["PER"] < 8 and (not np.isfinite(f["EPS"]) or f["EPS"] > 0): tags.append("저PER")
        if np.isfinite(f["DIV"]) and f["DIV"] >= 2: tags.append("배당2%+")
        return "·".join(tags)
    M["밸류"] = M.apply(vtag, axis=1)
    M = M.sort_values("출발일", ascending=False).reset_index(drop=True)
    keep = ["출발일", "code", "name", "유형", "국면", "밸류", "상승1월", "상승4월", "전체최고", "고점월", "ex_ret", "ex_how", "완결"]
    M[keep].to_csv(os.path.join(HERE, "휩쏘_910_리스트.csv"), index=False, encoding="utf-8-sig")

    C = M[M["완결"] == True]
    j = C["상승1월"].dropna(); a = C["상승4월"].dropna()
    both = C.dropna(subset=["상승1월", "상승4월"])
    print(f"\n완결 {len(C)}건")
    print(f"  1월 고점까지: 중앙 {j.median():+.1f}% · 평균 {j.mean():+.1f}% · 플러스 {(j>0).mean()*100:.0f}%")
    print(f"  4월 고점까지: 중앙 {a.median():+.1f}% · 평균 {a.mean():+.1f}% · 플러스 {(a>0).mean()*100:.0f}%")
    print(f"  4월>1월 비율: {(both['상승4월']>both['상승1월']).mean()*100:.0f}%")
    for rg in ("실행", "주의", "관찰만"):
        s = C[C["국면"] == rg]
        if len(s) < 10: continue
        print(f"  [{rg}] n={len(s)} · 1월 중앙 {s['상승1월'].median():+.1f}% · 4월 중앙 {s['상승4월'].median():+.1f}%")
    sv = C[C["밸류"] != ""]
    if len(sv) >= 10:
        print(f"  [밸류태그] n={len(sv)} · 1월 중앙 {sv['상승1월'].median():+.1f}% · 4월 중앙 {sv['상승4월'].median():+.1f}%")

    # ── HTML (전량 주르륵)
    esc = H.escape
    def pc(v):
        if pd.isna(v): return "<td class=n>-</td>"
        cl = "good" if v > 0 else "bad"
        return f"<td class='n {cl}'>{v:+.1f}%</td>"
    trs = ""
    for _, r in M.iterrows():
        rg = str(r["국면"]); chip = {"실행": "rgG", "주의": "rgY", "관찰만": "rgR"}.get(rg, "")
        vt = str(r["밸류"] or "")
        trs += (f"<tr><td>{r['출발일']}</td>"
                f"<td>{esc(str(r['name']))} <span class=c>{r['code']}</span></td>"
                f"<td><span class='rg {chip}'>{esc(rg)}</span></td>"
                f"<td style='color:var(--good);font-size:11px;font-weight:650'>{esc(vt) if vt else '-'}</td>"
                + pc(r["상승1월"]) + pc(r["상승4월"]) + pc(r["전체최고"])
                + f"<td class=n>{int(r['고점월']) if pd.notna(r['고점월']) else '-'}월</td>"
                + f"<td class=n>{float(r['ex_ret'])*100:+.1f}% {esc(str(r['ex_how']))}</td></tr>")
    doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>9~10월 눌림 → 이듬해 1월·4월 고점</title><style>
:root{{color-scheme:light;--bg:#f6f6f4;--sf:#fcfcfb;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b;--bad:#c0342f}}
@media(prefers-color-scheme:dark){{:root{{color-scheme:dark;--bg:#111110;--sf:#1a1a19;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c;--bad:#e0655a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14px;line-height:1.55}}
.w{{max-width:980px;margin:0 auto;padding:34px 20px 70px}}
h1{{font-size:22px;margin:0 0 4px}}.sub{{color:var(--ink2);margin:0 0 10px;font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bd);white-space:nowrap}}
th{{color:var(--ink2);font-size:11px;font-weight:650;position:sticky;top:0;background:var(--bg)}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.c{{color:var(--mut);font-size:10.5px}}.good{{color:var(--good)}}.bad{{color:var(--bad)}}
.rg{{display:inline-block;padding:0 7px;border-radius:20px;font-size:10.5px;font-weight:700;color:#fff;line-height:17px}}
.rgG{{background:var(--good)}}.rgY{{background:var(--b)}}.rgR{{background:var(--bad)}}
.k{{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}}
.kb{{flex:1;min-width:150px;background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:11px 13px}}
.kb .v{{font-size:20px;font-weight:700}}.kb .l{{font-size:11.5px;color:var(--mut)}}
.wrap{{max-height:74vh;overflow:auto;border:1px solid var(--bd);border-radius:10px;background:var(--sf)}}
.warn{{color:var(--mut);font-size:12px;margin-top:14px}}
</style></head><body><div class=w>
<h1>9~10월 눌림 종목 전량 — 이듬해 1월·4월 고점까지 상승률</h1>
<p class=sub>30년 {len(M)}건(완결 {len(C)}) · 형 사이클 앵커(1월·4월 쌍봉) 기준 · 눌린 종가 → 각 월 최고가</p>
<div class=k>
<div class=kb><div class=v>{j.median():+.1f}%</div><div class=l>1월 고점까지 중앙 (플러스 {(j>0).mean()*100:.0f}%)</div></div>
<div class=kb><div class=v>{a.median():+.1f}%</div><div class=l>4월 고점까지 중앙 (플러스 {(a>0).mean()*100:.0f}%)</div></div>
<div class=kb><div class=v>{(both['상승4월']>both['상승1월']).mean()*100:.0f}%</div><div class=l>4월 &gt; 1월 인 비율</div></div>
<div class=kb><div class=v>{C['전체최고'].median():+.1f}%</div><div class=l>진입~5월말 전체 최고 중앙</div></div>
</div>
<div class=wrap><table>
<tr><th>출발일</th><th>종목</th><th>국면</th><th>밸류</th><th>1월 고점</th><th>4월 고점</th><th>전체 최고</th><th>최고월</th><th>실제 카드청산</th></tr>
{trs}
</table></div>
<p class=warn>⚠️ 1월/4월 상승률 = '그때까지 계속 보유했다면'의 그 달 최고가 기준 — 실현 불가능한 신의 수치. 손절 없이 들고 가면 그 사이 낙폭도 다 맞는다(달력 보유 검정: 중앙 −10.8%). 실제 실현치는 맨 오른쪽 카드청산. 백조정 가격 · 검정용 · 매매 추천 아님.</p>
</div></body></html>"""
    open(os.path.join(HERE, "휩쏘_910_리스트.html"), "w", encoding="utf-8").write(doc)
    print("저장: 휩쏘_910_리스트.csv · 휩쏘_910_리스트.html")


if __name__ == "__main__":
    main()
