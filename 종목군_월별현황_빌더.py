# -*- coding: utf-8 -*-
"""종목군 × 월별 현황판 — 기록용. 판정이 아니다."""
import json, sys, html as H
sys.stdout.reconfigure(encoding="utf-8")
import 차트도구 as T
HERE = "/home/claude/jq"
D = json.load(open(f"{HERE}/종목군_월별현황.json"))
esc = H.escape
S1, S2c, S3 = "var(--s1)", "var(--s2)", "var(--s3)"
M = D["메타"]; SB = D["생존편향"]; GS = {r["군"]: r for r in D["군요약"]}
VS = {r["군"]: r for r in D["밸류요약"]}; ALL = D["전체요약"]
GC = {r["월"]: r for r in D["갭집중"]}
MON = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월", "10월", "11월", "12월"]

# 차트 1 — 월별 신호 발생 (국면 구성)
c1 = T.grouped(MON,
               [dict(name="🟢실행", color=S1, vals=[r["실행"] for r in D["월별국면"]]),
                dict(name="🟡주의", color=S2c, vals=[r["주의"] for r in D["월별국면"]]),
                dict(name="🔴관찰만", color=S3, vals=[r["관찰만"] for r in D["월별국면"]])],
               w=760, h=290, unit="건", title="월별 신호 발생 건수", signed=False, dec=0)
t1 = T.tbl(["월", "🟢실행", "🟡주의", "🔴관찰만", "합계"],
           [[f'{r["월"]}월', f'{r["실행"]:,}', f'{r["주의"]:,}', f'{r["관찰만"]:,}', f'{r["합계"]:,}']
            for r in D["월별국면"]])

# 차트 2 — 월별 종목군 구성
c2 = T.grouped(MON,
               [dict(name="반도체 체인", color=S1, vals=[r["체인"]["n"] for r in D["월별종목군"]]),
                dict(name="기타 업종", color=S2c, vals=[r["기타"]["n"] for r in D["월별종목군"]]),
                dict(name="섹터 불명(상폐 등)", color=S3, vals=[r["불명"]["n"] for r in D["월별종목군"]])],
               w=760, h=290, unit="건", title="월별 종목군 구성 (🟢실행 국면)", signed=False, dec=0)

# 차트 3 — 생존편향 실측
c3 = T.hbar_ci([dict(label="섹터 확인됨 (지금도 상장)", v=SB["섹터있음"]["카드"],
                     note=f'n={SB["섹터있음"]["n"]:,} · 승률 {SB["섹터있음"]["승률"]}%', color=S1),
                dict(label="섹터 불명 (대부분 사라진 종목)", v=SB["섹터불명"]["카드"],
                     note=f'n={SB["섹터불명"]["n"]:,} · 승률 {SB["섹터불명"]["승률"]}%', color=S2c)],
               w=760, pad_l=230, title="생존편향 실측 — 카드 수익률")
c3b = T.hbar_ci([dict(label="섹터 확인됨", v=SB["섹터있음"]["fwd40"], color=S1,
                      note=f'목표도달 {SB["섹터있음"]["목표율"]}% · 손절 {SB["섹터있음"]["손절율"]}%'),
                 dict(label="섹터 불명", v=SB["섹터불명"]["fwd40"], color=S2c,
                      note=f'목표도달 {SB["섹터불명"]["목표율"]}% · 손절 {SB["섹터불명"]["손절율"]}%')],
                w=760, pad_l=230, title="생존편향 실측 — 40일 수익률")

# 차트 4 — 카드 vs 40일 (군별)
c4 = T.grouped(["반도체 체인", "기타 업종", "섹터 불명", "밸류 O", "밸류 X"],
               [dict(name="카드로 팔면", color=S1,
                     vals=[GS["반도체체인"]["카드"], GS["기타업종"]["카드"], GS["섹터불명"]["카드"],
                           VS["밸류 태그 O"]["카드"], VS["밸류 태그 X"]["카드"]]),
                dict(name="40일 그냥 두면", color=S2c,
                     vals=[GS["반도체체인"]["fwd40"], GS["기타업종"]["fwd40"], GS["섹터불명"]["fwd40"],
                           VS["밸류 태그 O"]["fwd40"], VS["밸류 태그 X"]["fwd40"]])],
               w=760, h=280, title="카드 청산 vs 40일 보유")
