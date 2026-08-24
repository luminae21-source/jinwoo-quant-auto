#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
theme_heat.py — 뜨거운 테마 모니터 (발굴 트랙 surfacing 레이어) + 종목 차트 연동
==============================================================================
목적: 전 시장 포괄 백본(theme_classify) 위에 랭킹+모멘텀 레이어를 얹어 "지금 뜨거운
      테마"를 띄우고, 상위 종목 클릭 시 월봉 차트(regime 밴드+추세선+진입)를 본다.
      매수신호 아님(발굴≠매수≠검증).

엔진 무수정 재사용: theme_classify(coarse_sector·load_fine_map) +
  supercycle_overlay(_excess_breadth·detect_supercycle). 둘 다 소스 직접 컴파일 로드(스테일 .pyc 회피).

heat_score = 100·(0.45·pct(exc_3m)+0.25·pct(exc_6m)+0.15·pct(exc_1m)+0.15·pct(breadth_3m)).
  supercycle(12M·3개월지속)=점수 분리 확립태그. accel=exc_1m>exc_3m/3.

차트(자기완결·CDN 무의존, 인라인 canvas) — 주봉:
  · 주봉 캔들(kospi/kosdaq 일봉→W-FRI) + 거래량 바. 정합 게이트 PASS 후 도입
    (verify_weekly_reconcile: 월말종가 99.8%·수익환원/주봉무결성 100%).
  · 40주선 = 일봉 200일선 등가(MA200) + SEPA-lite 진입(▲ = 40주선 상회+상승전환).
  · regime 밴드 = regime_history_v40(MA200 기반 시장레짐) RISK_ON/NEUTRAL/OFF.
  · 일봉 미보유(신규상장 등)는 월봉 라인 fallback.

산출: theme_heat_latest.csv · theme_heat_members_latest.csv ·
      뜨거운테마_브리핑_YYYY-MM-DD.md · 뜨거운테마_패널_YYYY-MM-DD.html
