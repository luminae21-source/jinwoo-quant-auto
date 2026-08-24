# -*- coding: utf-8 -*-
r"""jq_console.py — 진우퀀트 콘솔 (Streamlit 앱)

흩어진 도구를 한 앱으로: 연구현황 · 딥밸류 타점 · 백테 · 라이브 전진기록.
로컬 CSV(진우퀀트 폴더)를 그대로 읽는다. qmj_engine.py 재사용.

실행: streamlit run jq_console.py       (런처 .bat이 파이썬 자동선택)
데이터경로: 환경변수 JQ_DATA 또는 이 파일이 있는 폴더.
"""
import os, sys
import numpy as np, pandas as pd, streamlit as st

BASE = os.environ.get("JQ_DATA") or os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qmj_engine as E
E.DATA = BASE   # 엔진 로더가 참조하는 데이터 폴더 재지정

st.set_page_config(page_title="진우퀀트 콘솔", page_icon="📈", layout="wide")

# ---------- 공통 스타일(차분한 톤) ----------
st.markdown("""<style>
 .stApp{background:#f7f6f3}
 .block-container{padding-top:2rem;max-width:1150px}
 h1,h2,h3{color:#2b2b2b}
 .verdict{display:inline-block;padding:3px 12px;border-radius:16px;color:#fff;font-weight:700;font-size:13px}
 .metricbox{background:#fff;border:1px solid #e7e4dd;border-radius:12px;padding:14px 16px}
</style>""", unsafe_allow_html=True)

def pct(x,p=1):
    try: return f"{x*100:+.{p}f}%"
    except Exception: return "-"

@st.cache_data(show_spinner=False)
def load_core():
    close=E.load_monthly_close(); idx=close.index; cols=close.columns
    pbr=E.load_pbr(idx,cols); bull,kret=E.load_regime(idx)
    sig=E.build_signals(close,pbr); qp=E.quality_panel(idx,cols)
    return close,pbr,bull,kret,sig,qp

@st.cache_data(show_spinner=False)
def load_adtv():
    p=os.path.join(BASE,"kospi_pit_daily.csv")
    if not os.path.exists(p): return None
    d=pd.read_csv(p,dtype={"code":str},usecols=["code","date","close","volume"])
    d["code"]=d["code"].str.zfill(6); dt=pd.to_datetime(d["date"],errors="coerce")
    d["m"]=dt.dt.to_period("M"); d["close"]=pd.to_numeric(d["close"],errors="coerce")
    d["volume"]=pd.to_numeric(d["volume"],errors="coerce"); d=d.dropna(subset=["m","close"])
    d["tv"]=d["close"]*d["volume"]
    return d.groupby(["m","code"])["tv"].mean().unstack().sort_index()

# ================= 사이드바 =================
st.sidebar.title("📈 진우퀀트 콘솔")
page=st.sidebar.radio("이동", ["🏁 연구 현황","🎯 딥밸류 타점","📊 백테","📓 라이브 기록"])
st.sidebar.caption(f"데이터: {BASE}")
data_ok=os.path.exists(os.path.join(BASE,"kospi_pit_daily.csv"))
if not data_ok:
    st.sidebar.error("kospi_pit_daily.csv 없음.\n진우퀀트 폴더에서 실행하세요.")

