# -*- coding: utf-8 -*-
r"""휩쏘_역사원장.py — 30년(1997~2026) 휩쏘 이벤트 전량을 '원장' 형태로 목록화.

[왜] 관찰원장과 같은 원리를 과거 전체에 소급: 각 이벤트는 **자기 출발일 시점의 시장국면**
     (실행/주의/관찰만) 도장을 받는다. 30년간 여러 모멘텀이 갈라 담긴 목록 원장.

[입력] 역사검정_이벤트_{KOSPI,KOSDAQ}.csv (휩쏘_역사검정.py 산출)
       kospi_index_daily.csv (국면 판정용)
[출력] 휩쏘_역사원장.csv · 휩쏘_역사원장.html (필터·검색 가능한 자체완결 문서)

[상태] 목표/손절/트레일/만기 = 카드 청산 시뮬 결과 · 진행중 = 40일 미경과(2026 최근분)
⚠️ 검정·기록용. 백조정 가격 기준 시뮬. 생존편향·소규모 증자 잔존 한계는 판정문 참조.
"""
import os, sys, html as H
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def load_events():
    fs = [_find(f"역사검정_이벤트_{m}.csv") for m in ("KOSPI", "KOSDAQ")]
    fs = [f for f in fs if f]
    if not fs: sys.exit("역사검정_이벤트_*.csv 없음 — 먼저 휩쏘_역사검정.py 실행")
    E = pd.concat([pd.read_csv(f, dtype={"code": str}) for f in fs], ignore_index=True)
    E["code"] = E["code"].str.zfill(6)
    return E.sort_values("date").reset_index(drop=True)


def regime_table():
    """지수 전 기간 국면 시계열 — 시장국면.py 와 동일 게이트."""
    p = _find("kospi_index_daily.csv")
    if not p: sys.exit("kospi_index_daily.csv 없음")
    ix = pd.read_csv(p); ix.columns = [c.strip().lstrip("﻿") for c in ix.columns]
    ix["Date"] = pd.to_datetime(ix["Date"]); ix = ix.sort_values("Date").reset_index(drop=True)
    c = ix["Close"].astype(float)
    ix["mdd"] = c / c.rolling(252, min_periods=120).max() - 1
    ret = c.pct_change()
    ix["vol20"] = ret.rolling(20, min_periods=10).std() * np.sqrt(252)
    volmed = ix["vol20"].median()
    def gate(r):
        mdd, vol = r["mdd"], r["vol20"]
        volhi = np.isfinite(vol) and vol > volmed
        if np.isfinite(mdd) and mdd <= -0.12: return "실행"
        if volhi and np.isfinite(mdd) and mdd <= -0.05: return "실행"
        if np.isfinite(mdd) and mdd >= -0.05 and not volhi: return "관찰만"
        return "주의"
    ix["국면"] = ix.apply(gate, axis=1)
    return ix[["Date", "국면", "mdd"]].rename(columns={"Date": "date"})


def build():
    E = load_events()
    R = regime_table()
    E["date"] = pd.to_datetime(E["date"])
    E = pd.merge_asof(E.sort_values("date"), R.sort_values("date"), on="date", direction="backward")

    L = pd.DataFrame({
        "출발일": E["date"].dt.strftime("%Y-%m-%d"),
        "code": E["code"], "name": E["name"],
        "유형": E["유형"], "등급": E["등급"].fillna(""),
        "국면": E["국면"].fillna(""),
        "시장낙폭": (E["mdd"] * 100).round(1),
        "당시종가": E["rawclose"].round(0),
        "2일누적": (E["cum2"] * 100).round(1),
        "핵심선": E["keyline"],
        "카드수익": (E["ex_ret"] * 100).round(1),
        "청산": E["ex_how"], "경과일": E["ex_bars"],
        "40일수익": (E["fwd40"] * 100).round(1),
        "시총": E["mcap"],
    })
    # 미성숙(40일 미경과)이면서 청산 못 한 '만기' → 진행중
    live = L["40일수익"].isna() & (L["청산"] == "만기")
    L.loc[live, "청산"] = "진행중"
    L = L.sort_values("출발일", ascending=False).reset_index(drop=True)
    out_csv = os.path.join(HERE, "휩쏘_역사원장.csv")
    L.to_csv(out_csv, index=False, encoding="utf-8-sig")
    return L, out_csv