t4 = T.tbl(["종목군", "건수", "카드", "승률", "40일", "갭", "목표도달율", "손절율"],
           [[k, f'{v["n"]:,}', f'{v["카드"]:+.2f}%', f'{v["승률"]}%', f'{v["fwd40"]:+.2f}%',
             f'{v["갭"]:+.2f}%p', f'{v["목표율"]}%', f'{v["손절율"]}%']
            for k, v in list(GS.items()) + list(VS.items())])

# 차트 5 — 월별 갭 (경고 포함)
c5 = T.grouped(MON,
               [dict(name="반도체 체인", color=S1, vals=[r["체인갭"] for r in D["갭월별"]]),
                dict(name="기타 업종", color=S2c, vals=[r["기타갭"] for r in D["갭월별"]])],
               w=760, h=300, unit="%p", title="월별 갭 (40일 − 카드)")
t5 = T.tbl(["월", "체인 갭", "체인 n", "기타 갭", "기타 n", "체인 표본의 최다 연도", "그 해 비중"],
           [[f'{r["월"]}월', f'{r["체인갭"]:+.1f}%p' if r["체인갭"] is not None else "–", r["체인n"],
             f'{r["기타갭"]:+.1f}%p' if r["기타갭"] is not None else "–", r["기타n"],
             f'{GC[r["월"]]["최다연도"]}년' if GC[r["월"]]["최다연도"] else "–",
             f'{GC[r["월"]]["비중"]:.0f}%' if GC[r["월"]].get("비중") else "–"]
            for r in D["갭월별"]])

# 차트 6 — 연도별
YR = [r for r in D["연도별"] if r["합계"] >= 1]
c6 = T.vbar([dict(label=str(r["연"])[2:], v=r["합계"], sub=f'{r["체인"]}') for r in YR],
            w=760, h=250, unit="건", title="연도별 신호 발생 (아래 회색=체인)", signed=False, dec=0)
t6 = T.tbl(["연도", "전체", "🟢실행", "체인", "실행 카드 평균"],
           [[r["연"], f'{r["합계"]:,}', f'{r["실행"]:,}', r["체인"],
             f'{r["카드"]:+.2f}%' if r["카드"] is not None else "–"] for r in YR])

# 차트 7 — 섹터 매칭률
c7 = T.vbar([dict(label=r["연대"], v=r["비율"], sub=f'{r["매칭"]:,}/{r["전체"]:,}') for r in D["매칭률"]],
            w=760, h=230, title="연대별 섹터 매칭률", signed=False, dec=0)

DS = {r["군"]: r for r in D["도달속도"]}
CSS = open(f"{HERE}/보고서_빌더.py", encoding="utf-8").read()
CSS = CSS[CSS.index('CSS = """') + 9:CSS.index('"""\nprint("css ok")')]