# ================= 페이지 1: 연구 현황 =================
if page.startswith("🏁"):
    st.title("5대 ★★★ 트랙 — 연구 현황")
    st.caption("2026-07-22 검증 · 정직판정. 통과만 시스템에, 기각은 기록.")
    rows=[("#2 퀄리티 오버레이(QMJ)","기각","#b4654a","딥밸류 내 우량주가 정크보다 유의하게 낮음(ALL −13%p·P0.999). 트랩회피는 대형주라 측정불가."),
          ("#4 낙폭완화(국면 비중조절)","부분채택","#c9973f","단순 국면타이밍=기각(휩쏘). 변동성타깃=유효(−49%→−33%, 수익 비례희생)."),
          ("#3 비용·유동성 완비","조건부·용량제약","#c9973f","소액만 근근이 +1.4%(1억), 1000억선 −14%/MDD−71%. 유동성이 진짜 벽."),
          ("#1 일본·홍콩 재현","PC 이관","#5b7fa6","클라우드 야후·stooq 403차단. 원클릭 .bat 제공, 결과 대기."),
          ("#5 라이브 전진기록","도구 완성","#5a8f6b","월 1줄 입력→누적통계+기대괴리 t검정. 측정은 시간이 쌓임(이 앱 라이브기록 탭).")]
    for name,v,c,desc in rows:
        with st.container():
            a,b=st.columns([0.32,0.68])
            a.markdown(f"**{name}**")
            a.markdown(f"<span class='verdict' style='background:{c}'>{v}</span>",unsafe_allow_html=True)
            b.write(desc)
            st.divider()
    st.info("가장 큰 소득: 순수 딥밸류 엣지의 견고성이 여러 각도에서 재확인됨. 그 위에 얹으려던 QMJ는 근거없음으로 확정.")

# ================= 페이지 2: 딥밸류 타점 =================
elif page.startswith("🎯") and data_ok:
    st.title("딥밸류 타점 — 최신월 반등군 후보")
    close,pbr,bull,kret,sig,qp=load_core()
    adtv=load_adtv()
    months=list(close.index)
    msel=st.selectbox("기준월", months[::-1], index=0, format_func=str)
    ti=months.index(msel)
    regime="🟥 하락장(RISK_OFF·신규진입 허용)" if not bool(bull.iloc[ti]) else "🟩 강세장(신규 보류)"
    st.markdown(f"**국면:** {regime}")
    row=sig["reb"].iloc[ti]
    cands=list(close.columns[row.values])
    disp=(close/close.rolling(10).mean()); ret1=close.pct_change()
    recs=[]
    for c in cands:
        recs.append(dict(종목=c,
            PBR=round(float(pbr.iloc[ti][c]),2) if pd.notna(pbr.iloc[ti][c]) else None,
            이격=round(float(disp.iloc[ti][c]),3) if pd.notna(disp.iloc[ti][c]) else None,
            _1M수익=pct(ret1.iloc[ti][c]),
            일ADTV억=round(float(adtv.loc[msel][c])/1e8,1) if (adtv is not None and msel in adtv.index and c in adtv.columns and pd.notna(adtv.loc[msel][c])) else None,
            퀄리티=round(float(qp["Quality"].iloc[ti][c]),2) if pd.notna(qp["Quality"].iloc[ti][c]) else None))
    st.caption(f"반등군 = 저PBR20% ∩ 이격<0.85 ∩ 1M수익>0 · 후보 {len(recs)}종")
    if recs:
        df=pd.DataFrame(recs).sort_values("_1M수익",ascending=False)
        st.dataframe(df, use_container_width=True, height=460)
        st.caption("※ 퀄리티는 참고용(검증상 딥밸류 수익과 역상관). 상폐/생존편향·투자자문 아님·결정 본인.")
    else:
        st.warning("이 달엔 반등군 후보 없음(강세장이거나 조건 미충족).")