def fmt_mcap(v):
    if not (isinstance(v, (int, float)) and np.isfinite(v)): return "-"
    return f"{v/1e12:.1f}조" if v >= 1e12 else f"{v/1e8:,.0f}억"


def live_section():
    """실전 관찰 원장(휩쏘·조사)을 읽어 상단 '지금' 블록 HTML 생성 — 한눈에."""
    esc = H.escape
    STC = {"관찰중": ("var(--a)", "stB"), "목표달성": ("var(--good)", "stG"),
           "손절": ("var(--bad)", "stR"), "만료": ("var(--mut)", "stM")}
    out = ""
    for ledger in ("휩쏘", "조사"):
        p = _find(f"{ledger}_관찰.csv")
        if not p: continue
        try:
            M = pd.read_csv(p, dtype={"code": str}); M["code"] = M["code"].str.zfill(6)
        except Exception: continue
        if len(M) == 0: continue
        M["_종료"] = pd.to_numeric(M.get("종료수익"), errors="coerce")
        M["_최고"] = pd.to_numeric(M.get("최고수익"), errors="coerce")
        M["_순서"] = M["상태"].map({"관찰중": 0, "목표달성": 1, "손절": 2, "만료": 3}).fillna(9)
        M = M.sort_values(["_순서", "_종료"], ascending=[True, False])
        # 요약
        parts = []
        for st in ("관찰중", "목표달성", "손절", "만료"):
            sub = M[M["상태"] == st]
            if len(sub) == 0: continue
            v = sub["_종료"].dropna()
            parts.append(f"{st} {len(sub)}" + (f"(평균 {v.mean():+.1f}%)" if len(v) else ""))
        갱신 = str(M.get("갱신일", pd.Series([""])).iloc[0]) if "갱신일" in M.columns else ""
        rows = ""
        for _, r in M.iterrows():
            st = str(r["상태"]); _, stc = STC.get(st, ("var(--mut)", "stM"))
            rg = str(r.get("국면", "") or "").strip()
            chip = {"실행": "rgG", "주의": "rgY", "관찰만": "rgR"}.get(rg, "")
            rgs = f"<span class='rg {chip}'>{esc(rg)}</span>" if chip else "<span class=c>-</span>"
            ret = r["_종료"] if pd.notna(r["_종료"]) else r["_최고"]
            rets = f"{ret:+.1f}%" if pd.notna(ret) else "-"
            retl = "확정" if pd.notna(r["_종료"]) else "최고"
            retc = "good" if (pd.notna(ret) and ret > 0) else ("bad" if pd.notna(ret) and ret < 0 else "")
            hi = f"{r['_최고']:+.1f}%" if pd.notna(r["_최고"]) else "-"
            rows += (f"<tr><td>{esc(str(r['출발일']))}</td>"
                     f"<td>{esc(str(r['name']))} <span class=c>{r['code']}</span></td>"
                     f"<td><span class='b b{esc(str(r['유형'])[:1])}'>{esc(str(r['유형'])[:1])}</span>{esc(str(r.get('등급','') or ''))}</td>"
                     f"<td>{rgs}</td>"
                     f"<td class=n>{float(r['출발가']):,.0f}</td>"
                     f"<td class=n>{float(r['손절가']):,.0f}</td>"
                     f"<td class=n>{float(r['목표가']):,.0f}</td>"
                     f"<td><span class='st {stc}'>{esc(st)}</span></td>"
                     f"<td class='n {retc}'><b>{rets}</b> <span class=c>{retl}</span></td>"
                     f"<td class=n>{hi}</td></tr>")
        out += (f"<h3>지금 — {ledger} 관찰 원장 · {len(M)}종"
                + (f" <span class=c>갱신 {esc(갱신)}</span>" if 갱신 else "") + "</h3>"
                f"<p class=sub style='margin:0 0 6px'>{' · '.join(parts)}</p>"
                "<div class=wrap style='max-height:46vh'><table>"
                "<tr><th>출발일</th><th>종목</th><th>유형</th><th>국면</th><th>출발가</th>"
                "<th>손절</th><th>목표</th><th>상태</th><th>수익</th><th>최고</th></tr>"
                f"{rows}</table></div>")
    return out


