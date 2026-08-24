# -*- coding: utf-8 -*-
"""jq_deriv_card.py — 선물·옵션 카드뉴스 (KRX Open API 실데이터, PC 전용)
KOSPI200 선물(종가·베이시스·OI·1계약 명목가치·증거금) + KOSDAQ150 선물 + KOSPI200 옵션체인(행사가·콜/풋 프리미엄·ATM).
데이터: krx_openapi.py(승인키 필요). 실패=데이터부족(가짜 금지). 첫 실행 시 jq_deriv_dump.txt에 원시행 덤프(파싱 검증용).
"""
import os, re, sys, datetime
HERE=os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0,HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from PIL import Image, ImageDraw, ImageFont
def _fp():
    for p in [r"C:\Windows\Fonts\malgun.ttf","/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
        if os.path.exists(p): return p
    return None
FP=_fp()
def F(s): return ImageFont.truetype(FP,s) if FP else ImageFont.load_default()
BG=(15,17,21); ACC=(255,122,69); GREEN=(63,179,122); RED=(226,96,106); YEL=(224,176,32); GREY=(150,156,166); BLUE=(90,160,240); TXT=(232,234,237); SUB=(150,156,166)
K200_MULT=250000; KQ150_MULT=10000; INIT_M=0.081; MAINT_M=0.054
def eok(n):
    return f"{n/1e8:.2f}억" if n>=1e8 else f"{n/1e4:,.0f}만원"

def next_expiries():
    import glob
    fs=sorted(glob.glob(os.path.join(HERE,"시장브리핑_*.md")))
    if not fs: return None,None
    txt=open(fs[-1],encoding="utf-8").read()
    today=datetime.date.today().isoformat(); opt=None; quad=None; ins=False
    for line in txt.splitlines():
        if "이벤트 캘린더" in line: ins=True; continue
        if ins:
            if line.strip().startswith("## "): break
            m=re.match(r"- (\d{4}-\d{2}-\d{2})\s*:\s*(.+)",line.strip())
            if not m: continue
            dt,rest=m.group(1),m.group(2)
            if "옵션만기" in rest and "위클리" not in rest and dt>=today and opt is None: opt=dt
            if ("동시만기" in rest or "네 마녀" in rest) and dt>=today and quad is None: quad=dt
    return opt,quad

def fetch():
    D={'date':datetime.date.today().strftime('%Y-%m-%d'),'errs':[]}
    dump=[]
    try:
        import krx_openapi as K
    except Exception as e:
        D['errs'].append('krx_openapi import '+str(e)); return D
    try:
        key=K.auth_key()
    except Exception as e:
        key=None; D['errs'].append('auth_key '+str(e))
    if not key:
        D['errs'].append('KRX 인증키 없음(krx_authkey.txt)'); return D
    NUM=getattr(K,'_num',lambda x:None)
    def num(x):
        try: return NUM(x)
        except Exception:
            try: return float(str(x).replace(',',''))
            except Exception: return None
    # KOSPI200 선물
    try:
        c,oi,spot=K.get_futures_k200(key)
        D['k200_fut']=c; D['k200_oi']=oi; D['k200_spot']=spot
        if c and spot: D['basis']=c-spot
    except Exception as e: D['errs'].append('K200선물 '+str(e))
    # 원시행 fetch 헬퍼
    def fetch_rows(path):
        for fn in ('_fetch','_fetch_dated'):
            f=getattr(K,fn,None)
            if f:
                try:
                    r=f(path,key)
                    return r[0] if isinstance(r,tuple) else r
                except Exception: pass
        return []
    # KOSDAQ150 선물
    try:
        fut=fetch_rows("drv/fut_bydd_trd")
        _bd=next((str(r.get('BAS_DD')) for r in (fut or []) if r.get('BAS_DD')),None)
        if _bd and len(_bd)==8: D['date']=_bd[:4]+'-'+_bd[4:6]+'-'+_bd[6:]
        kq=[r for r in fut if '코스닥150' in (str(r.get('PROD_NM',''))+str(r.get('ISU_NM',''))).replace(' ','')]
        dump.append('=== KOSDAQ150 fut rows (%d) ==='%len(kq))
        for r in kq[:6]: dump.append(str(r))
        def oiv(r): return num(r.get('ACC_OPNINT_QTY') or r.get('OPNINT_QTY')) or 0
        if kq:
            top=max(kq,key=oiv); D['kq150_fut']=num(top.get('TDD_CLSPRC')); D['kq150_oi']=oiv(top)
        _k2f=[r for r in fut if '코스피200' in (str(r.get('PROD_NM',''))+str(r.get('ISU_NM',''))).replace(' ','') and '미니' not in str(r.get('PROD_NM','')) and '주식' not in str(r.get('PROD_NM',''))]
        dump.append('=== KOSPI200 fut rows (%d) ==='%len(_k2f))
        for r in sorted(_k2f,key=lambda x:-oiv(x))[:8]: dump.append(str(r))
        def _night(pk):
            ns=[r for r in fut if pk in str(r.get('PROD_NM','')).replace(' ','') and '미니' not in str(r.get('PROD_NM','')) and '주식' not in str(r.get('PROD_NM','')) and '야간' in str(r.get('MKT_NM','')) and num(r.get('TDD_CLSPRC'))]
            ns=sorted(ns,key=lambda x:-oiv(x)); return num(ns[0].get('TDD_CLSPRC')) if ns else None
        D['k200_night']=_night('코스피200'); D['kq150_night']=_night('코스닥150')
    except Exception as e: D['errs'].append('KOSDAQ150 '+str(e))
    # KOSPI200 옵션 체인 — urllib 직접 fetch(대용량 ~2만행, requests 타임아웃 회피; krx_openapi 검증 방식)
    try:
        import urllib.request as _u, json as _j
        def opt_rows(dd):
            try:
                req=_u.Request("%s/drv/opt_bydd_trd?basDd=%s"%(K.API,dd),headers={"AUTH_KEY":key})
                o=_j.loads(_u.urlopen(req,timeout=45).read().decode("utf-8","replace"))
                return o.get("OutBlock_1",[]) if isinstance(o,dict) else []
            except Exception: return []
        opt=[]
        for dd in K.recent_bdays(8):
            opt=opt_rows(dd)
            if opt: break
        dump.append('=== opt rows (%d) 컬럼:%s ==='%(len(opt), list(opt[0].keys()) if opt else []))
        for r in opt[:12]: dump.append(str(r))
        def sidef(r):
            t=str(r.get('RGHT_TP_NM','') or r.get('RGHT_TP_CD',''))
            if 'CALL' in t.upper() or '콜' in t: return 'C'
            if 'PUT' in t.upper() or '풋' in t: return 'P'
            nm=str(r.get('ISU_NM',''))
            if '콜' in nm or ' C ' in nm: return 'C'
            if '풋' in nm or ' P ' in nm: return 'P'
            return None
        def isk2(r):
            nm=(str(r.get('PROD_NM',''))+str(r.get('ISU_NM',''))).replace(' ','')
            return ('코스피200' in nm or 'KOSPI200' in nm) and '위클리' not in nm and '미니' not in nm
        def strikef(r):
            for kc in ('STRK_PRC','행사가','EXER_PRC','ATM_PRC'):
                v=num(r.get(kc))
                if v: return v
            nums=re.findall(r'\d+\.?\d*',str(r.get('ISU_NM','')))
            return float(nums[-1]) if nums else None
        from collections import defaultdict
        parsed=[]  # (month, cp, strike, prem, oi)
        for r in opt:
            if not isk2(r): continue
            cp=sidef(r); strike=strikef(r); prem=num(r.get('TDD_CLSPRC'))
            if prem is None: prem=num(r.get('NXTDD_BAS_PRC'))
            oi=num(r.get('ACC_OPNINT_QTY')) or 0
            mon=re.search(r'20\d{4}',str(r.get('ISU_NM','')).replace(' ',''))
            if cp and strike and prem is not None:
                parsed.append((mon.group(0) if mon else '',cp,strike,prem,oi))
        _k2=[r for r in opt if isk2(r)]
        dump.append('=== 정규 KOSPI200 opt rows (%d) ==='%len(_k2))
        for r in _k2[:8]: dump.append(str(r))
        if parsed:
            moi=defaultdict(float)
            for m,cp,st,pr,oi in parsed: moi[m]+=oi
            nm0=max(moi,key=moi.get)
            near=[x for x in parsed if x[0]==nm0]
            calls={x[2]:x[3] for x in near if x[1]=='C'}; puts={x[2]:x[3] for x in near if x[1]=='P'}
            strikes=sorted(set(list(calls)+list(puts)))
            _spot=D.get('k200_spot') or D.get('k200_fut') or 0
            dump.append('월물별 OI: %s'%{k:int(v) for k,v in sorted(moi.items())})
            if strikes and _spot and _spot>strikes[-1]*1.02:
                D['opt_note']="행사가 사다리 %.1f~%.1f < 지수 %.0f → ATM 행사가 미상장(전구간 콜 ITM), 데이터부족"%(strikes[0],strikes[-1],_spot)
                dump.append('ATM 미상장: spot %.1f > maxstrike %.1f'%(_spot,strikes[-1]))
            elif strikes:
                both=[st for st in strikes if calls.get(st) is not None and puts.get(st) is not None]
                atm=min(both,key=lambda st:abs(calls[st]-puts[st])) if both else min(strikes,key=lambda st:abs(st-_spot))
                D['atm']=atm; D['opt_month']=nm0
                i=strikes.index(atm) if atm in strikes else len(strikes)//2
                sel=strikes[max(0,i-2):i+3]
                D['chain']=[(st,calls.get(st),puts.get(st)) for st in sel]
        try:
            cv=sum((num(r.get('ACC_TRDVOL')) or 0) for r in opt if sidef(r)=='C')
            pv=sum((num(r.get('ACC_TRDVOL')) or 0) for r in opt if sidef(r)=='P')
            if cv>0: D['pcr']=pv/cv
        except Exception: pass
    except Exception as e: D['errs'].append('옵션 '+str(e))
    try: open(os.path.join(HERE,'jq_deriv_dump.txt'),'w',encoding='utf-8').write('\n'.join(dump))
    except Exception: pass
    return D

def render(D):
    W=820; pad=26; img=Image.new("RGB",(W,1260),BG); d=ImageDraw.Draw(img); d.rectangle([0,0,W,6],fill=ACC); y=24
    d.text((pad,y),f"선물 · 옵션 · 기준일 {D['date']}",font=F(30),fill=(255,255,255)); y+=42
    d.text((pad,y),"KRX 파생 일별 종가(T-1) · 지수파생 · 매수·매도 추천 아님(고위험)",font=F(14),fill=SUB); y+=26
    _eo,_eq=next_expiries()
    _mt="만기 · 매월 둘째 목요일" + (f"  |  다음 월물 {_eo}" if _eo else "") + (f" · 분기 동시만기(네마녀) {_eq}" if _eq else "")
    d.text((pad,y),_mt,font=F(14),fill=ACC); y+=32
    fut=D.get('k200_fut'); spot=D.get('k200_spot'); basis=D.get('basis'); oi=D.get('k200_oi')
    d.text((pad,y),"■ KOSPI200 선물 (근월물)",font=F(15),fill=ACC); y+=26
    bh=150; d.rectangle([pad,y,W-pad,y+bh],fill=(24,27,34),outline=ACC,width=1); d.rectangle([pad,y,pad+5,y+bh],fill=ACC)
    if fut:
        d.text((pad+16,y+12),"선물 지수",font=F(14),fill=SUB); d.text((pad+16,y+30),f"{fut:,.2f}",font=F(34),fill=(255,255,255))
        if basis is not None:
            bc=GREEN if basis>0 else RED
            d.text((pad+16,y+76),f"베이시스 {basis:+.2f} ({'콘탱고' if basis>0 else '백워데이션'})",font=F(15),fill=bc)
        d.text((pad+16,y+102),f"현물 {spot:,.2f} · 미결제약정 {oi:,.0f}" if spot else f"미결제약정 {oi:,.0f}",font=F(14),fill=TXT)
        nom=fut*K200_MULT
        d.text((pad+360,y+12),"1계약 명목가치",font=F(14),fill=SUB); d.text((pad+360,y+30),f"{eok(nom)}",font=F(26),fill=BLUE)
        d.text((pad+360,y+66),f"= {fut:,.2f} × 25만원/pt",font=F(13),fill=SUB)
        d.text((pad+360,y+92),f"개시증거금 8.1% 약 {eok(nom*INIT_M)}",font=F(14),fill=YEL)
        d.text((pad+360,y+116),f"유지 5.4% 약 {eok(nom*MAINT_M)}",font=F(13),fill=SUB)
    else:
        d.text((pad+16,y+55),"데이터부족 (KRX 인증키/응답 확인)",font=F(18),fill=SUB)
    y+=bh+16
    d.text((pad,y),"■ KOSDAQ150 선물",font=F(15),fill=ACC); y+=26
    bh=64; d.rectangle([pad,y,W-pad,y+bh],fill=(24,27,34),outline=(46,50,60),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=GREEN)
    kq=D.get('kq150_fut')
    if kq:
        d.text((pad+16,y+10),"선물 지수",font=F(14),fill=SUB); d.text((pad+16,y+28),f"{kq:,.2f}",font=F(24),fill=(255,255,255))
        d.text((pad+300,y+14),f"미결제약정 {D.get('kq150_oi',0):,.0f} · 승수 1만원/pt",font=F(14),fill=TXT)
        d.text((pad+300,y+36),f"1계약 명목가치 {eok(kq*KQ150_MULT)}",font=F(14),fill=BLUE)
    else:
        d.text((pad+16,y+20),"데이터부족",font=F(16),fill=SUB)
    y+=bh+16
    kn=D.get('k200_night'); qn=D.get('kq150_night')
    if kn or qn:
        _dd=D.get('date','')
        try:
            _d0=datetime.date.fromisoformat(_dd); _d1=_d0+datetime.timedelta(days=1); _nl=f"{_d0.month}/{_d0.day} 야간(→{_d1.month}/{_d1.day} 새벽) · "
        except Exception: _nl=""
        d.text((pad,y),f"■ 야간 선물 · {_nl}미국장 반영 → 익일 방향 힌트",font=F(15),fill=ACC); y+=26
        _rows=[("KOSPI200 선물",kn,D.get('k200_fut')),("KOSDAQ150 선물",qn,D.get('kq150_fut'))]
        bh=72; d.rectangle([pad,y,W-pad,y+bh],fill=(20,24,32),outline=(50,60,80),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=BLUE)
        yy=y+12; _gs=[]
        for lab,night,day in _rows:
            if not (night and day): continue
            g=(night/day-1)*100; _gs.append(g)
            if g>=3: col=(90,230,140); badge="급등 주의"; bg=(38,30,24)
            elif g>=2: col=GREEN; badge="강세"; bg=(24,30,26)
            elif g<=-3: col=(255,110,120); badge="급락 주의"; bg=(40,24,26)
            elif g<=-2: col=RED; badge="약세"; bg=(32,24,26)
            else: col=(GREEN if g>0 else (RED if g<0 else GREY)); badge=""; bg=None
            ar='▲' if g>0 else ('▼' if g<0 else '·')
            d.text((pad+16,yy),lab,font=F(15),fill=(255,255,255))
            d.text((pad+200,yy),f"야간 {night:,.2f}",font=F(16),fill=TXT)
            d.text((pad+380,yy),f"주간比 {g:+.2f}% {ar}",font=F(16),fill=col)
            if badge:
                bw=d.textlength(badge,font=F(13)); d.rectangle([W-pad-bw-26,yy-1,W-pad-8,yy+21],fill=bg,outline=col,width=1); d.text((W-pad-bw-17,yy+2),badge,font=F(13),fill=col)
            yy+=27
        y+=bh+6
        if _gs:
            avg=sum(_gs)/len(_gs)
            if avg>=2: sig="야간 강세 → 익일 국내 개장 상승 압력(참고)"; sc=(90,230,140)
            elif avg<=-2: sig="야간 약세 → 익일 국내 개장 하락 압력(참고)"; sc=(255,110,120)
            elif abs(avg)<0.5: sig="야간 보합 → 뚜렷한 방향성 약함"; sc=SUB
            else: sig=("야간 소폭 강세" if avg>0 else "야간 소폭 약세")+" → 참고"; sc=(GREEN if avg>0 else RED)
            d.text((pad,y),"→ "+sig,font=F(14),fill=sc); y+=26
    chain=D.get('chain') or []
    if chain:
        _om=D.get('opt_month'); _oml=(f"{_om[2:4]}년 {int(_om[4:6])}월물" if _om and len(_om)>=6 else "근월물")
        d.text((pad,y),f"■ KOSPI200 옵션 체인 (ATM 근처 · {_oml})",font=F(15),fill=ACC); y+=26
        cS=pad+40; cC=pad+280; cP=pad+520
        d.text((cC-30,y),"콜(Call) 프리미엄",font=F(13),fill=GREEN); d.text((cP-30,y),"풋(Put) 프리미엄",font=F(13),fill=RED); d.text((cS-20,y),"행사가",font=F(13),fill=SUB); y+=24
        atm=D.get('atm')
        for strike,call,put in chain:
            isa=(atm and abs(strike-atm)<0.6)
            if isa: d.rectangle([pad,y-2,W-pad,y+26],fill=(38,34,26))
            d.text((cS-20,y),f"{strike:,.1f}",font=F(16),fill=(255,215,120) if isa else TXT)
            d.text((cC-30,y),(f"{call:,.2f}" if call is not None else "-"),font=F(16),fill=GREEN)
            d.text((cP-30,y),(f"{put:,.2f}" if put is not None else "-"),font=F(16),fill=RED)
            if isa: d.text((W-pad-60,y),"ATM",font=F(13),fill=ACC)
            y+=28
        if D.get('pcr'): d.text((pad,y+4),f"풋/콜 비율 {D['pcr']:.3f} · 프리미엄 옵션 1pt=25만원",font=F(14),fill=SUB); y+=28
    else:
        d.text((pad,y),"■ KOSPI200 옵션",font=F(15),fill=ACC); y+=26
        bh3=70; d.rectangle([pad,y,W-pad,y+bh3],fill=(28,26,22),outline=(80,66,44),width=1); d.rectangle([pad,y,pad+5,y+bh3],fill=YEL)
        if D.get('pcr'): d.text((pad+16,y+10),f"풋/콜 비율(거래량) {D['pcr']:.3f}",font=F(17),fill=(255,255,255))
        d.text((pad+16,y+38),(D.get('opt_note') or "옵션 체인 데이터부족 — jq_deriv_dump.txt 참고")[:74],font=F(13),fill=SUB); y+=bh3+2
    if D.get('errs'):
        y+=6; d.text((pad,y),"※ 미수신: "+" · ".join(D['errs'])[:90],font=F(12),fill=(150,110,90)); y+=20
    d.text((pad,y),"■ 1틱(최소 호가) 금액",font=F(15),fill=ACC); y+=26
    bh2=104; d.rectangle([pad,y,W-pad,y+bh2],fill=(24,27,34),outline=(46,50,60),width=1); d.rectangle([pad,y,pad+5,y+bh2],fill=YEL)
    yy=y+14
    for lab,val,col in [("KOSPI200 선물","0.05pt = 12,500원",BLUE),("KOSPI200 옵션","0.01pt = 2,500원 (프리미엄<10pt) · 0.05pt = 12,500원 (10pt 이상)",GREEN),("KOSDAQ150 선물","0.10pt = 1,000원",GREEN)]:
        d.ellipse([pad+16,yy+6,pad+26,yy+16],fill=col); d.text((pad+36,yy),lab,font=F(15),fill=(255,255,255)); d.text((pad+220,yy),val,font=F(14),fill=TXT); yy+=28
    y+=bh2+14
    y+=6
    d.text((pad,y),"해설 · 명목가치=계약 규모 · 증거금=진입 자금 · 풋콜비율=심리(비용X) · 옵션비용=프리미엄×25만원",font=F(13),fill=(120,165,210)); y+=22
    d.text((pad,y),"승수 KOSPI200 25만원/pt · KOSDAQ150 1만원/pt · 증거금률 변동(KRX 고시) · 파생 고위험",font=F(13),fill=(200,150,90)); y+=22
    d.text((pad,y),"KRX Open API 실데이터(T-1 종가) · 매수·매도 추천 아님 · 결정·책임 본인",font=F(13),fill=(88,94,104)); y+=26
    return img.crop((0,0,W,y+6))

def save(img,dstamp):
    import shutil
    p=os.path.join(HERE,"선물옵션_카드.png"); img.save(p)
    dd=os.path.join(HERE,"카드뉴스",dstamp); os.makedirs(dd,exist_ok=True)
    for t in [os.path.join(dd,"선물옵션_카드.png"), os.path.join(os.path.expanduser(r"~\OneDrive\문서\Claude\Projects\진우퀀트"),"선물옵션_카드.png")]:
        try:
            if os.path.isdir(os.path.dirname(t)): shutil.copy(p,t)
        except Exception: pass
    return p

def main():
    D=fetch()
    img=render(D)
    p=save(img,D['date'])
    print("[산출]",os.path.basename(p),"· errs:",D.get('errs'))
    return 0
if __name__=="__main__": sys.exit(main())
