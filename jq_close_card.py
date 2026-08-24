# -*- coding: utf-8 -*-
"""jq_close_card.py — 국내증시 마감 브리핑 카드뉴스.
데이터: 같은 폴더 jq_close_data.json (스케줄이 웹검색값으로 채움). 실데이터만·가짜 금지.
산출: 마감브리핑_카톡.png → 메인 + 카드뉴스/YYYY-MM-DD/ + OneDrive.
"""
import os, sys, json, datetime
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
BG=(15,17,21); ACC=(255,122,69); GREEN=(63,179,122); RED=(226,96,106); YEL=(224,176,32); GREY=(150,156,166); BLUE=(90,160,240); TXT=(232,234,237); SUB=(150,156,166)

def render(D):
    W=820; pad=26; img=Image.new("RGB",(W,900),BG); d=ImageDraw.Draw(img); d.rectangle([0,0,W,6],fill=ACC); y=24
    d.text((pad,y),f"국내증시 마감 브리핑 · 기준일 {D['date']}",font=F(29),fill=(255,255,255)); y+=42
    d.text((pad,y),"장 마감 실데이터(공개 뉴스) · 매수·매도 추천 아님 · 결정·책임 본인",font=F(14),fill=SUB); y+=34
    cw=(W-2*pad-14)//2
    def block(x,title,val,chg):
        up=chg>=0; col=RED if up==False else GREEN  # 국내: 상승=빨강? → 표준 초록/빨강 유지: 상승=초록
        col=GREEN if up else RED; ar='▲' if up else '▼'; tint=(22,30,26) if up else (34,22,24)
        d.rectangle([x,y,x+cw,y+96],fill=tint,outline=(46,50,60),width=1); d.rectangle([x,y,x+5,y+96],fill=col)
        d.text((x+16,y+12),title,font=F(15),fill=SUB); d.text((x+16,y+32),f"{val:,.2f}",font=F(30),fill=(255,255,255))
        d.text((x+16,y+74),f"{ar} {chg:+.2f}%",font=F(19),fill=col)
    d.text((pad,y),"■ 지수 마감",font=F(15),fill=ACC); y+=26
    block(pad,"코스피",D['kospi'],D['kospi_chg']); block(pad+cw+14,"코스닥",D['kosdaq'],D['kosdaq_chg']); y+=112
    # 수급
    d.text((pad,y),"■ 투자자별 수급 (순매수, 억원)",font=F(15),fill=ACC); y+=26
    bh=58; d.rectangle([pad,y,W-pad,y+bh],fill=(24,27,34),outline=(46,50,60),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=BLUE)
    inv=D.get('inv',{}); xx=pad+18
    for who in ["기관","외국인","개인"]:
        v=inv.get(who)
        if v is None: continue
        col=GREEN if v>0 else RED; sign='+' if v>0 else ''
        d.text((xx,y+8),who,font=F(14),fill=SUB); d.text((xx,y+28),f"{sign}{v:,}",font=F(18),fill=col); xx+=(W-2*pad)//3
    y+=bh+16
    # 동인
    if D.get('driver'):
        d.text((pad,y),"■ 오늘의 동인",font=F(15),fill=ACC); y+=26
        d.text((pad+8,y),D['driver'],font=F(16),fill=TXT); y+=32
    # 인사이트
    if D.get('insight'):
        d.text((pad,y),"■ 인사이트 (야간 선물 연계)",font=F(15),fill=ACC); y+=26
        bh=52; d.rectangle([pad,y,W-pad,y+bh],fill=(20,28,24),outline=(50,80,60),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=GREEN)
        d.text((pad+16,y+8),"→ "+D['insight'][:64],font=F(14),fill=(150,220,170))
        if len(D['insight'])>64: d.text((pad+16,y+28),D['insight'][64:128],font=F(14),fill=(150,220,170))
        y+=bh+16
    d.text((pad,y),"해설 · 상승=초록·하락=빨강 · 수급 순매수(+)/순매도(-) · 야간 선물이 미국장 반영해 방향 선행",font=F(13),fill=(120,165,210)); y+=22
    d.text((pad,y),f"출처: {D.get('sources','공개 뉴스')} · 매수·매도 추천 아님 · 결정·책임 본인",font=F(13),fill=(88,94,104)); y+=26
    return img.crop((0,0,W,y+6))

def main():
    p=os.path.join(HERE,"jq_close_data.json")
    if not os.path.exists(p):
        print("[오류] jq_close_data.json 없음"); return 2
    D=json.load(open(p,encoding="utf-8"))
    img=render(D); dt=D['date']
    out=os.path.join(HERE,"마감브리핑_카톡.png"); img.save(out)
    dd=os.path.join(HERE,"카드뉴스",dt); os.makedirs(dd,exist_ok=True)
    import shutil
    for t in [os.path.join(dd,"마감브리핑_카톡.png"), os.path.join(os.path.expanduser(r"~\OneDrive\문서\Claude\Projects\진우퀀트"),"마감브리핑_카톡.png")]:
        try:
            if os.path.isdir(os.path.dirname(t)): shutil.copy(out,t)
        except Exception: pass
    print("[산출] 마감브리핑_카톡.png ·",dt)
    return 0
if __name__=="__main__": sys.exit(main())