재무: fundamentals_pit+kosdaq 최신 FY 매출YoY·영업이익률·ROE(재계산). 없으면 n/a.
정직가드: 시장 EW 월|x|>15% 달이 활성창에 있으면 극단 레짐 경고.
사용: python theme_heat.py [--selftest] [--top N] [--min-members N]
"""
import argparse, os, sys, types, json
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_src(fname, modname):
    path = os.path.join(HERE, fname)
    src = open(path, encoding="utf-8").read()
    m = types.ModuleType(modname); m.__file__ = path
    sys.modules[modname] = m
    sys.dont_write_bytecode = True
    exec(compile(src, path, "exec"), m.__dict__)
    return m


def _engines():
    E = _load_src("supercycle_overlay.py", "supercycle_overlay")
    TC = _load_src("theme_classify.py", "theme_classify")
    return E, TC


def load_panel():
    frames = []
    for f in ("kospi_monthly_prices.csv", "kosdaq_monthly_prices.csv"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            d = pd.read_csv(p, parse_dates=["Date"], index_col="Date")
            d.columns = [str(c).zfill(6) for c in d.columns]
            frames.append(d)
    if not frames:
        raise FileNotFoundError("월간 가격 패널 없음")
    panel = pd.concat(frames, axis=1).sort_index()
    panel = panel.loc[:, ~panel.columns.duplicated()]
    return panel


def load_financials():
    frames = []
    for f in ("fundamentals_pit.csv", "fundamentals_kosdaq.csv"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            frames.append(pd.read_csv(p, dtype={"code": str}))
    if not frames:
        return {}
    fd = pd.concat(frames, ignore_index=True)
    fd["code"] = fd["code"].str.zfill(6)
    fd = fd.dropna(subset=["fiscal_year"]).sort_values(["code", "fiscal_year"])
    out = {}
    for code, g in fd.groupby("code"):
        g = g.drop_duplicates("fiscal_year", keep="last")
        last = g.iloc[-1]; fy = int(last["fiscal_year"])
        rev, op, ni, eq = last.get("revenue"), last.get("op_income"), last.get("net_income"), last.get("equity")
        prev_rev = g.iloc[-2]["revenue"] if len(g) >= 2 else np.nan
        rev_yoy = (rev / prev_rev - 1) if (pd.notna(rev) and pd.notna(prev_rev) and prev_rev) else np.nan
        op_margin = (op / rev) if (pd.notna(op) and pd.notna(rev) and rev) else np.nan
        roe = (ni / eq) if (pd.notna(ni) and pd.notna(eq) and eq) else np.nan
        out[code] = {"fy": fy, "rev_yoy": rev_yoy, "op_margin": op_margin, "roe": roe}
    return out


def load_size():
    p = os.path.join(HERE, "liquidity_sector.csv"); out = {}
    if os.path.exists(p):
        d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
        for _, r in d.iterrows():
            out[r["code"]] = (r.get("mcap"), r.get("adtv"))
    return out


def load_regime(fname="regime_history_v40.csv"):
    """{ 'YYYY-MM': state }  state∈{RISK_ON,NEUTRAL,RISK_OFF} (MA200 기반 v40 시장레짐)."""
    p = os.path.join(HERE, fname); reg = {}
    if os.path.exists(p):
        d = pd.read_csv(p)
        d = d[d["date"].astype(str).str.match(r"\d{4}-\d{2}")]
        for _, r in d.iterrows():
            reg[str(r["date"])[:7]] = str(r.get("state", ""))
    return reg


def load_daily_for(codes):
    """surfaced 코드들의 일봉 OHLCV {code: DataFrame(index=date, [open,high,low,close,volume])}.
    kospi_pit_daily(거래량 O) + kosdaq_pit_daily(거래량 X) 합본. 게이트 PASS 후 사용."""
    codes = set(codes); frames = []
    for f in ("kospi_pit_daily.csv", "kosdaq_pit_daily.csv"):
        pth = os.path.join(HERE, f)
        if os.path.exists(pth):
            d = pd.read_csv(pth, dtype={"code": str})
            d["code"] = d["code"].str.zfill(6)
            d = d[d["code"].isin(codes)].copy()
            d["date"] = pd.to_datetime(d["date"])
            for col in ("open", "high", "low", "close", "volume"):
                if col not in d.columns:
                    d[col] = np.nan
            frames.append(d[["code", "date", "open", "high", "low", "close", "volume"]])
    if not frames:
        return {}
    alld = pd.concat(frames, ignore_index=True)
    out = {}
    for c, g in alld.groupby("code"):
        out[c] = g.sort_values("date").set_index("date")
    return out


def cum_ret(ret, basket, i, k):
    if i - k + 1 < 0 or not basket:
        return np.nan
    win = slice(i - k + 1, i + 1)
    bm = ret[basket].iloc[win].mean(axis=1)
    return float((1 + bm).prod() - 1)


def member_cum(ret, code, i, k):
    if i - k + 1 < 0 or code not in ret.columns:
        return np.nan
    win = slice(i - k + 1, i + 1)
    s = ret[code].iloc[win]
    if s.isna().all():
        return np.nan
    return float((1 + s.fillna(0)).prod() - 1)


def compute_theme_heat(panel, fine, name, E, TC, min_members=5, i=None):
    cm, groups = {}, {}
    for c, s in fine.items():
        g = TC.coarse_sector(name.get(c, ""), s)
        cm[c] = g; groups.setdefault(g, []).append(c)
    cols = set(panel.columns)
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    i = (len(panel) - 1) if i is None else i
    allcols = list(cols)
    m1, m3, m6 = cum_ret(ret, allcols, i, 1), cum_ret(ret, allcols, i, 3), cum_ret(ret, allcols, i, 6)
    rows, members_in = [], {}
    for g, codes in groups.items():
        if g in ("기타", "미분류(섹터없음)"):
            continue
        basket = [c for c in codes if c in cols]
        if len(basket) < min_members:
            continue
        members_in[g] = basket
        ex12, br12 = E._excess_breadth(ret, basket, mkt, i)
        state_on = bool(E.detect_supercycle(ret, {"_": basket}, mkt, i)["_"])
        r1, r3, r6 = cum_ret(ret, basket, i, 1), cum_ret(ret, basket, i, 3), cum_ret(ret, basket, i, 6)
        e1, e3, e6 = r1 - m1, r3 - m3, r6 - m6
        mem3 = pd.Series({c: member_cum(ret, c, i, 3) for c in basket}).dropna()
        breadth_3m = float((mem3 > m3).mean()) if len(mem3) else np.nan
        accel = bool(pd.notna(e1) and pd.notna(e3) and e1 > (e3 / 3.0))
        rows.append({"theme": g, "n": len(basket), "ret_1m": r1, "ret_3m": r3, "ret_6m": r6,
                     "exc_1m": e1, "exc_3m": e3, "exc_6m": e6, "exc_12m": ex12,
                     "breadth_12m": br12, "breadth_3m": breadth_3m,
                     "supercycle": state_on, "accel": accel})
    df = pd.DataFrame(rows)
    if df.empty:
        return df, cm, members_in
    pct = lambda s: s.rank(pct=True)
    df["heat_score"] = 100.0 * (0.45 * pct(df["exc_3m"]) + 0.25 * pct(df["exc_6m"]) +
                                0.15 * pct(df["exc_1m"]) +
                                0.15 * pct(df["breadth_3m"].fillna(df["breadth_3m"].min())))
    df = df.sort_values("heat_score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df, cm, members_in


def surface_members(panel, members_in, themes, fin, size, i, names=None, top_themes=8, per=6):
    names = names or {}
    ret = panel.pct_change(); out = []
    for g in themes[:top_themes]:
        scored = []
        for c in members_in.get(g, []):
            r3 = member_cum(ret, c, i, 3)
            if pd.isna(r3):
                continue
            scored.append((c, r3))
        scored.sort(key=lambda x: -x[1])
        for c, r3 in scored[:per]:
            f = fin.get(c, {}); mc, _ = size.get(c, (np.nan, np.nan))
            out.append({"theme": g, "code": c, "name": names.get(c, c),
                        "ret_1m": member_cum(ret, c, i, 1), "ret_3m": r3,
                        "ret_6m": member_cum(ret, c, i, 6), "ret_12m": member_cum(ret, c, i, 12),
                        "rev_yoy": f.get("rev_yoy", np.nan), "op_margin": f.get("op_margin", np.nan),
                        "roe": f.get("roe", np.nan), "fy": f.get("fy", np.nan), "mcap": mc})
    return pd.DataFrame(out)


def build_chart_data(panel, mdf, regime, daily=None, wk_lookback=156, mo_lookback=60, ES=None, mkt26=0.0, regime_state=""):
    """클릭 차트 데이터. 일봉 보유 종목=주봉 캔들+40주MA(≈MA200)+거래량+SEPA진입,
    미보유=월봉 라인 fallback. regime 밴드(월간 v40)는 양쪽 공통."""
    daily = daily or {}
    out = {}
    for _, r in mdf.iterrows():
        c = r["code"]
        if c in out:
            continue
        if c in daily and len(daily[c]) >= 60:
            g = daily[c]
            w = g.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min",
                                          "close": "last", "volume": "sum"}).dropna(subset=["close"])
            if len(w) < 30:
                continue
            ma = w["close"].rolling(40, min_periods=20).mean()
            cond = (w["close"] > ma) & (ma > ma.shift(4))
            entry = cond & (~cond.shift(1, fill_value=False))
            has_vol = bool(g["volume"].notna().any() and (w["volume"] > 0).any())
            w2 = w.iloc[-wk_lookback:]; ma2 = ma.iloc[-wk_lookback:]; ent2 = entry.iloc[-wk_lookback:]
            dates = [d.strftime("%Y-%m-%d") for d in w2.index]
            regs = [regime.get(d.strftime("%Y-%m"), "") for d in w2.index]
            ent_idx = [k for k, v in enumerate(ent2.values) if bool(v)]
            out[c] = {"name": r["name"], "theme": r["theme"], "type": "weekly", "dates": dates,
                      "o": [round(float(x), 1) for x in w2["open"]],
                      "h": [round(float(x), 1) for x in w2["high"]],
                      "l": [round(float(x), 1) for x in w2["low"]],
                      "c": [round(float(x), 1) for x in w2["close"]],
                      "v": ([int(x) for x in w2["volume"].fillna(0)] if has_vol else []),
                      "ma": [None if pd.isna(x) else round(float(x), 1) for x in ma2],
                      "entries": ent_idx, "regime": regs}
            if ES is not None and len(w) >= 27:
                _rs = float(w["close"].iloc[-1] / w["close"].iloc[-27] - 1) - mkt26
                try:
                    out[c]["plan"] = ES.plan(w, _rs, regime_state)
                except Exception:
                    out[c]["plan"] = None
        else:
            s = panel[c].dropna()
            if len(s) < 6:
                continue
            s = s.iloc[-mo_lookback:]
            sma = s.rolling(12, min_periods=6).mean()
            dates = [d.strftime("%Y-%m") for d in s.index]
            cv, sv = s.values, sma.values
            entries = [k for k in range(1, len(cv))
                       if pd.notna(sv[k]) and pd.notna(sv[k - 1]) and cv[k - 1] <= sv[k - 1] and cv[k] > sv[k]]
            out[c] = {"name": r["name"], "theme": r["theme"], "type": "monthly", "dates": dates,
                      "close": [round(float(x), 1) for x in s.values],
                      "sma": [None if pd.isna(x) else round(float(x), 1) for x in sma.values],
                      "entries": entries, "regime": [regime.get(d, "") for d in dates]}
    return out


def regime_warn(panel, i, lookback=6):
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    win = mkt.iloc[max(0, i - lookback + 1): i + 1]
    big = win[win.abs() > 0.15]
    return [(d.strftime("%Y-%m"), float(v)) for d, v in big.items()]


def _pct(x, d=1):
    return "n/a" if pd.isna(x) else f"{x*100:.{d}f}%"


_CHART_JS = """
var REGCOL = {RISK_ON:'rgba(46,125,80,.16)', NEUTRAL:'rgba(160,135,40,.14)', RISK_OFF:'rgba(160,55,60,.16)', '':'rgba(120,120,120,.04)'};
function _title(d,code,sub){
  var last=(d.type==='weekly'?d.c:d.close); last=last[last.length-1];
  var first=(d.type==='weekly'?d.c:d.close)[0];
  var chg=first?((last/first-1)*100):0;
  return '<b>'+d.name+'</b> <span class="muted">('+code+' · '+d.theme+')</span>  ·  <span class="muted">'+sub+'  '+d.dates[0]+'~'+d.dates[d.dates.length-1]+' '+(chg>=0?'+':'')+chg.toFixed(0)+'%</span>';
}
function showChart(code){
  var d=CHART[code]; if(!d) return;
  document.querySelectorAll('.mrow').forEach(function(x){x.classList.toggle('sel', x.getAttribute('data-code')===code);});
  var cv=document.getElementById('cv'), ctx=cv.getContext('2d');
  var W=cv.width,H=cv.height; ctx.clearRect(0,0,W,H);
  var pad=56,padR=14,padT=14,AX=22;
  function X(i,n){ return pad+(W-pad-padR)*(n<=1?0:i/(n-1)); }
  function bands(n,reg,top,bot){ for(var i=0;i<n;i++){ ctx.fillStyle=(REGCOL[reg[i]]!==undefined?REGCOL[reg[i]]:REGCOL['']); ctx.fillRect(X(i-0.5,n),top,(X(i+0.5,n)-X(i-0.5,n)),bot-top);} }
  if(d.type==='monthly'){
    var n=d.close.length, top=padT, bot=H-AX;
    var vals=d.close.concat(d.sma.filter(function(x){return x!=null;}));
    var lo=Math.min.apply(null,vals),hi=Math.max.apply(null,vals),rng=(hi-lo)||1; lo-=rng*.07; hi+=rng*.07;
    function Ym(v){return top+(bot-top)*(1-(v-lo)/(hi-lo));}
    bands(n,d.regime,top,bot);
    ctx.strokeStyle='#2a2f3a';ctx.beginPath();ctx.moveTo(pad,bot);ctx.lineTo(W-padR,bot);ctx.stroke();
    ctx.fillStyle='#7a818c';ctx.font='10px sans-serif';ctx.textAlign='right';
    [lo,(lo+hi)/2,hi].forEach(function(v){ctx.fillText(Math.round(v).toLocaleString(),pad-6,Ym(v)+3);});
    ctx.textAlign='center';var st=Math.max(1,Math.floor(n/7));
    for(var i=0;i<n;i+=st){ctx.fillText(d.dates[i],X(i,n),H-7);}
    ctx.strokeStyle='#6b9bd1';ctx.lineWidth=1.5;ctx.setLineDash([4,3]);ctx.beginPath();var s2=false;
    for(var i=0;i<n;i++){if(d.sma[i]==null)continue;var x=X(i,n),y=Ym(d.sma[i]);if(!s2){ctx.moveTo(x,y);s2=true;}else ctx.lineTo(x,y);}ctx.stroke();ctx.setLineDash([]);
    ctx.strokeStyle='#ff7a45';ctx.lineWidth=2;ctx.beginPath();
    for(var i=0;i<n;i++){var x=X(i,n),y=Ym(d.close[i]);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.stroke();
    ctx.fillStyle='#ffd479';d.entries.forEach(function(i){var x=X(i,n),y=Ym(d.close[i]);ctx.beginPath();ctx.moveTo(x,y-12);ctx.lineTo(x-5,y-3);ctx.lineTo(x+5,y-3);ctx.closePath();ctx.fill();});
    document.getElementById('charttitle').innerHTML=_title(d,code,'월봉(일봉 미보유 fallback)');
    return;
  }
  // weekly candles
  var n=d.c.length, hasV=d.v&&d.v.length===n;
  var volH=hasV?Math.round((H-padT-AX)*0.22):0;
  var pTop=padT, pBot=H-AX-volH-(hasV?6:0), vTop=pBot+6, vBot=H-AX;
  var lo=Infinity,hi=-Infinity;
  for(var i=0;i<n;i++){lo=Math.min(lo,d.l[i]);hi=Math.max(hi,d.h[i]);if(d.ma[i]!=null){lo=Math.min(lo,d.ma[i]);hi=Math.max(hi,d.ma[i]);}}
  var rng=(hi-lo)||1; lo-=rng*.06; hi+=rng*.06;
  function Y(v){return pTop+(pBot-pTop)*(1-(v-lo)/(hi-lo));}
  bands(n,d.regime,pTop,pBot);
  if(hasV){var vm=0;for(var i=0;i<n;i++)vm=Math.max(vm,d.v[i]);vm=vm||1;
    for(var i=0;i<n;i++){var up=d.c[i]>=d.o[i];ctx.fillStyle=up?'rgba(110,200,140,.45)':'rgba(220,110,120,.45)';var bh=volH*(d.v[i]/vm),bw=Math.max(1,(W-pad-padR)/n*0.6);ctx.fillRect(X(i,n)-bw/2,vBot-bh,bw,bh);} }
  ctx.strokeStyle='#2a2f3a';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(pad,pBot);ctx.lineTo(W-padR,pBot);ctx.stroke();
  ctx.fillStyle='#7a818c';ctx.font='10px sans-serif';ctx.textAlign='right';
  [lo,(lo+hi)/2,hi].forEach(function(v){ctx.fillText(Math.round(v).toLocaleString(),pad-6,Y(v)+3);});
  ctx.textAlign='center';var step=Math.max(1,Math.floor(n/7));
  for(var i=0;i<n;i+=step){ctx.fillText(d.dates[i].slice(0,7),X(i,n),H-7);}
  ctx.strokeStyle='#6b9bd1';ctx.lineWidth=1.6;ctx.beginPath();var st2=false;
  for(var i=0;i<n;i++){if(d.ma[i]==null)continue;var x=X(i,n),y=Y(d.ma[i]);if(!st2){ctx.moveTo(x,y);st2=true;}else ctx.lineTo(x,y);}ctx.stroke();
  var cw=Math.max(1.5,(W-pad-padR)/n*0.62);
  for(var i=0;i<n;i++){var up=d.c[i]>=d.o[i],col=up?'#3fb37a':'#e2606a';ctx.strokeStyle=col;ctx.fillStyle=col;
    ctx.beginPath();ctx.moveTo(X(i,n),Y(d.h[i]));ctx.lineTo(X(i,n),Y(d.l[i]));ctx.stroke();
    var yo=Y(d.o[i]),yc=Y(d.c[i]),tp=Math.min(yo,yc),bh=Math.max(1,Math.abs(yc-yo));ctx.fillRect(X(i,n)-cw/2,tp,cw,bh);}
  ctx.fillStyle='#ffd479';
  d.entries.forEach(function(i){var x=X(i,n),y=Y(d.l[i])+7;ctx.beginPath();ctx.moveTo(x,y+11);ctx.lineTo(x-5,y+20);ctx.lineTo(x+5,y+20);ctx.closePath();ctx.fill();});
  if(d.plan){var pl=d.plan;
    function hline(v,col,lbl){if(v==null)return;var y=Math.max(pTop,Math.min(pBot,Y(v)));ctx.strokeStyle=col;ctx.setLineDash([5,4]);ctx.lineWidth=1.2;ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(W-padR,y);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=col;ctx.textAlign='left';ctx.font='10px sans-serif';ctx.fillText(lbl,pad+3,y-3);}
    hline(pl.pivot,'#46c0e0','\uB9E4\uC218 '+(pl.pivot!=null?Math.round(pl.pivot).toLocaleString():''));
    hline(pl.stop,'#e2606a','\uC190\uC808 '+(pl.stop!=null?Math.round(pl.stop).toLocaleString():''));
    var bg=({BREAKOUT:'#1c5b3a',BREAKOUT_LOWVOL:'#5a4a1c',NEAR:'#3a3050',SETUP:'#2a2f3a',WATCH:'#22262f'})[pl.state]||'#22262f';
    ctx.fillStyle=bg;ctx.fillRect(pad,pTop,150,18);ctx.fillStyle='#e8eaed';ctx.textAlign='left';ctx.font='11px sans-serif';
    ctx.fillText(pl.state_ko+' '+pl.regime_label,pad+5,pTop+13);
  }
  document.getElementById('charttitle').innerHTML=_title(d,code,'주봉 · 40주선(MA200)'+(hasV?' · 거래량':''));
}
window.addEventListener('load',function(){var f=document.querySelector('.mrow'); if(f) showChart(f.getAttribute('data-code'));});
"""


def write_handoff(mdf, chart_data, asof):
    """진입 트리거(돌파/임박) → 워치리스트 핸드오프 후보 파일. active 정본은 안 건드림.
    무효화 트리거 먼저·thesis는 진우 기입(발굴→재량 경계). 매수신호 아님."""
    datestr = asof.strftime("%Y-%m-%d")
    acts = []
    for _, r in mdf.iterrows():
        pl = (chart_data.get(r["code"]) or {}).get("plan")
        if pl and pl["state"] in ("BREAKOUT", "BREAKOUT_LOWVOL", "NEAR"):
            acts.append((r, pl))
    acts.sort(key=lambda x: {"BREAKOUT": 0, "BREAKOUT_LOWVOL": 1, "NEAR": 2}.get(x[1]["state"], 9))
    md = []
    md.append(f"# 진입 → 워치리스트 핸드오프 후보 — {datestr}")
    md.append("")
    md.append("> 진입 상태머신이 **돌파/임박**으로 띄운 후보. **매수신호 아님.** "
              "active 워치리스트(`진우퀀트_KOSDAQ_워치리스트_active.md`)는 시스템이 절대 안 건드림.")
    md.append("> 절차: ①forward 카탈리스트 확인된 것만 ②**무효화 트리거 먼저** 적고 ③active .md로 옮긴 뒤 ④매수(cap≤10%) ⑤월말 Track W.")
    md.append("")
    if not acts:
        md.append("**현재 돌파/임박 후보 없음.** (주도주 눌림·셋업 미충족 또는 regime 보류) — 신규 진입 보류 구간.")
    else:
        md.append("| 상태 | 종목(코드) | 테마 | 매수(pivot) | 손절 | R | regime | 카탈리스트 [진우 기입] | 무효화 트리거 [먼저!] | 비중 cap |")
        md.append("|---|---|---|---:|---:|---:|---|---|---|---|")
        for r, pl in acts:
            piv = f"{pl['pivot']:,.0f}" if pl.get("pivot") is not None else "—"
            stp = f"{pl['stop']:,.0f}" if pl.get("stop") is not None else "—"
            rr = "—" if pl.get("R") is None else f"{pl['R']}"
            md.append(f"| {pl['state_ko']} {pl['regime_label']} | {r['name']}({r['code']}) | {r['theme']} | "
                      f"{piv} | {stp} | {rr} | {pl['regime']} | _촉매: ____ (가드레일=고려가능, 매수신호 아님)_ | "
                      f"_thesis붕괴/촉매 부정/실적 미스/거래량 소멸 中 + 구체화_ | ≤10% |")
    md.append("")
    md.append("원칙: 카탈리스트 없으면 추가 금지 · 선반영은 '카탈리스트가 남았나'로만 정당화 · 판단·책임은 진우, 시스템은 가드레일·측정만.")
    path = os.path.join(HERE, "진입_워치리스트_핸드오프_후보.md")
    open(path, "w", encoding="utf-8").write("\n".join(md))
    return path, len(acts)


def write_outputs(df, mdf, panel, asof, top_themes=8, warns=None, chart_data=None):
    df.to_csv(os.path.join(HERE, "theme_heat_latest.csv"), index=False, encoding="utf-8-sig")
    mdf.to_csv(os.path.join(HERE, "theme_heat_members_latest.csv"), index=False, encoding="utf-8-sig")
    datestr = asof.strftime("%Y-%m-%d")
    partial = (pd.Period(asof, "M") == pd.Period(pd.Timestamp.today(), "M"))
    snap = " (월중 스냅샷)" if partial else ""
    warns = warns or []

    md = []
    md.append(f"# 🔥 뜨거운 테마 브리핑 — {datestr}")
    md.append("")
    md.append(f"> 전 시장 포괄 백본(KOSPI+KOSDAQ {panel.shape[1]}종, {len(df)}개 테마그룹) · 기준 {asof.strftime('%Y-%m')}{snap}.")
    md.append("> **발굴 층 surfacing — 매수신호 아님.** thesis·무효화·사이징은 재량(워치리스트), 측정은 Track W.")
    md.append("")
    if warns:
        ws = ", ".join(f"{m}({v*100:+.0f}%)" for m, v in warns)
        md.append(f"> ⚠️ **극단 레짐 경고**: 최근 활성창에 시장 EW 월수익 |x|>15% 인 달 존재 — {ws}. 절대 모멘텀 과신 금지(레짐 효과 큼).")
        md.append("")
    md.append("## TOP 테마 (heat_score 순)")
    md.append("")
    md.append("| # | 테마 | heat | 3m초과 | 6m초과 | 1m초과 | 3m breadth | 수퍼사이클 | 가속 |")
    md.append("|---|------|-----:|-------:|-------:|-------:|-----------:|:---------:|:----:|")
    for _, r in df.head(top_themes).iterrows():
        md.append(f"| {int(r['rank'])} | {r['theme']} | {r['heat_score']:.0f} | "
                  f"{_pct(r['exc_3m'])} | {_pct(r['exc_6m'])} | {_pct(r['exc_1m'])} | "
                  f"{_pct(r['breadth_3m'],0)} | {'🟢' if r['supercycle'] else '·'} | {'⚡' if r['accel'] else '·'} |")
    md.append("")
    md.append("`초과` = 테마 EW 누적수익 − 시장 EW 누적수익. `수퍼사이클` = 12M초과≥30%·breadth≥60%·3개월지속. `가속` = 최근1m이 3m평균 페이스 추월.")
    md.append("")
    md.append("## 상위 테마 · 종목 surfacing (3m 수익 상위)")
    md.append("")
    md.append("| 테마 | 종목 | 1m | 3m | 6m | 12m | 매출YoY | 영업이익률 | ROE | FY |")
    md.append("|------|------|---:|---:|---:|----:|--------:|-----------:|----:|:--:|")
    for _, r in mdf.iterrows():
        nm = f"{r['name']} ({r['code']})"
        md.append(f"| {r['theme']} | {nm} | {_pct(r['ret_1m'])} | {_pct(r['ret_3m'])} | "
                  f"{_pct(r['ret_6m'])} | {_pct(r['ret_12m'])} | {_pct(r['rev_yoy'])} | "
                  f"{_pct(r['op_margin'])} | {_pct(r['roe'])} | {'' if pd.isna(r['fy']) else int(r['fy'])} |")
    md.append("")
    md.append("재무 = 최신 FY(재계산 검증). 모멘텀·재무는 **확인용 컨텍스트**일 뿐 매수근거 아님. 차트(HTML)에서 종목 클릭 시 월봉+regime밴드+추세선+진입 확인.")
    md.append("")
    md.append("---")
    md.append("**차트 연동:** HTML 패널에서 종목 행 클릭 → 월봉·regime(v40 MA200)·12개월 추세선·진입▲. 거래량/일봉MA200은 일봉 연동 시 추가. 발굴→워치리스트→Track W 경계 고정.")
    mdpath = os.path.join(HERE, f"뜨거운테마_브리핑_{datestr}.md")
    open(mdpath, "w", encoding="utf-8").write("\n".join(md))

    htmlpath = os.path.join(HERE, f"뜨거운테마_패널_{datestr}.html")
    open(htmlpath, "w", encoding="utf-8").write(
        _render_panel(df, mdf, asof, panel, top_themes, partial, warns, chart_data or {}))
    return mdpath, htmlpath


def _render_panel(df, mdf, asof, panel, top_themes, partial=False, warns=None, chart_data=None):
    datestr = asof.strftime("%Y-%m-%d")
    snap = " (월중 스냅샷)" if partial else ""
    warns = warns or []
    chart_data = chart_data or {}
    acts = []
    for _, r in mdf.iterrows():
        pl = (chart_data.get(r["code"]) or {}).get("plan")
        if pl and pl["state"] in ("BREAKOUT", "BREAKOUT_LOWVOL", "NEAR"):
            acts.append((r, pl))
    acts.sort(key=lambda x: {"BREAKOUT": 0, "BREAKOUT_LOWVOL": 1, "NEAR": 2}.get(x[1]["state"], 9))
    if acts:
        _items = []
        for r, pl in acts:
            rtxt = "R n/a" if pl["R"] is None else f"R {pl['R']}"
            ecls = "e-bo" if pl["state"].startswith("BREAKOUT") else "e-near"
            _items.append(
                f'<div class="ecard {ecls}"><div class="eh"><b>{r["name"]}</b> '
                f'<span class="code">{r["code"]}</span> <span class="etag">{pl["state_ko"]}</span> '
                f'<span class="rgm">{pl["regime_label"]}</span></div>'
                f'<div class="erow">매수 <b>{pl["pivot"]:,.0f}</b> · 손절 <b>{pl["stop"]:,.0f}</b> · {rtxt} · pivot까지 {pl["to_pivot_pct"]}%</div>'
                f'<div class="esub">{r["theme"]}</div></div>')
        entrycard_html = '<h2>🎯 진입 카드 — 돌파/임박 (재량 검토용 · 매수신호 아님)</h2><div class="egrid">' + "".join(_items) + '</div>'
    else:
        entrycard_html = '<h2>🎯 진입 카드</h2><div class="enote">현재 돌파/임박(트리거) 종목 없음. 표의 진입 컬럼에서 셋업/관망 상태 확인.</div>'
    vmax = df["heat_score"].max()

    def heatcolor(v):
        t = 0 if vmax == 0 else max(0.0, min(1.0, v / vmax))
        r = int(60 + t * 195); g = int(60 + (1 - t) * 90); b = int(70 - t * 40)
        return f"rgb({r},{g},{b})"

    cards = []
    for _, r in df.head(top_themes).iterrows():
        tags = []
        if r["supercycle"]:
            tags.append('<span class="tag sc">🟢 수퍼사이클</span>')
        if r["accel"]:
            tags.append('<span class="tag ac">⚡ 가속</span>')
        cards.append(f"""
        <div class="card" style="border-left:6px solid {heatcolor(r['heat_score'])}">
          <div class="chead"><span class="rk">{int(r['rank'])}</span><span class="th">{r['theme']}</span>
            <span class="heat">{r['heat_score']:.0f}</span></div>
          <div class="bars">
            <div class="brow"><span>3m초과</span><b>{_pct(r['exc_3m'])}</b></div>
            <div class="brow"><span>6m초과</span><b>{_pct(r['exc_6m'])}</b></div>
            <div class="brow"><span>3m breadth</span><b>{_pct(r['breadth_3m'],0)}</b></div>
          </div>
          <div class="tags">{''.join(tags) or '<span class="tag muted">·</span>'}</div>
        </div>""")

    def _statecell(code):
        pl = (chart_data.get(code) or {}).get("plan")
        if not pl:
            return '<span class="muted">—</span>'
        cls = {"BREAKOUT": "st-bo", "BREAKOUT_LOWVOL": "st-lv", "NEAR": "st-near",
               "SETUP": "st-set", "WATCH": "st-watch"}.get(pl["state"], "")
        return f'<span class="stbadge {cls}">{pl["state_ko"]}</span> <span class="rgm">{pl["regime_label"]}</span>'

    mrows = []
    for _, r in mdf.iterrows():
        clickable = r["code"] in chart_data
        attrs = (f'class="mrow" data-code="{r["code"]}" onclick="showChart(\'{r["code"]}\')" style="cursor:pointer"'
                 if clickable else 'class="mrow off"')
        mrows.append(f"""<tr {attrs}><td>{r['theme']}</td><td><b>{r['name']}</b> <span class="code">{r['code']}</span></td>
          <td>{_statecell(r['code'])}</td>
          <td class="num">{_pct(r['ret_1m'])}</td><td class="num">{_pct(r['ret_3m'])}</td>
          <td class="num">{_pct(r['ret_6m'])}</td><td class="num">{_pct(r['ret_12m'])}</td>
          <td class="num fin">{_pct(r['rev_yoy'])}</td><td class="num fin">{_pct(r['op_margin'])}</td>
          <td class="num fin">{_pct(r['roe'])}</td></tr>""")

    warnhtml = ""
    if warns:
        ws = ", ".join(f"{m}({v*100:+.0f}%)" for m, v in warns)
        warnhtml = f'<div class="warn">⚠️ 극단 레짐: 활성창에 시장 EW 월 |x|&gt;15% — {ws}. 절대 모멘텀 과신 금지.</div>'

    chart_css = (
        ".mrow:hover{background:#1d2129}.mrow.sel{background:#231a12;box-shadow:inset 3px 0 0 var(--acc)}"
        ".mrow.off{opacity:.55}.muted{color:#9aa0aa}"
        "#chartcard{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-top:8px}"
        "#charttitle{font-size:14px;margin-bottom:8px}"
        "#cv{width:100%;height:auto;background:#11141a;border-radius:8px;display:block}"
        ".clegend{display:flex;gap:14px;flex-wrap:wrap;margin-top:10px;font-size:11.5px;color:var(--mut);align-items:center}"
        ".clegend i{display:inline-block;width:14px;height:10px;margin-right:5px;vertical-align:middle;border-radius:2px}"
        ".lg.up{background:#3fb37a}.lg.dn{background:#e2606a}.lg.sma{background:#6b9bd1}.lg.ent{background:#ffd479}.lg.vol{background:rgba(110,200,140,.55)}.lg.line{background:#ff7a45}"
        ".lg.on{background:rgba(46,125,80,.6)}.lg.neu{background:rgba(160,135,40,.6)}.lg.off{background:rgba(160,55,60,.6)}"
        ".cnote{margin-top:9px;color:#5a6068;font-size:11px;line-height:1.5}"
        ".lg.buy{background:#46c0e0}.lg.stp{background:#e2606a}"
        ".stbadge{font-size:11px;border-radius:5px;padding:1px 6px}.st-bo{background:#1c5b3a;color:#aef0c8}.st-lv{background:#5a4a1c;color:#ffe3a3}.st-near{background:#3a3050;color:#cdb9ff}.st-set{background:#2a2f3a;color:#bcd}.st-watch{background:#22262f;color:#7a818c}.rgm{font-size:11px}"
        ".egrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px;margin-bottom:18px}"
        ".ecard{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}.ecard.e-bo{border-left:4px solid #3fb37a}.ecard.e-near{border-left:4px solid #8a78d0}"
        ".eh{font-size:13px;margin-bottom:5px}.etag{font-size:11px;background:#22262f;border-radius:5px;padding:1px 6px;color:#cde}.erow{font-size:12px;color:#cdd3da}.erow b{color:#fff}.esub{font-size:11px;color:#7a818c;margin-top:3px}.enote{color:#7a818c;font-size:12.5px;margin-bottom:16px}"
    )

    chart_section = (
        '<h2>📈 종목 차트 — 위 표에서 종목을 클릭 (주봉)</h2>'
        '<div id="chartcard">'
        '<div id="charttitle">위 표의 종목을 클릭하면 차트가 표시됩니다</div>'
        '<canvas id="cv" width="940" height="360"></canvas>'
        '<div class="clegend">'
        '<span><i class="lg up"></i>양봉</span><span><i class="lg dn"></i>음봉</span>'
        '<span><i class="lg sma"></i>40주선(MA200)</span>'
        '<span><i class="lg ent"></i>▲ 진입(SEPA-lite: 40주선 상회+상승전환)</span>'
        '<span><i class="lg vol"></i>거래량</span>'
        '<span><i class="lg buy"></i>매수선(pivot)</span><span><i class="lg stp"></i>손절선</span>'
        '<span><i class="lg on"></i>RISK_ON</span><span><i class="lg neu"></i>NEUTRAL</span><span><i class="lg off"></i>RISK_OFF</span>'
        '</div>'
        '<div class="cnote">주봉 = kospi/kosdaq 일봉→W-FRI 리샘플(정합 게이트 PASS: 월말종가 99.8%/수익환원·주봉무결성 100%). 40주선 = 일봉 200일선 등가. KOSDAQ 일부·신규상장은 거래량/주봉 미보유 시 월봉 라인 fallback. regime 밴드=v40 시장레짐. 차트는 발굴 보조 — 매수신호 아님.</div>'
        '</div>'
    )

    chart_script = "<script>\nvar CHART = " + json.dumps(chart_data, ensure_ascii=False) + ";\n" + _CHART_JS + "</script>"

    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🔥 뜨거운 테마 — {datestr}</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--ink:#e8eaed;--mut:#9aa0aa;--line:#262a33;--acc:#ff7a45}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI',Roboto,'Malgun Gothic',sans-serif;padding:18px}}
h1{{font-size:20px;margin:0 0 4px}} .sub{{color:var(--mut);font-size:12.5px;margin-bottom:14px;line-height:1.5}}
.guard{{background:#2a1d12;border:1px solid #5a3a1f;color:#ffc6a3;padding:8px 12px;border-radius:8px;font-size:12.5px;margin-bottom:12px}}
.warn{{background:#2c1416;border:1px solid #5e2a2e;color:#ffb3b8;padding:8px 12px;border-radius:8px;font-size:12.5px;margin-bottom:16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:12px;margin-bottom:24px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}}
.chead{{display:flex;align-items:center;gap:8px;margin-bottom:10px}}
.rk{{font-size:11px;color:var(--mut);background:#22262f;border-radius:6px;padding:2px 7px}}
.th{{font-weight:700;font-size:15px;flex:1}} .heat{{font-size:22px;font-weight:800;color:var(--acc)}}
.brow{{display:flex;justify-content:space-between;font-size:12.5px;color:var(--mut);padding:2px 0}}
.brow b{{color:var(--ink)}}
.tags{{margin-top:10px;display:flex;gap:6px;flex-wrap:wrap}}
.tag{{font-size:11px;border-radius:6px;padding:2px 8px}} .tag.sc{{background:#143b2a;color:#7ee0ad}}
.tag.ac{{background:#3b2e14;color:#ffd479}} .tag.muted{{color:#444}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}
th,td{{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left}}
th{{color:var(--mut);font-weight:600;font-size:11.5px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}} .code{{color:var(--mut);font-family:monospace;font-size:11px}}
.fin{{color:#9fc4e8}}
h2{{font-size:14px;color:var(--mut);margin:22px 0 8px;font-weight:600}}
.foot{{margin-top:18px;color:#5a6068;font-size:11.5px;line-height:1.6}}
{chart_css}
</style></head><body>
<h1>🔥 뜨거운 테마</h1>
<div class="sub">전 시장 포괄 백본 · KOSPI+KOSDAQ {panel.shape[1]}종 · {len(df)}개 테마그룹 · 기준 {asof.strftime('%Y-%m')}{snap}</div>
<div class="guard">⚠️ 발굴 층 <b>surfacing</b> — 매수신호 아님. 살지는 재량(워치리스트), 밥값은 Track W. 모멘텀·재무·차트는 확인용 컨텍스트.</div>
{warnhtml}
<div class="grid">{''.join(cards)}</div>
{entrycard_html}
<h2>상위 테마 · 종목 surfacing (3m 수익 상위 · 재무는 파란색 · 클릭 시 차트)</h2>
<table><thead><tr><th>테마</th><th>종목</th><th>진입</th><th class="num">1m</th><th class="num">3m</th>
<th class="num">6m</th><th class="num">12m</th><th class="num">매출YoY</th><th class="num">영업이익률</th><th class="num">ROE</th></tr></thead>
<tbody>{''.join(mrows)}</tbody></table>
{chart_section}
<div class="foot">heat = 100·(0.45·pct(3m초과)+0.25·pct(6m초과)+0.15·pct(1m초과)+0.15·pct(3m breadth)). 수퍼사이클=12M·3개월지속 확립 태그. 재무=최신 FY 재계산. 차트=월봉+regime(v40 MA200)+12개월 추세선+진입. 정직 가드: 백테스트 불가 영역=Track W 사후 측정만.</div>
{chart_script}
</body></html>"""


def _selftest():
    E, TC = _engines(); ok = 0
    rng = np.random.default_rng(7); Tm = 40
    idx = pd.date_range("2022-01-31", periods=Tm, freq="ME")
    hot = [f"H{i:05d}" for i in range(8)]; cold = [f"C{i:05d}" for i in range(8)]
    cols = hot + cold
    px = pd.DataFrame(1000.0, index=idx, columns=cols)
    for t in range(1, Tm):
        for c in cols:
            mu = 0.10 if (c in hot and t >= Tm - 8) else 0.004
            px.loc[idx[t], c] = px.loc[idx[t - 1], c] * (1 + rng.normal(mu, 0.02))
    fine = {c: ("반도체 제조업" if c in hot else "기타 금융업") for c in cols}
    name = {c: c for c in cols}
    df, cm, mem = compute_theme_heat(px, fine, name, E, TC, min_members=5)
    assert not df.empty
    hrow = df[df["theme"] == "반도체/전자"]; crow = df[df["theme"] == "금융"]
    assert len(hrow) and len(crow)
    assert hrow["heat_score"].iloc[0] > crow["heat_score"].iloc[0]; ok += 1
    assert hrow["exc_3m"].iloc[0] > 0; ok += 1
    ret = px.pct_change()
    assert abs(ret[hot].iloc[-1].mean() - cum_ret(ret, hot, len(px) - 1, 1)) < 1e-12; ok += 1
    g = pd.DataFrame({"revenue": [100.0, 130.0], "op_income": [13.0, 26.0],
                      "net_income": [10.0, 20.0], "equity": [100.0, 100.0]})
    assert abs((g.iloc[-1]["revenue"] / g.iloc[-2]["revenue"] - 1) - 0.30) < 1e-9
    assert abs((g.iloc[-1]["op_income"] / g.iloc[-1]["revenue"]) - 0.20) < 1e-9
    assert abs((g.iloc[-1]["net_income"] / g.iloc[-1]["equity"]) - 0.20) < 1e-9; ok += 1
    md = surface_members(px, mem, df["theme"].tolist(), {}, {}, len(px) - 1, names={c: "테스트종목" for c in hot})
    assert "name" in md.columns and (md["name"] == "테스트종목").any(); ok += 1
    # 차트 데이터: 시계열·진입·regime 정합
    reg = {d.strftime("%Y-%m"): "RISK_ON" for d in idx}
    cd = build_chart_data(px, md, reg)
    any_code = md["code"].iloc[0]
    assert any_code in cd
    cdi = cd[any_code]
    assert len(cdi["close"]) == len(cdi["dates"]) == len(cdi["sma"]) == len(cdi["regime"])
    assert all(isinstance(e, int) for e in cdi["entries"])
    assert cdi["regime"][-1] == "RISK_ON"
    # JSON 직렬화 가능
    json.dumps(cd, ensure_ascii=False); ok += 1
    # 7) 주봉 경로: 합성 일봉 → 캔들 OHLC+40주MA+거래량
    bd = pd.bdate_range("2022-01-03", periods=400)
    dpx = 1000 * np.cumprod(1 + np.random.default_rng(1).normal(0.001, 0.012, len(bd)))
    g = pd.DataFrame({"open": dpx, "high": dpx*1.01, "low": dpx*0.99, "close": dpx,
                      "volume": np.random.default_rng(2).integers(1e5, 1e6, len(bd))}, index=bd)
    daily = {any_code: g}
    mdf2 = md[md["code"] == any_code].copy()
    cw = build_chart_data(px, mdf2, reg, daily=daily)
    w = cw[any_code]
    assert w["type"] == "weekly", "주봉 경로 미작동"
    assert len(w["c"]) == len(w["o"]) == len(w["h"]) == len(w["l"]) == len(w["dates"]) == len(w["ma"])
    assert len(w["v"]) == len(w["c"]) and all(x >= 0 for x in w["v"]), "거래량 누락"
    assert all(w["h"][k] >= w["l"][k] for k in range(len(w["c"]))), "고가<저가 모순"
    json.dumps(cw, ensure_ascii=False); ok += 1
    print(f"✅ 셀프테스트 통과 ({ok}/7): heat랭킹·3m초과부호·모멘텀재계산·재무산식·종목명·월봉차트·주봉캔들")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--min-members", type=int, default=5)
    args = ap.parse_args()
    if args.selftest:
        _selftest(); return
    E, TC = _engines()
    panel = load_panel(); fine, name = TC.load_fine_map()
    i = len(panel) - 1; asof = panel.index[i]
    df, cm, members_in = compute_theme_heat(panel, fine, name, E, TC, min_members=args.min_members, i=i)
    if df.empty:
        print("⚠️ 테마 결과 없음"); return
    fin = load_financials(); size = load_size(); regime = load_regime()
    mdf = surface_members(panel, members_in, df["theme"].tolist(), fin, size, i, names=name, top_themes=args.top, per=6)
    daily = load_daily_for(mdf["code"].tolist())
    ES = _load_src("entry_signals.py", "entry_signals")
    _mret = panel.pct_change().mean(axis=1)
    mkt26 = float((1 + _mret.iloc[-6:]).prod() - 1)
    regime_state = regime.get(asof.strftime("%Y-%m")) or (regime.get(max(regime)) if regime else "")
    chart_data = build_chart_data(panel, mdf, regime, daily=daily, ES=ES, mkt26=mkt26, regime_state=regime_state)
    warns = regime_warn(panel, i, lookback=6)
    mdpath, htmlpath = write_outputs(df, mdf, panel, asof, top_themes=args.top, warns=warns, chart_data=chart_data)
    hopath, nact = write_handoff(mdf, chart_data, asof)
    nw = sum(1 for v in chart_data.values() if v.get("type")=="weekly")
    nbo = sum(1 for v in chart_data.values() if (v.get("plan") or {}).get("state","").startswith("BREAKOUT"))
    nnear = sum(1 for v in chart_data.values() if (v.get("plan") or {}).get("state")=="NEAR")
    print(f"  진입: 돌파 {nbo} · 임박 {nnear} · regime {regime_state}"); print(f"기준시점 {asof.strftime('%Y-%m-%d')} · 패널 {panel.shape[1]}종 · {len(df)}개 테마 · 차트 {len(chart_data)}종(주봉 {nw}/월봉 {len(chart_data)-nw})")
    if warns:
        print("⚠️ 극단 레짐:", ", ".join(f"{m}({v*100:+.0f}%)" for m, v in warns))
    show = df.head(args.top)[["rank", "theme", "heat_score", "exc_3m", "exc_6m", "breadth_3m", "supercycle", "accel"]].copy()
    for c in ("exc_3m", "exc_6m"):
        show[c] = (show[c] * 100).round(1)
    show["breadth_3m"] = (show["breadth_3m"] * 100).round(0)
    show["heat_score"] = show["heat_score"].round(0)
    print("\nTOP 뜨거운 테마:"); print(show.to_string(index=False))
    print(f"\n산출: theme_heat_latest.csv · theme_heat_members_latest.csv · {os.path.basename(mdpath)} · {os.path.basename(htmlpath)}")
    print(f"      핸드오프 후보: {os.path.basename(hopath)} (돌파/임박 {nact}건)")


if __name__ == "__main__":
    main()
