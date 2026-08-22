# -*- coding: utf-8 -*-
r"""휩쏘_재무검정.py — 진입 시점 재무(PER·PBR·배당)가 휩쏘 성과를 가르는가, 전량 검정.

[가설 후보] ① 적자 전환기 진입이 오히려 세다  ② 고PER 주도주 눌림이 세다
            ③ 저PBR(자산가치 지지)이 세다      ④ 배당주가 덜 빠진다
[규율] 국면(실행/주의/관찰만)을 통제한 뒤의 리프트만 인정 — 주도주 풀의 교훈.
[표본] 역사원장 이벤트 중 KRX 재무 커버리지(2002-02~) & 40일 전진 확정분.
"""
import os, sys, json, importlib.util, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def _load_mod(fn, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def main():
    B1 = _load_mod("휩쏘_케이스빌더.py", "b1")
    FIN = B1.load_fin()
    G = pd.read_csv(os.path.join(HERE, "휩쏘_고점_이벤트.csv"), dtype={"code": str})
    G["code"] = G["code"].str.zfill(6)

    rows = []
    for _, r in G.iterrows():
        d = str(r["출발일"])
        if d < "2002-02": continue
        f = B1.fin_asof(FIN, r["code"], d)
        if not f: continue
        rows.append(dict(출발일=d, code=r["code"], 유형=r["유형"], 국면=r["국면"],
                         PER=f["PER"], PBR=f["PBR"], EPS=f["EPS"], DIV=f["DIV"],
                         ex=float(r["ex_ret"]) * 100 if pd.notna(r["ex_ret"]) else np.nan,
                         f40=float(r["fwd40"]) * 100 if pd.notna(r["fwd40"]) else np.nan,
                         peak6=r["고점6M"]))
    M = pd.DataFrame(rows)
    Mm = M.dropna(subset=["f40"]).copy()   # 40일 확정분만
    print(f"재무 결합 표본 {len(M)}건 · 40일 확정 {len(Mm)}건 (2002-02 이후)")

    def bucket_per(r):
        per, eps = r["PER"], r["EPS"]
        if not np.isfinite(per) or per == 0 or (np.isfinite(eps) and eps <= 0): return "적자/무실적"
        if per < 8: return "저PER(<8)"
        if per < 15: return "중PER(8~15)"
        if per < 30: return "중고PER(15~30)"
        return "고PER(30+)"
    def bucket_pbr(r):
        p = r["PBR"]
        if not np.isfinite(p) or p == 0: return None
        if p < 0.8: return "저PBR(<0.8)"
        if p < 1.5: return "중PBR(0.8~1.5)"
        if p < 3: return "중고PBR(1.5~3)"
        return "고PBR(3+)"
    def bucket_div(r):
        d = r["DIV"]
        if not np.isfinite(d): return None
        if d == 0: return "무배당"
        if d < 2: return "배당<2%"
        return "배당2%+"

    Mm["PER군"] = Mm.apply(bucket_per, axis=1)
    Mm["PBR군"] = Mm.apply(bucket_pbr, axis=1)
    Mm["DIV군"] = Mm.apply(bucket_div, axis=1)

    def stat(d):
        if len(d) < 15: return None
        return dict(n=int(len(d)), f40=float(d["f40"].mean()), w40=float((d["f40"] > 0).mean()),
                    ex=float(d["ex"].mean()), wex=float((d["ex"] > 0).mean()),
                    peak=float(pd.to_numeric(d["peak6"], errors="coerce").median()))

    def table(dd, col, order):
        out = []
        base = stat(dd)
        for b in order:
            s = stat(dd[dd[col] == b])
            if s: s["군"] = b; s["Δ40"] = s["f40"] - base["f40"]; out.append(s)
        return base, out

    ORD_PER = ["적자/무실적", "저PER(<8)", "중PER(8~15)", "중고PER(15~30)", "고PER(30+)"]
    ORD_PBR = ["저PBR(<0.8)", "중PBR(0.8~1.5)", "중고PBR(1.5~3)", "고PBR(3+)"]
    ORD_DIV = ["무배당", "배당<2%", "배당2%+"]

    res = {"표본": int(len(Mm))}
    scopes = [("전체", Mm), ("실행국면만", Mm[Mm["국면"] == "실행"])]
    for lab, dd in scopes:
        res[lab] = {}
        for collab, col, order in (("PER", "PER군", ORD_PER), ("PBR", "PBR군", ORD_PBR), ("배당", "DIV군", ORD_DIV)):
            base, tab = table(dd, col, order)
            res[lab][collab] = dict(기준=base, 표=tab)

    with open(os.path.join(HERE, "재무검정_요약.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    Mm.to_csv(os.path.join(HERE, "휩쏘_재무_이벤트.csv"), index=False, encoding="utf-8-sig")

    for lab, dd in scopes:
        base = stat(dd)
        print(f"\n{'='*86}\n [{lab}] n={base['n']} · 40일 {base['f40']:+.1f}%(승 {base['w40']*100:.0f}%) · 카드 {base['ex']:+.1f}%\n{'='*86}")
        for collab, col, order in (("PER", "PER군", ORD_PER), ("PBR", "PBR군", ORD_PBR), ("배당", "DIV군", ORD_DIV)):
            print(f"  ── {collab}")
            for b in order:
                s = stat(dd[dd[col] == b])
                if not s: print(f"    {b:<14} 표본<15 생략"); continue
                print(f"    {b:<14} n={s['n']:>4} · 40일 {s['f40']:+6.1f}% (Δ{s['f40']-base['f40']:+.1f}%p) · 승률 {s['w40']*100:3.0f}%"
                      f" · 카드 {s['ex']:+5.1f}% · 6M고점중앙 {s['peak']:+6.1f}%")


if __name__ == "__main__":
    main()
