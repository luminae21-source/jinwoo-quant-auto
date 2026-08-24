# -*- coding: utf-8 -*-
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
BG=(15,17,21); ACC=(255,122,69); GREEN=(63,179,122); RED=(226,96,106); YEL=(224,176,32); GREY=(150,156,166); BLUE=(90,160,240); TXT=(232,234,237); SUB=(150,156,166)

def render(D):
    W=820; pad=26
    vt=D.get('value_top',[]); st=D.get('sector_top',[]); gn=D.get('gainers',[]); tw=D.get('trend_watch',[])
    H=1560
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img); d.rectangle([0,0,W,6],fill=ACC); y=24
    d.text((pad,y),f"마감 특징주·섹터 · 기준일 {D['date']}",font=F(29),fill=(255,255,255)); y+=42
    d.text((pad,y),"장 마감 실데이터(공개 뉴스) · 매수·매도 추천 아님 · 결정·책임 본인",font=F(14),fill=SUB); y+=34
    if D.get('driver'):
        d.text((pad,y),"■ 오늘의 동인",font=F(15),fill=ACC); y+=26
        bh=52; d.rectangle([pad,y,W-pad,y+bh],fill=(28,26,22),outline=(80,66,44),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=ACC)
        dv=D['driver']; d.text((pad+16,y+9),dv[:44],font=F(15),fill=TXT)
        if len(dv)>44: d.text((pad+16,y+29),dv[44:92],font=F(14),fill=SUB)
        y+=bh+16
    if D.get('breadth'):
        d.text((pad,y),"■ 시장 폭  ·  "+D['breadth'],font=F(14),fill=SUB); y+=26
    if gn:
        d.text((pad,y),"■ 상승 마감 종목 (오늘 등락률 · 급락장 상대강도)",font=F(15),fill=ACC); y+=26
        bh=14+len(gn)*30; d.rectangle([pad,y,W-pad,y+bh],fill=(22,30,26),outline=(50,80,60),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=GREEN)
        yy=y+10
        for item in gn:
            nm=item[0]; pct=item[1] if len(item)>1 else None; tag=item[2] if len(item)>2 else ""
            d.text((pad+16,yy),nm,font=F(16),fill=(255,255,255))
            if pct is not None: d.text((pad+300,yy),f"▲ +{pct:.2f}%",font=F(16),fill=GREEN)
            if tag:
                bw=d.textlength(tag,font=F(13)); d.rectangle([pad+440,yy,pad+440+bw+16,yy+21],fill=(40,30,24),outline=ACC,width=1); d.text((pad+448,yy+2),tag,font=F(13),fill=ACC)
            yy+=30
        y+=bh+16
    if D.get('losers'):
        ls=D['losers']
        d.text((pad,y),"■ 급락 상위 종목 (오늘 등락률)",font=F(15),fill=ACC); y+=26
        bh=14+len(ls)*30; d.rectangle([pad,y,W-pad,y+bh],fill=(34,22,24),outline=(90,55,60),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=RED)
        yy=y+10
        for item in ls:
            nm=item[0]; pct=item[1]; memo=item[2] if len(item)>2 else ""
            d.text((pad+16,yy),nm,font=F(16),fill=(255,255,255))
            d.text((pad+300,yy),f"▼ {pct:.2f}%",font=F(16),fill=RED)
            if memo: d.text((pad+440,yy+2),memo,font=F(13),fill=SUB)
            yy+=30
        y+=bh+16
    if vt:
        d.text((pad,y),"■ 거래대금 상위 (오늘 자금 쏠린 주도주)",font=F(15),fill=ACC); y+=26
        bh=14+len(vt)*30; d.rectangle([pad,y,W-pad,y+bh],fill=(24,27,34),outline=(46,50,60),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=BLUE)
        yy=y+10
        for i,(nm,val) in enumerate(vt):
            d.text((pad+16,yy),f"{i+1}. {nm}",font=F(16),fill=(255,255,255)); d.text((pad+360,yy),f"거래대금 {val}",font=F(15),fill=BLUE); yy+=30
        y+=bh+16
    if st:
        d.text((pad,y),"■ 주도 섹터 (업종 상승률)",font=F(15),fill=ACC); y+=26
        bh=14+len(st)*30; d.rectangle([pad,y,W-pad,y+bh],fill=(24,27,34),outline=(46,50,60),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=GREEN)
        mx=max((p for _,p in st),default=1) or 1; yy=y+10; bx0=pad+230; bxw=W-pad-16-bx0
        for nm,p in st:
            d.text((pad+16,yy),nm,font=F(15),fill=TXT)
            d.rectangle([bx0,yy+3,bx0+bxw*(p/mx),yy+17],fill=(40,90,64))
            d.text((bx0+8,yy+1),f"+{p:.2f}%",font=F(14),fill=GREEN); yy+=30
        y+=bh+16
    if tw:
        d.text((pad,y),"■ 추세 관심종목 (추세 유효 · 조정 시 재관심 · 참고)",font=F(15),fill=ACC); y+=24
        d.text((pad,y),"주도 섹터 대표주 · 조정에도 상승추세 살아있어 지지 확인 시 다시 볼 후보 (추천 아님)",font=F(12),fill=SUB); y+=24
        bh=14+len(tw)*32; d.rectangle([pad,y,W-pad,y+bh],fill=(20,26,32),outline=(52,72,96),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=BLUE)
        yy=y+10
        for item in tw:
            nm=item[0]; th=item[1] if len(item)>1 else ""; memo=item[2] if len(item)>2 else ""
            d.text((pad+16,yy),nm,font=F(16),fill=(255,255,255))
            if th:
                bw=d.textlength(th,font=F(12)); d.rectangle([pad+170,yy+1,pad+170+bw+14,yy+21],fill=(24,34,30),outline=GREEN,width=1); d.text((pad+177,yy+3),th,font=F(12),fill=(120,220,170))
            if memo: d.text((pad+300,yy+2),memo,font=F(13),fill=SUB)
            yy+=32
        y+=bh+16
    if D.get('note'):
        d.text((pad,y),"■ 추세매매 관점 (참고 · 추천 아님)",font=F(15),fill=ACC); y+=26
        bh=74; d.rectangle([pad,y,W-pad,y+bh],fill=(20,28,24),outline=(50,80,60),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=GREEN)
        nt=D['note']
        for i in range(3):
            seg=nt[i*52:(i+1)*52]
            if seg: d.text((pad+16,y+8+i*22),("→ "+seg) if i==0 else seg,font=F(13),fill=(150,220,170))
        y+=bh+14
    d.text((pad,y),"해설 · 거래대금 상위=오늘 자금 몰린 주도주 · 업종 상승률=오늘 강했던 섹터 · 급등일 추격은 리스크",font=F(13),fill=(120,165,210)); y+=22
    d.text((pad,y),f"출처: {D.get('sources','공개 뉴스')} · 매수·매도 추천 아님 · 결정·책임 본인",font=F(13),fill=(88,94,104)); y+=26
    return img.crop((0,0,W,y+6))

def main():
    p=os.path.join(HERE,"jq_close_stocks.json")
    if not os.path.exists(p):
        print("[오류] jq_close_stocks.json 없음"); return 2
    D=json.load(open(p,encoding="utf-8")); dt=D['date']
    img=render(D)
    out=os.path.join(HERE,"마감종목_카톡.png"); img.save(out)
    dd=os.path.join(HERE,"카드뉴스",dt); os.makedirs(dd,exist_ok=True)
    import shutil
    for t in [os.path.join(dd,"마감종목_카톡.png")]:
        try:
            if os.path.isdir(os.path.dirname(t)): shutil.copy(out,t)
        except Exception: pass
    print("[산출] 마감종목_카톡.png ·",dt)
    return 0
if __name__=="__main__": sys.exit(main())
