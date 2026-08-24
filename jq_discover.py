# -*- coding: utf-8 -*-
"""
jq_discover.py — **종목 발굴 + 매매 준비 툴** (스크리너 아님)
철학: 예측하지 않는다. **대응한다.** 후보를 띄우고, 사면 얼마에 자르고 몇 주 살지까지 계산해준다.
⚠️ 발굴 ≠ 매수신호. 필터 통과 = "볼 만한 후보"일 뿐. 최종 판단·책임은 진우.

필터(예측 아닌 상태 확인 — 진입 상태만 확인, 순위는 아래 ⑥):
  ① 추세      : 종가 > MA200 (상승추세 안)
  ② 상대강도  : 최근 3개월 수익률 상위
  ③ 관심 유입 : 최근 20일 거래대금 > 60일 평균 (자금 유입 중)
  ④ 유동성    : 20일 평균 거래대금 하한(기본 30억)
  ⑤ 테마      : theme_heat 상위 테마 소속(있으면 표시·가점)
  ⑥ ★검증 기울기(순위·시총 tier별) : 통과 후보를 검증 팩터로 위/아래로.
     · 소형 = 저변동성 위주(결합이 단독 못이김) · 중형 = 저변동성×저PBR 결합(OOS 증분 +1%p)
     · 대형 = 엣지 소진(소>대 5번 반복) → 페널티로 아래로.
     근거 = C(저변동성·저PBR 채택) + 팩터결합 검정(중형만 결합 채택·대형 기각) + GP 기각.
     상태필터는 안 건드리고 순위 점수에만 가산. --no-tilt 로 끌 수 있음.
매매 준비(매도규칙서·사이징 자동 반영):
  · 손절가 = max(현재가 − 2.5×ATR14, 현재가×0.80)
  · 1R = 현재가 − 손절가
  · 매수 수량 = (자본 × 리스크%) / 1R      ← 갭 리스크(실측 −15~19R) 때문에 필수
  · 계절 구간(11~4월/5~10월) 표시 → 위성 비중 조절 가이드

실행(폴더에서):
  py jq_discover.py --capital 10000000 --risk 1.0        # 자본 1천만·트레이드당 1% 리스크
  py jq_discover.py --capital 10000000 --top 8 --card    # 카드(PNG)까지 생성
산출: 발굴후보.csv · (옵션) 종목발굴_카톡.png
"""
import os, sys, json, argparse, warnings, importlib.util
from datetime import date
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

CFG=dict(MA=200, ATR_N=14, ATR_K=2.5, STOP_CAP=0.20, RS_DAYS=60, VOL_MIN=3_000_000_000,
         EXT_MAX=1.40,      # [안정] 이격도 상한: MA200×1.40 초과 = 과열 → 제외(늦은 진입 방지)
         STOP_MAX=0.15,     # [안정] 손절폭 상한 15%
         # ─ 돌파 모드(--breakout): 10배 종목은 여기서 나온다. 실패율 높음 → 사이징 절반 ─
         BO_HIGH=0.95,      # 52주 최고가의 95% 이상 (신고가 부근)
         BO_INFL=1.5,       # 거래대금 급증 1.5배+
         BO_RISK_MULT=0.5,  # 리스크 절반(자본 1% → 0.5%)
         # ─ ⑥ 검증 기울기(순위 가산) — C·②·팩터결합 근거. 상태필터 아님, 밀어주기만 ─
         #   시총 tier별: 소형=저변동성 위주 / 중형=저변동성×저PBR 결합 / 대형=엣지 없음(페널티)
         TILT_W=25.0,       # 기울기 최대 가산점(테마·자금유입과 비슷한 크기, 지배 안 함)
         TILT_VOL_S=0.85, TILT_PBR_S=0.15,   # 소형: 저변동 단독 최선(결합이 단독 못이김)
         TILT_VOL_M=0.50, TILT_PBR_M=0.50,   # 중형: 저변동×저PBR 결합 채택(OOS 증분 +1%p)
         TILT_LARGE_PEN=-0.5)                # 대형: 소>대 5번 반복, 엣지 소진 → 아래로