BODY = f"""
<header>
<h1>종목군 × 월별 현황판</h1>
<p class="lead">휩쏘 신호가 언제·어떤 종목군에서 얼마나 떴고, 어떻게 끝났는지의 <b>기록</b></p>
<p class="meta">{M['기간']} · 전체 {M['전체']:,}건 · 성과 판정 가능 {M['창완결']:,}건 · 🟢실행 {M['실행']:,}건</p>
</header>

<div class="callout stop">
<div class="t">먼저 — 이건 '판정'이 아니라 '기록'입니다</div>
아래 숫자는 <b>무엇이 일어났는지</b>를 보여줄 뿐, <b>무엇을 해야 하는지</b>를 말하지 않습니다.
월별로 쪼개면 칸당 표본이 중앙 71건까지 줄어드는데, 이 시스템의 실제 효과크기(0.5~2%p)를
탐지하려면 칸당 200건 이상이 필요합니다. <b>그래서 이 표에서 "3월이 좋다" 같은 결론을 내리면 안 됩니다.</b><br><br>
<span class="dim">또한 이건 <b>형이 실제로 매매한 기록이 아니라</b>, 규칙을 과거에 적용했을 때의 시뮬레이션입니다.
실제 추적 중인 건 관찰 원장 33종뿐입니다.</span>
</div>

<h2 id="s1"><span class="num">1</span>가장 먼저 눈에 띈 것 — 사라진 종목들</h2>
<p class="sec-lead">종목군을 나누려고 업종 데이터를 붙이다가 뜻밖의 게 나왔습니다.</p>
<p>전체 종목 {SB['섹터있음종목'] + SB['섹터불명종목']:,}종 중 <b>{SB['섹터불명종목']}종은 업종을 붙일 수가 없습니다.</b>
업종 파일은 <b>지금 상장돼 있는 종목</b>만 담고 있으니까요. 즉 이 {SB['섹터불명종목']}종은
<b>그 사이에 상장폐지되거나 합병으로 사라진 회사들</b>입니다.</p>
<p>그래서 이 둘을 갈라 봤습니다.</p>
<figure>{c3}
<figcaption><b>카드 수익률.</b> 사라진 종목 쪽이 {SB['섹터있음']['카드'] - SB['섹터불명']['카드']:.2f}%p 낮습니다.</figcaption></figure>
<figure>{c3b}
<figcaption><b>40일 수익률.</b> 격차가 훨씬 큽니다 — {SB['섹터있음']['fwd40']:+.2f}% vs <b>{SB['섹터불명']['fwd40']:+.2f}%</b>.</figcaption></figure>

<div class="big">지금 살아있는 회사: 카드 <span class="g">{SB['섹터있음']['카드']:+.2f}%</span> · 승률 {SB['섹터있음']['승률']}% · 40일 <span class="g">{SB['섹터있음']['fwd40']:+.2f}%</span>
<br>그 사이 사라진 회사: 카드 <span class="w">{SB['섹터불명']['카드']:+.2f}%</span> · 승률 {SB['섹터불명']['승률']}% · 40일 <span class="b">{SB['섹터불명']['fwd40']:+.2f}%</span></div>

<div class="callout warn">
<div class="t">이게 왜 중요한가 — 생존편향의 크기를 처음으로 실측했습니다</div>
그동안 모든 판정문에 "생존편향 때문에 실제는 이보다 나쁘다"고 적어왔지만 <b>얼마나 나쁜지는 몰랐습니다.</b>
이제 대략 알 수 있습니다 — 사라진 종목들은 카드 기준 <b>{SB['섹터있음']['카드'] - SB['섹터불명']['카드']:.2f}%p</b>,
40일 기준 <b>{SB['섹터있음']['fwd40'] - SB['섹터불명']['fwd40']:.1f}%p</b> 나빴습니다.
손절률도 {SB['섹터불명']['손절율']}%로 {SB['섹터있음']['손절율']}%보다 높습니다.<br><br>
<b>그리고 이건 하한선입니다.</b> 여기 잡힌 {SB['섹터불명종목']}종은 그래도 데이터에 남아 있는 종목들이고,
데이터 수집 자체에서 빠진 종목은 셀 수조차 없습니다.<br><br>
<b>실무적 결론: 업종으로 종목군을 나누는 분석은 이 편향을 피할 수 없습니다.</b>
아래 2~4장은 그 사실을 알고 읽어야 합니다.
</div>

<figure>{c7}
<figcaption><b>연대별 업종 매칭률.</b> 1990년대는 절반만 붙고, 2020년대는 거의 다 붙습니다.
<b>옛날로 갈수록 "살아남은 종목만" 남는다는 뜻</b>입니다.</figcaption></figure>

<h2 id="s2"><span class="num">2</span>언제 신호가 뜨는가</h2>
<figure>{c1}
<figcaption><b>월별 신호 발생 건수와 그때의 시장 국면.</b> 3월과 8월이 많고, 그 대부분이 🟢실행 국면입니다.
{t1}</figcaption></figure>
<p>신호가 많은 달은 <b>시장이 그때 많이 빠졌던 달</b>입니다. 계절성이라기보다 <b>위기가 언제 있었나</b>의 기록에 가깝습니다.</p>
<figure>{c2}
<figcaption><b>월별 종목군 구성</b> (🟢실행 국면). 반도체 체인은 전체의 {GS['반도체체인']['n'] / M['실행'] * 100:.0f}% 수준으로 꾸준합니다.</figcaption></figure>

<h2 id="s3"><span class="num">3</span>종목군별로 어떻게 끝났는가</h2>
<figure>{c4}
<figcaption><b>카드로 팔았을 때 vs 40일 그냥 뒀을 때.</b> 파란 막대가 실제 규칙, 주황이 손절 없이 40일 보유했을 때입니다.
{t4}</figcaption></figure>

<div class="big">반도체 체인 — 카드 <span class="g">{GS['반도체체인']['카드']:+.2f}%</span> 인데 40일 두면 <span class="g">{GS['반도체체인']['fwd40']:+.2f}%</span>
<br>기타 업종 — 카드 {GS['기타업종']['카드']:+.2f}% 인데 40일 두면 {GS['기타업종']['fwd40']:+.2f}%
<br><br>갭이 <b>{GS['반도체체인']['갭']:.1f}%p</b> vs <b>{GS['기타업종']['갭']:.1f}%p</b> — 체인 쪽이 <b>{GS['반도체체인']['갭'] / GS['기타업종']['갭']:.1f}배</b>입니다.</div>

<div class="callout">
<div class="t">이게 다음 과제(①)로 가는 다리입니다</div>
카드 성과는 체인({GS['반도체체인']['카드']:+.2f}%)이나 기타({GS['기타업종']['카드']:+.2f}%)나 거의 같습니다.
승률도 둘 다 {GS['반도체체인']['승률']}% 수준으로 동일합니다.<br>
<b>그런데 "그냥 뒀을 때"는 완전히 다릅니다.</b> 체인이 두 배 가까이 갑니다.<br><br>
읽는 법: <b>체인은 목표가를 찍고 나서도 계속 간다</b>는 뜻일 수 있습니다.
현재 목표가는 "급락폭의 절반 되돌림"인데, 체인은 그 절반을 훌쩍 넘어간다는 것이죠.<br>
<span class="dim">⚠️ 단, 40일 수익은 <b>손절 없이</b> 그냥 보유한 값이라 카드와 직접 비교할 수 없습니다.
체인 vs 기타의 <b>상대 비교</b>만 유효합니다. 실제로 목표를 늘려야 하는지는 ①에서 제대로 검정해야 합니다.</span>
</div>

<h3>목표는 얼마나 빨리 도달하는가</h3>
<table class="m"><thead><tr><th>종목군</th><th>목표 도달 건수</th><th>중앙</th><th>75%</th><th>90%</th><th>이틀 안</th><th>일주일 안</th></tr></thead><tbody>
{"".join(f'<tr><td>{esc(k)}</td><td>{v["n"]:,}건</td><td>{v["p"][1]["v"]:.0f}봉</td><td>{v["p"][2]["v"]:.0f}봉</td><td>{v["p"][3]["v"]:.0f}봉</td><td>{v["일봉이내"]}%</td><td>{v["일주일이내"]}%</td></tr>' for k, v in DS.items())}
</tbody></table>
<p><b>목표 도달까지 중앙 2봉 — 이틀입니다.</b> 체인은 {DS.get('반도체체인', {}).get('일봉이내', 0)}%가 이틀 안에 목표를 찍습니다.
사고 이틀 만에 절반을 팔고 나오는 구조라는 뜻이고, 그래서 <b>그 뒤에 오는 상승을 통째로 놓칩니다.</b></p>

<h2 id="s4"><span class="num">4</span>월별로 갈리는가 — 여기가 함정입니다</h2>
<figure>{c5}
<figcaption><b>월별 갭 (40일 − 카드).</b> 3월이 튀고 5월이 음수로 튑니다. 그런데…
{t5}</figcaption></figure>

<div class="callout stop">
<div class="t">이 그림을 계절성으로 읽으면 안 됩니다</div>
표를 열어 맨 오른쪽 두 칸을 보세요. <b>월별 패턴은 특정 한 해가 만들고 있습니다.</b>
<table class="m"><thead><tr><th>월</th><th>체인 갭</th><th>표본</th><th>최다 연도</th><th>그 해가 차지하는 비중</th></tr></thead><tbody>
<tr><td>3월</td><td class="g">{D['갭월별'][2]['체인갭']:+.1f}%p</td><td>{D['갭월별'][2]['체인n']}건</td><td><b>2026년</b></td><td class="b">44% (상위 2개 연도 77%)</td></tr>
<tr><td>5월</td><td class="b">{D['갭월별'][4]['체인갭']:+.1f}%p</td><td>{D['갭월별'][4]['체인n']}건</td><td><b>2026년</b></td><td class="b">47% (상위 2개 연도 62%)</td></tr>
<tr><td>12월</td><td>{D['갭월별'][11]['체인갭']:+.1f}%p</td><td>{D['갭월별'][11]['체인n']}건</td><td>2024년</td><td class="b">50% (상위 2개 78%)</td></tr>
</tbody></table>
3월 체인 164건 중 <b>72건이 2026년, 55건이 2020년</b>(코로나)입니다. 즉 "3월이 좋다"가 아니라
<b>"2026년과 2020년이 좋았고, 그게 마침 3월이었다"</b>가 맞습니다.<br><br>
5월도 마찬가지로 <b>32건이 2026년</b>이고, 2026년 5월 갭이 −29.5%p라 전체를 끌어내렸습니다.<br><br>
<b>결론: 월별 칸은 계절 정보가 아니라 사건 정보입니다.</b> 30년을 12칸으로 나눴지만,
실제로는 몇 개의 큰 사건이 칸마다 다르게 흩어져 있을 뿐입니다.
</div>

<h2 id="s5"><span class="num">5</span>연도별 — 사건의 기록으로 읽기</h2>
<figure>{c6}
<figcaption><b>연도별 신호 발생 건수.</b> 막대 아래 회색 숫자는 그중 반도체 체인 건수입니다.
{t6}</figcaption></figure>
<p>신호는 <b>위기 해에 몰립니다.</b> 이게 이 시스템의 성격이자 한계입니다 —
표본이 독립적이지 않고, 몇 개의 사건에 지배됩니다. 그래서 모든 판정에 <b>연도블록 부트스트랩</b>을 씁니다.</p>

<h2 id="s6"><span class="num">6</span>그래서 이 현황판이 말하는 것</h2>
<table class="m"><thead><tr><th>본 것</th><th>말할 수 있는 것</th><th>말할 수 없는 것</th></tr></thead><tbody>
<tr><td>사라진 종목 {SB['섹터불명종목']}종의 성과</td><td class="g">생존편향의 크기 ≈ 카드 {SB['섹터있음']['카드'] - SB['섹터불명']['카드']:.1f}%p · 40일 {SB['섹터있음']['fwd40'] - SB['섹터불명']['fwd40']:.1f}%p</td><td class="dim">이게 전부라는 것 (수집 누락분은 셀 수 없음)</td></tr>
<tr><td>체인 vs 기타 카드 성과</td><td class="g">거의 같다 ({GS['반도체체인']['카드']:+.2f}% vs {GS['기타업종']['카드']:+.2f}%)</td><td class="dim">→ 종목군별로 손절·트레일을 다르게 할 근거는 없다</td></tr>
<tr><td>체인 vs 기타 40일 갭</td><td class="w">체인이 {GS['반도체체인']['갭'] / GS['기타업종']['갭']:.1f}배 크다 — 검정할 가치가 있다</td><td class="dim">"목표를 늘려야 한다" (손절 없는 값이라 직접 비교 불가)</td></tr>
<tr><td>월별 패턴</td><td class="dim">거의 없다 — 특정 연도가 만든 착시</td><td class="b">"3월에 사라" 같은 결론</td></tr>
<tr><td>목표 도달 속도</td><td class="g">중앙 2봉 · 이틀 안에 {DS.get('반도체체인', {}).get('일봉이내', 0)}%</td><td class="dim">그게 너무 빠른지 (①에서 검정)</td></tr>
</tbody></table>

<div class="callout ok">
<div class="t">다음 단계 — 과제 ①</div>
이 현황판이 가리키는 곳은 하나입니다: <b>"체인은 목표를 찍고도 계속 가는데, 카드가 이틀 만에 절반을 판다."</b><br><br>
①에서 제대로 물어야 할 것:
<ul>
<li>목표가를 "급락폭 절반 되돌림"에서 늘리면 종목군별로 어떻게 달라지는가 (손절 유지한 채로)</li>
<li>2단 청산의 잔여분 트레일을 종목군별로 다르게 하면 나은가</li>
<li>표본: 체인 {GS['반도체체인']['n']}건 vs 기타 {GS['기타업종']['n']:,}건 — <b>주효과 비교는 검정력 충분</b></li>
<li>단, <b>월별로 쪼개지 않는다</b>. 4장에서 본 대로 월 칸은 사건 정보일 뿐이다</li>
</ul>
</div>

<footer>
<b>종목군 × 월별 현황판</b> — 2026-08-02 · 진우퀀트<br>
재현: <code>종목군_월별현황_데이터.py</code> → <code>종목군_월별현황_빌더.py</code> · 타당성: <code>종목군_타당성점검.py</code><br>
업종 분류: <code>liquidity_sector.csv</code> + <code>kosdaq_industry.csv</code> (현재 시점 스냅숏) ·
반도체 체인 정의: {esc(M['체인정의'])}<br><br>
⚠️ <b>기록용 문서이며 투자 권유가 아닙니다.</b> 실제 매매 기록이 아니라 과거 규칙 적용 시뮬레이션입니다.
1장의 생존편향이 모든 숫자에 적용됩니다.
</footer>
"""

DOC = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>종목군 × 월별 현황판 — 진우퀀트</title>
<style>{CSS}</style></head><body><div class="wrap">{BODY}</div></body></html>"""
open(f"{HERE}/종목군_월별현황.html", "w", encoding="utf-8").write(DOC)
print(f"저장: 종목군_월별현황.html ({len(DOC):,} bytes)")
