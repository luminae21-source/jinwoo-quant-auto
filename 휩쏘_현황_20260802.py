# -*- coding: utf-8 -*-
"""휩쏘 현황판 HTML 빌더 — 국면 + 원장 33종 + 2단 전환 지시."""
import os, sys, html as H, importlib.util
import numpy as np, pandas as pd
HERE = "/home/claude/jq"
spec = importlib.util.spec_from_file_location("sg", f"{HERE}/시장국면.py")
sg = importlib.util.module_from_spec(spec); spec.loader.exec_module(sg)
rg = sg.regime_at()
R = pd.read_csv(f"{HERE}/휩쏘_원장_2단전환_20260802.csv", dtype={"code": str})
done = R[R["목표도달일"].notna() & (R["목표도달일"] != "")].sort_values("잔여_평가", ascending=False)
open_ = R[~R.index.isin(done.index)]
esc = H.escape
mark = "🟢" if rg.get("실행") else ("🟡" if "주의" in rg["판정"] else "🔴")

def rows_done():
    s = ""
    for _, x in done.iterrows():
        buf = x["잔여_트레일선"] / x["현재가"] - 1
        cls = "bad" if buf > -0.03 else ""
        s += (f"<tr><td><b>{esc(str(x['name']))}</b> <span class=c>{x['code']}</span></td>"
              f"<td class=n>{esc(str(x['유형']))}{esc(str(x['등급']))}</td>"
              f"<td class=n>{x['진입가']:,.0f}</td><td class=n>{x['목표가']:,.0f}</td>"
              f"<td class=n>{x['현재가']:,.0f}</td>"
              f"<td class='n good'>+{x['실현_50%']*100:.1f}%</td>"
              f"<td class='n {'good' if x['잔여_평가']>0 else 'bad'}'>{x['잔여_평가']*100:+.1f}%</td>"
              f"<td class='n key'>{x['잔여_트레일선']:,.0f}</td>"
              f"<td class='n {cls}'>{buf*100:+.1f}%</td></tr>")
    return s

def rows_open():
    s = ""
    for _, x in open_.iterrows():
        s += (f"<tr><td><b>{esc(str(x['name']))}</b> <span class=c>{x['code']}</span></td>"
              f"<td class=n>{esc(str(x['유형']))}{esc(str(x['등급']))}</td>"
              f"<td class=n>{x['진입가']:,.0f}</td><td class=n>{x['현재가']:,.0f}</td>"
              f"<td class='n {'good' if x['현재수익']>0 else 'bad'}'>{x['현재수익']*100:+.1f}%</td>"
              f"<td class='n key'>{x['손절가']:,.0f}</td><td class=n>{x['손절까지']*100:+.1f}%</td>"
              f"<td class='n key'>{x['목표가']:,.0f}</td><td class=n>{x['목표까지']*100:+.1f}%</td></tr>")
    return s

old = done["카드_구(전량)"].mean() * 100
new = done["카드_신(2단·현재평가)"].mean() * 100

doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>휩쏘 현황 · {rg['date']}</title><style>
:root{{--bg:#0f1115;--sf:#171a21;--sf2:#1d212a;--bd:#2a2f3a;--ink:#e6e8ee;--dim:#98a0b0;--mut:#6d7484;
--good:#3fb98a;--bad:#e0596b;--warn:#e0a33f;--acc:#6aa6ff}}
@media(prefers-color-scheme:light){{:root{{--bg:#f7f8fa;--sf:#fff;--sf2:#f0f2f6;--bd:#e2e5ec;--ink:#1a1d24;--dim:#5b6373;--mut:#8a92a3}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",sans-serif}}
.w{{max-width:1080px;margin:0 auto;padding:30px 18px 70px}}
h1{{font-size:25px;margin:0 0 4px;letter-spacing:-.4px}}
.sub{{color:var(--dim);font-size:13.5px;margin-bottom:20px}}
h2{{font-size:18px;margin:34px 0 10px;padding-top:18px;border-top:1px solid var(--bd)}}
.banner{{border-radius:12px;padding:16px 20px;margin:16px 0;border:1px solid;
background:linear-gradient(135deg,rgba(63,185,138,.14),rgba(63,185,138,.03));border-color:rgba(63,185,138,.45)}}
.banner b{{font-size:19px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px;margin:16px 0}}
.kpi{{background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:13px 15px}}
.kpi .l{{font-size:11.5px;color:var(--mut)}}.kpi .v{{font-size:22px;font-weight:650;margin-top:2px;letter-spacing:-.5px}}
.kpi .n{{font-size:11.5px;color:var(--dim);margin-top:2px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:7px 9px;border-bottom:1px solid var(--bd);text-align:left;white-space:nowrap}}
th{{color:var(--dim);font-size:11.5px;font-weight:600;position:sticky;top:0;background:var(--bg)}}
td.n,th.n{{text-align:right;font-variant-numeric:tabular-nums}}
tbody tr:hover{{background:var(--sf2)}}
.c{{color:var(--mut);font-size:10.5px}}.good{{color:var(--good)}}.bad{{color:var(--bad)}}.key{{color:var(--acc);font-weight:600}}
.box{{max-height:none;border:1px solid var(--bd);border-radius:10px;background:var(--sf);overflow-x:auto}}
.note{{font-size:12.5px;color:var(--dim);border-left:2px solid var(--bd);padding-left:12px;margin:12px 0}}
pre{{background:var(--sf2);border:1px solid var(--bd);border-radius:10px;padding:14px 16px;font-size:12.5px;
line-height:1.7;font-family:ui-monospace,Menlo,monospace;overflow-x:auto}}
footer{{margin-top:38px;padding-top:16px;border-top:1px solid var(--bd);color:var(--mut);font-size:12px}}
</style></head><body><div class=w>

<h1>휩쏘 현황판</h1>
<div class=sub>기준 {rg['date']} (마지막 거래일) · 작성 2026-08-02 · 관찰 원장 {len(R)}종</div>

<div class=banner><b>{mark} 시장국면 : {esc(rg['판정'])}</b><br>
<span style="color:var(--dim)">{esc(rg['이유'])}</span></div>

<div class=kpis>
<div class=kpi><div class=l>지수 1년고점比</div><div class=v>{rg['mdd252']*100:+.1f}%</div><div class=n>게이트 기준 −12%</div></div>
<div class=kpi><div class=l>20일 변동성(연율)</div><div class=v warn>{rg['vol20']*100:.0f}%</div><div class=n>중앙 {rg['volmed']*100:.1f}% · 고변동</div></div>
<div class=kpi><div class=l>목표 도달</div><div class=v good>{len(done)}/{len(R)}종</div><div class=n>7/30 진입분</div></div>
<div class=kpi><div class=l>구 카드 실현(전량)</div><div class=v>+{old:.1f}%</div><div class=n>목표에서 전량 청산</div></div>
<div class=kpi><div class=l>신 카드(2단) 현재평가</div><div class=v good>+{new:.1f}%</div><div class=n>차이 +{new-old:.1f}%p (미실현)</div></div>
</div>

<h2>1. 목표 도달 {len(done)}종 — 잔여 50% 트레일 관리표</h2>
<div class=note>과제1에서 채택한 <b>2단 청산</b> 적용 시, 이 종목들은 <b>절반은 목표가에 실현 완료</b>이고
<b>잔여 50%가 살아있다</b>. 아래 <b class=key>잔여 트레일선</b>이 그 절반의 손절 주문 가격이다
(고점比 −12%, 단 본전 미만으로는 내리지 않음). <b>트레일 판정은 8/3(월)부터 개시.</b></div>
<div class=box><table>
<tr><th>종목</th><th class=n>유형</th><th class=n>진입가</th><th class=n>목표가</th><th class=n>현재가</th>
<th class=n>실현 50%</th><th class=n>잔여 평가</th><th class=n>잔여 트레일선</th><th class=n>여유</th></tr>
{rows_done()}
</table></div>
<div class=note>‘여유’ = 현재가 대비 트레일선까지의 거리. 0에 가까울수록 월요일 이탈 위험이 크다.
비츠로셀·한올바이오파마·현대백화점·GS건설은 고점이 낮아 트레일선이 <b>본전(진입가)</b>에 걸려 있다.</div>

<h2>2. 관찰중 {len(open_)}종 — 목표 미도달</h2>
<div class=box><table>
<tr><th>종목</th><th class=n>유형</th><th class=n>진입가</th><th class=n>현재가</th><th class=n>현재수익</th>
<th class=n>손절가</th><th class=n>손절까지</th><th class=n>목표가</th><th class=n>목표까지</th></tr>
{rows_open()}
</table></div>

<h2>3. 월요일(8/3) 실행 체크리스트</h2>
<pre>① 국면 재확인       py 시장국면.py         → 🟢실행이면 신규 휩쏘 탐색 유효
② 신규 탐색         py 휩쏘_탐색기.py       → 2일째 종가 판단. 오늘(월)은 급락1일째면 대기
③ 잔여 50% 주문     위 표 '잔여 트레일선' 가격에 stop 주문 (29종)
                    · 본전선 걸린 4종(비츠로셀·한올바이오파마·현대백화점·GS건설)은
                      본전 이탈 시 잔여도 정리 — 손실 없이 빠진다
④ 관찰 4종          목표까지 4~12% · 손절까지 10~14%. 카드 그대로 유지
⑤ 원장 갱신         py 휩쏘_관찰.py         → 전진 상태 재도장</pre>

<div class=note><b>국면 해설.</b> 지수 1년고점比 −28.2%인데 200일선 위(강세)다. 급등 뒤 초단기 급락이라
장기 추세는 아직 살아있다는 뜻. 20일 변동성 {rg['vol20']*100:.0f}%는 30년 중앙(17.5%)의 5.6배 —
역사검정의 '고변동 × 큰 낙폭' = <b>승리 셀</b>(40일 +8.5% · 승 57%)에 정확히 들어와 있다.
다만 이 표본은 위기해에 몰려 있어 개별 재현은 보장되지 않는다.</div>

<footer>
재현: <code>휩쏘_원장점검_20260802.py</code> · <code>시장국면.py</code> · 원장 <code>휩쏘_관찰.csv</code><br>
가격 = 종목일봉_30년 {rg['date']} 종가 기준. 잔여 평가익은 <b>미실현</b>이다.<br>
⚠️ 검정·관리용 문서. 매매 추천이 아니다.
</footer>
</div></body></html>"""
open(f"{HERE}/휩쏘_현황_20260802.html", "w", encoding="utf-8").write(doc)
print("저장: 휩쏘_현황_20260802.html")