def write_html(L, out_html):
    esc = H.escape
    mature = L[L["청산"] != "진행중"]
    v = pd.to_numeric(mature["카드수익"], errors="coerce").dropna()

    def cell_stat(sub):
        x = pd.to_numeric(sub["카드수익"], errors="coerce").dropna()
        if not len(x): return "-", "-", 0
        return f"{x.mean():+.1f}%", f"{(x>0).mean()*100:.0f}%", len(x)

    rgrows = ""
    for rg, chip in (("실행", "rgG"), ("주의", "rgY"), ("관찰만", "rgR")):
        sub = mature[mature["국면"] == rg]
        m40 = pd.to_numeric(sub["40일수익"], errors="coerce").dropna()
        a, w, n = cell_stat(sub)
        m40s = f"{m40.mean():+.1f}%" if len(m40) else "-"
        w40 = f"{(m40>0).mean()*100:.0f}%" if len(m40) else "-"
        rgrows += (f"<tr><td><span class='rg {chip}'>{rg}</span></td><td class=n>{n:,}</td>"
                   f"<td class=n>{m40s}</td><td class=n>{w40}</td>"
                   f"<td class=n>{a}</td><td class=n>{w}</td></tr>")

    years = sorted(L["출발일"].str[:4].unique(), reverse=True)
    yopts = "".join(f"<option value='{y}'>{y}</option>" for y in years)

    # 연도별 건수 미니차트 (클릭 → 그 연도 필터)
    yc = L["출발일"].str[:4].value_counts().sort_index()
    W2 = 780; bw = W2 / len(yc); ymax = int(yc.max())
    ybars = ""
    for i, (yy, n) in enumerate(yc.items()):
        x = i * bw; hh = max(2, n / ymax * 78)
        ybars += (f"<rect x='{x+1:.1f}' y='{88-hh:.1f}' width='{bw-2:.1f}' height='{hh:.1f}' "
                  f"fill='var(--a)' opacity='0.75' style='cursor:pointer' onclick='setY(\"{yy}\")'>"
                  f"<title>{yy}: {n}건</title></rect>")
        if int(yy) % 5 == 0 or yy == "2026":
            ybars += f"<text x='{x+bw/2:.1f}' y='100' font-size='9' fill='var(--mut)' text-anchor='middle'>{yy[2:]}</text>"
    ychart = (f"<svg viewBox='0 0 {W2} 104' width='100%' style='max-width:{W2}px;display:block'>{ybars}</svg>"
              "<p class=sub style='margin:2px 0 0'>연도별 건수 — 막대를 클릭하면 그 연도만 표시 (위기해 1998·2000·2008·2020·2024·2026에 몰림)</p>")

    trs = []
    for _, r in L.iterrows():
        rg = str(r["국면"])
        chip = {"실행": "rgG", "주의": "rgY", "관찰만": "rgR"}.get(rg, "")
        ex = str(r["청산"])
        excl = {"목표": "good", "손절": "bad", "트레일": "", "만기": "mut", "진행중": "acc"}.get(ex, "")
        cardv = r["카드수익"]; f40 = r["40일수익"]
        card_s = f"{cardv:+.1f}%" if pd.notna(cardv) else "-"
        f40_s = f"{f40:+.1f}%" if pd.notna(f40) else "-"
        card_c = "good" if (pd.notna(cardv) and cardv > 0) else ("bad" if pd.notna(cardv) and cardv < 0 else "")
        f40_c = "good" if (pd.notna(f40) and f40 > 0) else ("bad" if pd.notna(f40) and f40 < 0 else "")
        trs.append(
            f"<tr data-y='{r['출발일'][:4]}' data-g='{esc(rg)}' data-t='{esc(str(r['유형']))}' "
            f"data-s='{esc(str(r['name']))} {r['code']}'>"
            f"<td>{r['출발일']}</td>"
            f"<td>{esc(str(r['name']))} <span class=c>{r['code']}</span></td>"
            f"<td><span class='b b{esc(str(r['유형']))}'>{esc(str(r['유형']))}</span>{esc(str(r['등급']))}</td>"
            f"<td><span class='rg {chip}'>{esc(rg)}</span></td>"
            f"<td class=n>{r['시장낙폭']:+.1f}%</td>"
            f"<td class=n>{r['당시종가']:,.0f}</td>"
            f"<td class=n>{r['2일누적']:+.1f}%</td>"
            f"<td class='n {excl}'>{esc(ex)}</td>"
            f"<td class='n {card_c}'>{card_s}</td>"
            f"<td class='n {f40_c}'>{f40_s}</td>"
            f"<td class=n>{fmt_mcap(r['시총'])}</td></tr>")
    body_rows = "\n".join(trs)

    n_all = len(L); n_live = int((L["청산"] == "진행중").sum())
    live = live_section()
    doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>휩쏘 30년 역사원장</title><style>