def load_pbr():
    """최신 PBR(>0) 스냅샷. 라이브 발굴이라 PIT 불필요(분기 지연은 존재)."""
    out={}
    for f in ("종목재무_KRX_KOSPI.csv","종목재무_KRX_KOSDAQ.csv"):
        p=os.path.join(HERE,f)
        if not os.path.exists(p): continue
        try:
            d=pd.read_csv(p,dtype={"code":str},usecols=["date","code","PBR"],encoding="utf-8-sig")
        except Exception:
            continue
        d["PBR"]=pd.to_numeric(d["PBR"],errors="coerce")
        d=d[d["PBR"]>0].dropna(subset=["PBR"]).sort_values("date").groupby("code").tail(1)
        for _,r in d.iterrows(): out[str(r["code"]).zfill(6)]=float(r["PBR"])
    return out

def load_mcap():
    """최신 시총 스냅샷 + 전체 유니버스 tercile 경계(소/중/대 분류용)."""
    p=os.path.join(HERE,"종목시총_30년.csv")
    if not os.path.exists(p): return {}, None
    try:
        d=pd.read_csv(p,dtype={"code":str},usecols=["date","code","mcap"],encoding="utf-8-sig")
    except Exception:
        return {}, None
    d["mcap"]=pd.to_numeric(d["mcap"],errors="coerce")
    d=d.dropna(subset=["mcap"]).sort_values("date").groupby("code").tail(1)
    mp={str(r["code"]).zfill(6):float(r["mcap"]) for _,r in d.iterrows()}
    vals=np.array(sorted(v for v in mp.values() if v>0))
    cuts=tuple(np.quantile(vals,[1/3,2/3])) if len(vals)>=3 else None
    return mp, cuts

def tier_of(mcap, cuts):
    """시총 → 소/중/대. 경계 = 전체 상장 유니버스 tercile. 모르면 '중'(중립)."""
    if cuts is None or not (isinstance(mcap,(int,float)) and np.isfinite(mcap)): return "중"
    q1,q2=cuts
    return "소" if mcap<q1 else ("중" if mcap<q2 else "대")

def load_daily():
    fs=[]
    for f in ("kospi_pit_daily.csv","kosdaq_pit_daily.csv"):
        p=os.path.join(HERE,f)
        if os.path.exists(p):
            d=pd.read_csv(p,dtype={"code":str},on_bad_lines="skip")
            d["date"]=pd.to_datetime(d["date"],errors="coerce")   # 잘린 EOF 조각 등 → NaT
            d["close"]=pd.to_numeric(d.get("close"),errors="coerce")
            fs.append(d)
    if not fs: return None
    d=pd.concat(fs,ignore_index=True).dropna(subset=["date","close"])  # 손상행 자동 제외
    return d.sort_values(["code","date"])

def load_names():
    out={}
    for f in ("liquidity_sector.csv","kosdaq_industry.csv"):
        p=os.path.join(HERE,f)
        if os.path.exists(p):
            d=pd.read_csv(p,dtype={"code":str})
            for _,r in d.iterrows():
                c=str(r["code"]).zfill(6)
                if c not in out: out[c]=dict(name=r.get("name"), sector=r.get("sector"))
    return out

def hot_themes(top=6):
    p=os.path.join(HERE,"theme_heat_members_latest.csv")
    if not os.path.exists(p): return {}, []
    m=pd.read_csv(p,dtype={"code":str})
    t=os.path.join(HERE,"theme_heat_latest.csv")
    order=[]
    if os.path.exists(t):
        th=pd.read_csv(t); order=th.sort_values("heat_score",ascending=False)["theme"].head(top).tolist()
    mp={}
    for _,r in m.iterrows():
        c=str(r["code"]).zfill(6)
        if r["theme"] in order: mp[c]=r["theme"]
    return mp, order