# ================= 페이지 3: 백테 =================
elif page.startswith("📊") and data_ok:
    st.title("백테 — 딥밸류 슬리브 (상폐반영·하락장진입)")
    close,pbr,bull,kret,sig,qp=load_core()
    c1,c2,c3=st.columns(3)
    maxpos=c1.slider("최대 종목수",5,30,15); hold=c2.slider("보유개월",3,24,12)
    overlay=c3.selectbox("퀄리티 오버레이",["없음(기준)","QMJ 상위50%","QMJ 상위33%"])
    qmin={"없음(기준)":None,"QMJ 상위50%":0.50,"QMJ 상위33%":0.67}[overlay]
    with st.spinner("백테 계산..."):
        mret=E.monthly_return_delist_aware(close)
        r=E.portfolio_backtest(close,sig,bull,kret,mret,maxpos=maxpos,hold=hold,
                               qpanel=qp if qmin else None,q_min_rank=qmin)
        sr=r["sleeve"]; stt=E.stats_block(sr); eq=(1+sr).cumprod()
    m1,m2,m3,m4=st.columns(4)
    m1.metric("CAGR",pct(stt["CAGR"])); m2.metric("MDD",pct(stt["MDD"]))
    m3.metric("Sharpe",f"{stt['Sharpe']:.2f}"); m4.metric("Calmar",f"{stt['Calmar']:.2f}")
    eq.index=eq.index.astype(str)
    st.line_chart(eq, height=320)
    st.caption(f"기간 {sr.index.min()}~{sr.index.max()} · {stt['월수']}개월 · 매수15bp/매도33bp · 상폐 -100% 반영.")
    st.caption("※ 검증결론: QMJ 오버레이는 통계적으로 수익을 높이지 못함(기각). 이 화면은 파라미터 탐색·교육용.")

# ================= 페이지 4: 라이브 기록 =================
elif page.startswith("📓"):
    st.title("라이브 전진기록 (#5) — 백테를 라이브가 확증")
    LED=os.path.join(BASE,"진우_라이브전진기록.csv")
    def load_led():
        if os.path.exists(LED): return pd.read_csv(LED,dtype={"month":str})
        return pd.DataFrame(columns=["month","sleeve_ret","bench_ret","n_hold","note"])
    df=load_led()
    with st.form("add"):
        st.write("이번 달 실현 입력")
        c1,c2,c3,c4=st.columns(4)
        m=c1.text_input("월(YYYY-MM)")
        s=c2.number_input("슬리브 수익(소수, 예 0.031)",value=0.0,format="%.4f",step=0.001)
        b=c3.number_input("벤치(KOSPI) 수익",value=0.0,format="%.4f",step=0.001)
        n=c4.number_input("보유종목수",value=0,step=1)
        note=st.text_input("메모")
        if st.form_submit_button("기록 추가"):
            if m:
                df=df[df["month"]!=m]
                df=pd.concat([df,pd.DataFrame([dict(month=m,sleeve_ret=s,bench_ret=b,n_hold=int(n),note=note)])],ignore_index=True).sort_values("month")
                df.to_csv(LED,index=False,encoding="utf-8-sig"); st.success(f"기록: {m}")
    if len(df):
        sv=df["sleeve_ret"].astype(float); bv=df["bench_ret"].astype(float); ex=sv-bv
        e=(1+sv).cumprod(); nn=len(sv)
        cg=(e.iloc[-1]**(12/nn)-1) if e.iloc[-1]>0 else float("nan")
        m1,m2,m3=st.columns(3)
        m1.metric("누적배수",f"{e.iloc[-1]:.2f}x"); m2.metric("연율CAGR",pct(cg))
        m3.metric("월평균 초과",pct(ex.mean(),2))
        d2=df.copy(); d2["_누적"]=e.values
        chart=d2.set_index("month")["_누적"]; st.line_chart(chart,height=260)
        st.dataframe(df.iloc[::-1],use_container_width=True)
        if nn>=6 and ex.std()>0:
            t=(ex.mean()-0.010)/(ex.std()/np.sqrt(nn))
            msg="⚠️ 기대와 상충" if t<-2 else "✅ 기대와 부합" if abs(t)<=2 else "🎯 기대상회"
            st.info(f"백테기대(+1%p/월) 대비 t={t:+.2f} → {msg}")
        else:
            st.caption("6개월 이상 쌓이면 기대괴리 t검정 표시.")
    else:
        st.caption("아직 기록 없음. 위 폼으로 매월 실현을 한 줄씩 추가하세요. 판정은 6~12개월 누적으로만.")

elif not data_ok:
    st.title("데이터 필요")
    st.error("이 앱은 진우퀀트 폴더의 CSV를 읽습니다. 그 폴더 안에서 런처(.bat)로 실행하세요.")