:root{{color-scheme:light;--bg:#f6f6f4;--sf:#fcfcfb;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b;--bad:#c0342f}}
@media(prefers-color-scheme:dark){{:root{{color-scheme:dark;--bg:#111110;--sf:#1a1a19;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c;--bad:#e0655a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14px;line-height:1.55}}
.w{{max-width:1060px;margin:0 auto;padding:34px 20px 70px}}
h1{{font-size:23px;margin:0 0 4px}}.sub{{color:var(--ink2);margin:0 0 14px;font-size:13px}}
h3{{font-size:15px;margin:22px 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bd);white-space:nowrap}}
th{{color:var(--ink2);font-size:11px;font-weight:650;position:sticky;top:0;background:var(--bg)}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.c{{color:var(--mut);font-size:10.5px}}.good{{color:var(--good)}}.bad{{color:var(--bad)}}.mut{{color:var(--mut)}}.acc{{color:var(--a)}}
.b{{display:inline-block;width:17px;height:17px;border-radius:4px;text-align:center;line-height:17px;font-size:10.5px;font-weight:700;color:#fff;margin-right:3px}}
.bA{{background:var(--a)}}.bB{{background:var(--b)}}
.rg{{display:inline-block;padding:0 7px;border-radius:20px;font-size:10.5px;font-weight:700;color:#fff;line-height:17px}}
.rgG{{background:var(--good)}}.rgY{{background:var(--b)}}.rgR{{background:var(--bad)}}
.st{{display:inline-block;padding:0 7px;border-radius:5px;font-size:10.5px;font-weight:700;color:#fff;line-height:17px}}
.stB{{background:var(--a)}}.stG{{background:var(--good)}}.stR{{background:var(--bad)}}.stM{{background:var(--mut)}}
.bar{{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0;align-items:center}}
.bar select,.bar input{{background:var(--sf);color:var(--ink);border:1px solid var(--bd);border-radius:7px;padding:6px 9px;font-size:13px}}
.bar input{{min-width:180px}}
.fb{{background:var(--sf);border:1px solid var(--bd);border-radius:20px;padding:4px 12px;font-size:12.5px;cursor:pointer;color:var(--ink2)}}
.fb.on{{border-color:var(--a);color:var(--a);font-weight:650}}
.cnt{{color:var(--mut);font-size:12px;margin-left:auto}}
.wrap{{max-height:72vh;overflow:auto;border:1px solid var(--bd);border-radius:10px;background:var(--sf)}}
.warn{{color:var(--mut);font-size:12px;margin-top:16px;border-top:1px solid var(--bd);padding-top:10px}}
sm{{color:var(--mut)}}
</style></head><body><div class=w>
<h1>휩쏘 30년 역사원장</h1>
<p class=sub>1997~2026 · 전 {n_all:,}건(확정 {len(mature):,} · 진행중 {n_live}) · 각 행은 <b>자기 출발일 시점</b>의 시장국면 도장 · 카드수익=손절·목표·트레일 청산 시뮬 · 가격은 백조정 기준</p>

{live}

<h3>국면별 성과 (확정분) — 30년 여러 모멘텀이 갈라 담긴 결과</h3>
<table style="max-width:640px"><tr><th>국면(출발일 도장)</th><th>건수</th><th>40일 평균</th><th>40일 승률</th><th>카드 평균</th><th>카드 승률</th></tr>
{rgrows}</table>
<p class=warn style="border:0;margin-top:6px;padding:0">역사검정 결론 그대로: 🟢실행 국면 등록분이 이기고 🔴관찰만 국면 등록분이 진다. 이 원장이 그 원자료다.</p>

<h3>30년 역사 목록 — 전 {n_all:,}건 (1997~2026 · 최신순 정렬이라 첫 화면은 2026부터)</h3>
{ychart}
<div class=bar>
<button class="fb on" data-g="">전체</button>
<button class=fb data-g="실행">🟢 실행</button>
<button class=fb data-g="주의">🟡 주의</button>
<button class=fb data-g="관찰만">🔴 관찰만</button>
<select id=fy><option value="">전체 연도</option>{yopts}</select>
<select id=ft><option value="">A+B</option><option value="A">A 선지지형</option><option value="B">B 리더형</option></select>
<input id=fs placeholder="종목명·코드 검색">
<span class=cnt id=cnt></span>
</div>

<div class=wrap><table id=tbl>
<tr><th>출발일</th><th>종목</th><th>유형</th><th>국면</th><th>시장낙폭</th><th>당시종가</th><th>2일누적</th><th>청산</th><th>카드수익</th><th>40일수익</th><th>시총</th></tr>
{body_rows}
</table></div>

<p class=warn>⚠️ 검정·기록용. 매매 추천 아님. 생존편향(상폐 종목 과소반영)·가격제한폭 이내 소규모 증자 잔존·합성지수 한계는 <b>휩쏘_역사검정_판정문.md</b> 참조. 갱신: <code>py 휩쏘_역사원장.py</code></p>
</div>
<script>
var G="",Y="",T="",S="";
var rows=[].slice.call(document.querySelectorAll("#tbl tr[data-y]"));
function ap(){{var n=0;rows.forEach(function(r){{
 var ok=(!G||r.dataset.g===G)&&(!Y||r.dataset.y===Y)&&(!T||r.dataset.t===T)&&(!S||r.dataset.s.toLowerCase().indexOf(S)>=0);
 r.style.display=ok?"":"none";if(ok)n++;}});
 document.getElementById("cnt").textContent=n.toLocaleString()+"건 표시";}}
document.querySelectorAll(".fb").forEach(function(b){{b.onclick=function(){{
 document.querySelectorAll(".fb").forEach(function(x){{x.classList.remove("on")}});
 b.classList.add("on");G=b.dataset.g;ap();}}}});
document.getElementById("fy").onchange=function(){{Y=this.value;ap();}};
function setY(y){{var s=document.getElementById("fy");s.value=(s.value===y?"":y);Y=s.value;ap();
 document.getElementById("tbl").scrollIntoView({{behavior:"smooth"}});}}
window.setY=setY;
document.getElementById("ft").onchange=function(){{T=this.value;ap();}};
document.getElementById("fs").oninput=function(){{S=this.value.trim().toLowerCase();ap();}};
ap();
</script></body></html>"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    L, out_csv = build()
    out_html = out_csv.replace(".csv", ".html")
    write_html(L, out_html)
    mature = L[L["청산"] != "진행중"]
    print("=" * 78)
    print(f" 휩쏘 30년 역사원장 — 전 {len(L):,}건 (확정 {len(mature):,} · 진행중 {int((L['청산']=='진행중').sum())})")
    print("=" * 78)
    for rg in ("실행", "주의", "관찰만"):
        sub = mature[mature["국면"] == rg]
        x = pd.to_numeric(sub["카드수익"], errors="coerce").dropna()
        mark = {"실행": "🟢", "주의": "🟡", "관찰만": "🔴"}[rg]
        if len(x):
            print(f"  {mark} {rg:<4} {len(sub):>5,}건 · 카드 평균 {x.mean():+.1f}% · 승률 {(x>0).mean()*100:.0f}%")
    print(f"\n저장: 휩쏘_역사원장.csv · 휩쏘_역사원장.html")


if __name__ == "__main__":
    main()