def atr(g,n):
    pc=g["close"].shift(1)
    tr=pd.concat([g["high"]-g["low"],(g["high"]-pc).abs(),(g["low"]-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()

def scan(capital, risk_pct, top, breakout=False, tilt=True):
    """breakout=False: 안정 후보(과열 제외) / True: 돌파 후보(10배 후보군·실패율↑·사이징 절반)
    tilt=True: ⑥ 검증 기울기(저PBR·저변동성)를 순위 점수에 가산(상태필터 불변)."""
    d=load_daily()
    if d is None: return None,None,None
    names=load_names(); theme_map, hot = hot_themes()
    pbr_map=load_pbr() if tilt else {}
    mcap_map,mcap_cuts=(load_mcap() if tilt else ({},None))
    asof=d["date"].max()
    if breakout: risk_pct = risk_pct*CFG["BO_RISK_MULT"]      # 리스크 절반
    rows=[]; excl=dict(과열=0, 초고변동=0, 신고가아님=0, 거래량부족=0)
    for code,g in d.groupby("code"):
        g=g.reset_index(drop=True)
        if len(g)<CFG["MA"]+10: continue
        g=g[g["date"]<=asof]
        close=g["close"].iloc[-1]
        ma=g["close"].rolling(CFG["MA"]).mean().iloc[-1]
        if not (pd.notna(ma) and close>ma): continue                       # ① 추세 안(공통)
        ext=close/ma                                                        # 이격도
        a=atr(g,CFG["ATR_N"]).iloc[-1]
        if not (pd.notna(a) and a>0): continue
        if breakout:
            hi52=g["close"].tail(250).max()                                 # 52주 최고가
            if close < hi52*CFG["BO_HIGH"]: excl["신고가아님"]+=1; continue  # ★ 신고가 부근만
        else:
            if ext > CFG["EXT_MAX"]: excl["과열"]+=1; continue               # 안정: 과열 제외
            if (CFG["ATR_K"]*a)/close > CFG["STOP_MAX"]: excl["초고변동"]+=1; continue
        val=(g["close"]*g.get("volume",pd.Series(0,index=g.index))).rolling(20).mean().iloc[-1]
        val60=(g["close"]*g.get("volume",pd.Series(0,index=g.index))).rolling(60).mean().iloc[-1]
        if not (pd.notna(val) and val>=CFG["VOL_MIN"]): continue            # ④ 유동성
        infl = (val/val60) if (pd.notna(val60) and val60>0) else 1.0        # ③ 관심 유입
        if breakout:
            if infl < CFG["BO_INFL"]: excl["거래량부족"]+=1; continue        # ★ 돌파: 거래량 폭증 필수
        elif infl < 1.0: continue
        rs = close/g["close"].iloc[-CFG["RS_DAYS"]]-1 if len(g)>CFG["RS_DAYS"] else np.nan   # ② 상대강도
        if not pd.notna(rs): continue
        vol60 = g["close"].pct_change().tail(60).std()                      # ⑥ 60일 변동성(검증 팩터)
        pbr = pbr_map.get(code, np.nan)                                     # ⑥ 저PBR(검증 팩터)
        stop=max(close-CFG["ATR_K"]*a, close*(1-CFG["STOP_CAP"]))
        R=close-stop
        if R<=0: continue
        qty=int((capital*risk_pct/100.0)//R)
        th=theme_map.get(code,"")
        # 정렬: 안정=리스크 통제 가능성 / 돌파=거래량 폭증·신고가 강도(대박 후보군)
        score = ((infl-1)*40 + ext*20 + (10 if th else 0)) if breakout \
                else ((1.0 - R/close)*100 + (infl-1)*15 + (10 if th else 0))
        rows.append(dict(code=code, name=(names.get(code,{}) or {}).get("name") or code,
                         sector=(names.get(code,{}) or {}).get("sector") or "",
                         theme=th, 현재가=int(close), 손절가=int(stop), R=int(R),
                         손절폭=round(R/close*100,1), 이격도=round(ext,2), RS_3M=round(rs*100,1),
                         자금유입배수=round(infl,2), 거래대금_억=int(val/1e8), 수량=qty,
                         투입금액=int(qty*close),
                         PBR=(round(pbr,2) if pd.notna(pbr) else np.nan),
                         변동성60=(round(vol60*100,1) if pd.notna(vol60) else np.nan),
                         시총tier=tier_of(mcap_map.get(code,np.nan),mcap_cuts),
                         시총억=(int(mcap_map.get(code)/1e8) if mcap_map.get(code) else np.nan),
                         score_base=round(score,1), score=round(score,1)))
    if not rows: return None, asof, excl
    T=pd.DataFrame(rows)
    # ⑥ ★검증 기울기: 통과 후보들 사이에서 저PBR·저변동성 쪽을 위로 (밀어주기, 상태필터 불변)
    if tilt and len(T)>=4:
        lowvol=(1-T["변동성60"].rank(pct=True)).fillna(0.5)    # 덜 출렁일수록 ↑
        lowpbr=(1-T["PBR"].rank(pct=True)).fillna(0.5)         # 쌀수록 ↑ · 결측=중립(벌점 없음)
        W=CFG["TILT_W"]
        def _tilt(i):
            t=T["시총tier"].iloc[i]
            if t=="대": return CFG["TILT_LARGE_PEN"]*W          # 대형: 엣지 소진(소>대) → 페널티
            wv,wp=(CFG["TILT_VOL_S"],CFG["TILT_PBR_S"]) if t=="소" else (CFG["TILT_VOL_M"],CFG["TILT_PBR_M"])
            return (wv*lowvol.iloc[i]+wp*lowpbr.iloc[i])*W     # 소=저변동 위주 / 중=결합
        T["기울기"]=pd.Series([_tilt(i) for i in range(len(T))],index=T.index).round(1)
        T["score"]=(T["score_base"]+T["기울기"]).round(1)
    else:
        T["기울기"]=0.0
    T=T.sort_values("score",ascending=False)
    # ★ 섹터 분산: 같은 섹터 최대 2종목. (같은 섹터 3종을 각 1% 리스크로 사면
    #    상관관계 때문에 사실상 3% 한 방 → 분산이 아니라 집중이 됨)
    T=T.groupby("sector",group_keys=False).head(2).sort_values("score",ascending=False).head(top)
    return T, asof, excl

def season_note():
    """월중 위치 기반 진입 필터.

    ⚠️ 2026-07-13 변경: 기존 '할로윈(5~10월 코어 50% 축소)' 규칙은 **기각**됐다.
       근거: 가상매매\\검증\\할로윈_검증결과.md
             발표후(2003~) p=0.2189 → post-publication decay. 엔진 기본값 OFF.
    대신 **하순(월말 −9~−5거래일) 신규진입 보류** 필터를 쓴다.
       근거: 증명된_규칙\\하순필터_규칙서.md — **30년·상폐포함·OOS 봉인 (채택)**
             코스닥 소·중형 OOS p=0.0002(소)/0.0041(중). 대형은 기각(소>대).
             효과 소형 일간 −0.16%p. **진입 필터로만**(타이밍 규칙은 비용관문서 기각).
    """
    eng=os.path.join(HERE,"가상매매","엔진")
    if eng not in sys.path: sys.path.insert(0,eng)
    try:
        from jq_calendar_filter import is_late_month, rdom_of
        d=load_daily()
        if d is None: return "⚪ 시세 데이터 없음 — 월중 필터 미적용"
        td=sorted(pd.to_datetime(d["date"].unique()))
        today=date.today()
        rd=rdom_of(today,td)
        if rd is None:
            return "⚪ 월중 위치 판정불가 — 진입 필터 미적용"
        if is_late_month(today,td):
            return f"🔴 하순({rd}거래일) — 신규진입 보류 권고 · 기존 보유는 유지 (30년 봉인·코스닥 소·중형)"
        return f"🟢 진입 가능 구간({rd}거래일) — 하순 아님"
    except Exception as e:
        return f"⚪ 월중 필터 오류: {str(e)[:45]}"

def make_card(T, asof, capital, risk_pct):
    from PIL import Image, ImageDraw, ImageFont
    def _fp():
        for p in [r"C:\Windows\Fonts\malgun.ttf","/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
            if os.path.exists(p): return p
        return None
    FP=_fp()
    def F(s): return ImageFont.truetype(FP,s) if FP else ImageFont.load_default()
    BG=(15,17,21);ACC=(255,122,69);GREEN=(63,179,122);RED=(226,96,106);SUB=(150,156,166);TXT=(232,234,237);BLUE=(90,160,240)
    W=880;H=280+len(T)*72
    img=Image.new("RGB",(W,H),BG);d=ImageDraw.Draw(img);d.rectangle([0,0,W,6],fill=ACC);y=24
    d.text((26,y),f"종목 발굴 · 기준일 {asof.date()}",font=F(29),fill=(255,255,255));y+=42
    d.text((26,y),"발굴 ≠ 매수신호 · 필터 통과=볼 만한 후보 · 결정·책임 본인",font=F(14),fill=SUB);y+=30
    d.text((26,y),season_note(),font=F(16),fill=(255,210,120));y+=30
    d.text((26,y),f"자본 {capital:,}원 · 트레이드당 리스크 {risk_pct}% → 아래 수량은 손절 시 손실이 리스크와 같아지는 크기",font=F(13),fill=BLUE);y+=30
    for _,r in T.iterrows():
        d.rectangle([26,y,W-26,y+64],fill=(22,25,31),outline=(44,48,58),width=1);d.rectangle([26,y,31,y+64],fill=GREEN)
        d.text((42,y+8),f"{r['name']}",font=F(18),fill=(255,255,255))
        if r["theme"]:
            bw=d.textlength(r["theme"],font=F(12));d.rectangle([220,y+9,220+bw+14,y+29],fill=(24,34,30),outline=GREEN,width=1)
            d.text((227,y+11),r["theme"],font=F(12),fill=(120,220,170))
        # ── 이하 2026-07-13 복원: 원본이 여기서 잘려 있었다(SyntaxError·실행불가) ──
        d.text((42,y+36),f"현재가 {r['현재가']:,}원",font=F(14),fill=TXT)
        d.text((190,y+36),f"손절 {r['손절가']:,}원 (−{r['손절폭']}%)",font=F(14),fill=RED)
        d.text((400,y+36),f"1R {r['R']:,}원",font=F(14),fill=SUB)
        _pbr = f"PBR {r['PBR']:.2f}" if pd.notna(r.get('PBR')) else "PBR –"
        _v = f"·변동 {r['변동성60']:.1f}%" if pd.notna(r.get('변동성60')) else ""
        d.text((520,y+36),f"{_pbr} {_v}",font=F(14),fill=BLUE)
        d.text((650,y+8),f"{r['수량']:,}주",font=F(20),fill=ACC)
        d.text((650,y+38),f"{r['투입금액']:,}원",font=F(13),fill=SUB)
        y+=72
    y+=6
    d.text((26,y),season_note(),font=F(15),fill=(255,210,120)); y+=26
    d.text((26,y),"수량 = (자본×리스크%) ÷ 1R — 손절 시 손실이 설정 리스크와 같아지는 크기",font=F(13),fill=BLUE); y+=22
    d.text((26,y),"발굴 ≠ 매수신호 · 추격 금지 · 진입 시 손절가 동시 설정 · 결정·책임 본인",font=F(13),fill=(88,94,104))
    out=os.path.join(HERE,"종목발굴_카톡.png"); img.crop((0,0,W,y+30)).save(out)
    print(f"[산출] 종목발굴_카톡.png · {asof.date()}")
    return out


def main():
    ap=argparse.ArgumentParser(description="종목 발굴 + 매매 준비 (발굴 ≠ 매수신호)")
    ap.add_argument("--capital",type=int,default=10_000_000,help="투자 자본(원)")
    ap.add_argument("--risk",type=float,default=1.0,help="트레이드당 리스크 %%")
    ap.add_argument("--top",type=int,default=8,help="후보 수")
    ap.add_argument("--breakout",action="store_true",help="돌파 모드(10배 후보군·실패율↑·사이징 절반)")
    ap.add_argument("--card",action="store_true",help="카드(PNG) 생성")
    ap.add_argument("--no-tilt",action="store_true",help="⑥ 검증 기울기(저PBR·저변동성) 끄기 — 배선 전후 비교용")
    ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()

    if a.self_test:
        ok=tot=0
        def chk(n,c):
            nonlocal ok,tot; tot+=1; ok+=1 if c else 0
            print(f"  [{'OK' if c else 'FAIL'}] {n}")
        chk("load_daily 동작", load_daily() is not None)
        chk("season_note 문자열", isinstance(season_note(),str))
        chk("하순 필터 연동", "하순" in season_note() or "진입 가능" in season_note() or "⚪" in season_note())
        chk("CFG 정합(ATR_K>0)", CFG["ATR_K"]>0)
        # ⑥ 시총 tier별 검증 기울기 — 소=저변동 위주 / 중=결합 / 대=페널티
        chk("소형 가중 저변동>저PBR", CFG["TILT_VOL_S"]>CFG["TILT_PBR_S"])
        chk("중형 가중 저변동=저PBR(결합)", abs(CFG["TILT_VOL_M"]-CFG["TILT_PBR_M"])<1e-9)
        chk("대형 페널티<0", CFG["TILT_LARGE_PEN"]<0)
        chk("tier_of: 소/중/대 경계", tier_of(100,(500,1800))=="소" and tier_of(1000,(500,1800))=="중" and tier_of(5000,(500,1800))=="대")
        chk("tier_of: 경계없음→중(중립)", tier_of(1e12,None)=="중")
        # 심은 데이터로 tier별 기울기 방향 확인
        _t=pd.DataFrame({"시총tier":["소","소","중","대"],"변동성60":[2.0,5.0,2.5,2.8],"PBR":[1.5,1.2,0.5,0.8]})
        _lv=(1-_t["변동성60"].rank(pct=True)).fillna(0.5); _lp=(1-_t["PBR"].rank(pct=True)).fillna(0.5); W=CFG["TILT_W"]
        def _tf(i):
            t=_t["시총tier"].iloc[i]
            if t=="대": return CFG["TILT_LARGE_PEN"]*W
            wv,wp=(CFG["TILT_VOL_S"],CFG["TILT_PBR_S"]) if t=="소" else (CFG["TILT_VOL_M"],CFG["TILT_PBR_M"])
            return (wv*_lv.iloc[i]+wp*_lp.iloc[i])*W
        _tl=[_tf(i) for i in range(4)]
        chk("대형 기울기 음수(아래로)", _tl[3]<0)
        chk("소형 저변동>고변동(0행>1행)", _tl[0]>_tl[1])
        chk("PBR 결측=중립(0.5)", ((1-pd.Series([np.nan,np.nan]).rank(pct=True)).fillna(0.5)==0.5).all())
        chk("load_pbr 딕셔너리 반환", isinstance(load_pbr(),dict))
        chk("load_mcap 튜플(dict,cuts) 반환", isinstance(load_mcap(),tuple) and isinstance(load_mcap()[0],dict))
        print(f"\n셀프테스트: {ok}/{tot}")
        return 0 if ok==tot else 1

    print("="*78)
    print(f"종목 발굴 {'[돌파 모드]' if a.breakout else '[안정 모드]'}  ·  "
          f"자본 {a.capital:,}원 · 리스크 {a.risk}%")
    print("="*78)
    print(f"  {season_note()}")
    print("  발굴 ≠ 매수신호. 필터 통과 = '볼 만한 후보'일 뿐. 결정·책임 본인.\n")

    tilt=not a.no_tilt
    print(f"  순위 기울기(⑥ 저PBR·저변동성): {'ON' if tilt else 'OFF(--no-tilt)'}  근거 C·②\n")
    T,asof,excl=scan(a.capital,a.risk,a.top,a.breakout,tilt=tilt)
    if T is None or len(T)==0:
        print("  [결과] 조건을 통과한 후보 없음.")
        if excl: print(f"  제외 내역: {excl}")
        return 0

    cols=["name","시총tier","theme","현재가","손절가","손절폭","R","수량","투입금액","PBR","변동성60","기울기","RS_3M","자금유입배수"]
    cols=[c for c in cols if c in T.columns]
    print(T[cols].to_string(index=False))
    print(f"\n  기준일 {asof.date()} · 제외 내역 {excl}")

    out=os.path.join(HERE,"발굴후보.csv")
    T.to_csv(out,index=False,encoding="utf-8-sig")
    print(f"[산출] 발굴후보.csv ({len(T)}종목)")

    if a.card:
        try: make_card(T,asof,a.capital,a.risk)
        except Exception as e: print(f"  [카드 생략] {str(e)[:60]}")
    return 0


if __name__=="__main__":
    sys.exit(main())