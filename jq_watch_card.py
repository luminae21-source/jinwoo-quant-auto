# -*- coding: utf-8 -*-
"""jq_watch_card.py — 관심 워치리스트 카드뉴스.
데이터: 같은 폴더 jq_watchlist.json (스케줄이 매일 유지·갱신). 실데이터만·가짜 금지.
성격: '추천' 아님. 내가 며칠간 지켜보는 관심종목 + 진입/손절 규율 추적.
산출: 관심워치리스트_카톡.png → 메인 + 카드뉴스/YYYY-MM-DD/ + OneDrive.
"""
import os, sys, json
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from PIL import Image, ImageDraw, ImageFont
def _fp():
    for p in [r"C:\Windows\Fonts\malgun.ttf","/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
        if os.path.exists(p): return p
    return None
FP=_fp()
def F(s): return ImageFont.truetype(FP,s) if FP else ImageFont.load_default()
BG=(15,17,21); ACC=(255,122,69); GREEN=(63,179,122); RED=(226,96,106); YEL=(224,176,32); BLUE=(90,160,240); TXT=(232,234,237); SUB=(150,156,166)

def _status_color(s):
    if any(k in s for k in ["이탈","제외","손절","약화"]): return RED,(34,22,24)
    if any(k in s for k in ["근접","관찰","주의"]): return YEL,(34,30,20)
    return GREEN,(22,30,26)

def render(D):
    W=820; pad=26
    items=D.get('items',[])
    H=360+len(items)*60
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img); d.rectangle([0,0,W,6],fill=BLUE); y=24
    d.text((pad,y),f"관심 워치리스트 · 기준일 {D['updated']}",font=F(29),fill=(255,255,255)); y+=42
    d.text((pad,y),"내가 지켜보는 종목 · 추천 아님 · 진입 시 손절가 동시 설정 · 결정·책임 본인",font=F(14),fill=SUB); y+=32
    # 상태 범례
    lx=pad; d.text((lx,y),"상태:",font=F(13),fill=SUB); lx+=44
    for lab,(c,_) in [("추세 유효",(GREEN,0)),("지지 근접",(YEL,0)),("이탈·제외후보",(RED,0))]:
        d.rectangle([lx,y+2,lx+12,y+14],fill=c); lx+=18
        d.text((lx,y),lab,font=F(13),fill=TXT); lx+=int(d.textlength(lab,font=F(13)))+22
    y+=30
    # 종목 카드들
    for it in items:
        nm=it.get('name',''); th=it.get('theme',''); stt=it.get('status','관찰')
        note=it.get('note',''); sup=it.get('support',''); stp=it.get('stop','')
        col,tint=_status_color(stt)
        rh=54; d.rectangle([pad,y,W-pad,y+rh],fill=(22,25,31),outline=(44,48,58),width=1); d.rectangle([pad,y,pad+5,y+rh],fill=col)
        d.text((pad+18,y+8),nm,font=F(17),fill=(255,255,255))
        if th:
            bw=d.textlength(th,font=F(12)); d.rectangle([pad+200,y+9,pad+200+bw+14,y+29],fill=(24,34,30),outline=GREEN,width=1); d.text((pad+207,y+11),th,font=F(12),fill=(120,220,170))
        # 상태 배지(우측)
        sw=d.textlength(stt,font=F(13)); bx1=W-pad-10; bx0=bx1-sw-16
        d.rectangle([bx0,y+8,bx1,y+30],fill=tint,outline=col,width=1); d.text((bx0+8,y+10),stt,font=F(13),fill=col)
        # 2행: 근거 + 규율(지지/손절)
        if note: d.text((pad+18,y+32),"· "+note,font=F(12),fill=SUB)
        disc=f"지지 {sup} · 손절 {stp}" if (sup or stp) else ""
        if disc:
            dw=d.textlength(disc,font=F(12)); d.text((W-pad-10-dw,y+32),disc,font=F(12),fill=YEL)
        y+=rh+6
    y+=6
    d.text((pad,y),"규율 · 추세 유효 종목만 유지 · 이탈 시 제외 후보 · 진입은 지지 재확인 후 · 손절가 먼저 정하기",font=F(13),fill=(224,176,80)); y+=22
    d.text((pad,y),"해설 · 급등 추격이 아니라 조정 시 지지에서 관심 · 구체 진입가·손절가는 본인이 차트로 확정",font=F(13),fill=(120,165,210)); y+=22
    d.text((pad,y),f"출처: {D.get('sources','공개 뉴스·주도주/순환매')} · 추천 아님 · 결정·책임 본인",font=F(13),fill=(88,94,104)); y+=26
    return img.crop((0,0,W,y+6))

def main():
    p=os.path.join(HERE,"jq_watchlist.json")
    if not os.path.exists(p):
        print("[오류] jq_watchlist.json 없음"); return 2
    D=json.load(open(p,encoding="utf-8")); dt=D['updated']
    img=render(D)
    out=os.path.join(HERE,"관심워치리스트_카톡.png"); img.save(out)
    dd=os.path.join(HERE,"카드뉴스",dt); os.makedirs(dd,exist_ok=True)
    import shutil
    for t in [os.path.join(dd,"관심워치리스트_카톡.png"), os.path.join(os.path.expanduser(r"~\OneDrive\문서\Claude\Projects\진우퀀트"),"관심워치리스트_카톡.png")]:
        try:
            if os.path.isdir(os.path.dirname(t)): shutil.copy(out,t)
        except Exception: pass
    print("[산출] 관심워치리스트_카톡.png ·",dt)
    return 0
if __name__=="__main__": sys.exit(main())
