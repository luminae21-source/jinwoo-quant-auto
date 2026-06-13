#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""grade-cut 타이밍 자동 기록·패턴분석 (Track S 공격형 S+/S 전환 의사결정 지원).
매월 실행 → 등급분포·집중도·반도체%·피크플래그·MA200이격을 gradecut_log.csv에 누적 →
타이밍 신호(GREEN/YELLOW/RED) 산출. 패턴: '반도체 과열 + 피크 집중'일 땐 공격형 보류.
근거: 공격형 S+/S(10종·각10%)는 반도체 40%·피크명 30% 집중 → 과열구간 적용 = 최악 타이밍.
실행: python gradecut_tracker.py   |  입력: 최신 *_scores_latest.csv + value_peak_overlay.py
⚠️ 투자자문 아님. 의사결정 지원 기록."""
import sys
from datetime import datetime
from pathlib import Path
import pandas as pd, numpy as np
BASE=Path(__file__).parent.resolve(); sys.path.insert(0,str(BASE))
from value_peak_overlay import apply_overlay
SEMI={'반도체','2차전지'}  # 반도체 복합(경기민감 핵심)
CANDS=['v40_regime_scores_latest.csv','v39_pead_scores_latest.csv','v37_2_scores_latest.csv','v36_scores_latest.csv']

def pick():
    for c in CANDS:
        if (BASE/c).exists(): return BASE/c
    g=sorted(BASE.glob('*scores_latest.csv')); 
    if g: return g[-1]
    sys.exit('점수 CSV 없음')

def run():
    f=pick(); df=pd.read_csv(f,encoding='utf-8-sig')
    sc='체력_최종' if '체력_최종' in df.columns else [c for c in df.columns if '체력' in c][-1]
    ov=apply_overlay(df.copy(), code_col='코드', score_col=sc)
    gr=df['등급'] if '등급' in df.columns else df[[c for c in df.columns if '등급' in c][0]]
    sps=df[gr.isin(['S+','S'])]; spsa=df[gr.isin(['S+','S','A'])]
    nm={c:('등급' if c=='등급' else c) for c in df.columns}
    def semi_pct(sub): return round(100*sub['산업'].isin(SEMI).mean(),0) if len(sub) else 0
    peak_n=int((ov['트림권고'].astype(str).str.startswith('TRIM')).sum())
    watch_n=int((ov['트림권고'].astype(str).str.startswith('WATCH')).sum())
    # 반도체 평균 이격(과열 게이지)
    semi_gap=round(ov[df['산업'].isin(SEMI)]['이격_SMA%'].dropna().mean(),1) if len(ov[df['산업'].isin(SEMI)]) else np.nan
    row={'date':datetime.now().strftime('%Y-%m-%d'),'src':f.name,
         'n_SpS':len(sps),'wt_SpS_%':round(100/len(sps),1) if len(sps) else 0,
         'n_SpSA':len(spsa),'wt_SpSA_%':round(100/len(spsa),1) if len(spsa) else 0,
         'semi%_SpS':semi_pct(sps),'semi%_SpSA':semi_pct(spsa),
         'peak_TRIM':peak_n,'WATCH':watch_n,'semi_gap_SMA%':semi_gap}
    # 타이밍 신호: 반도체 과열·피크집중이면 공격형 보류
    score=0
    score += 2 if (semi_gap==semi_gap and semi_gap>50) else (1 if (semi_gap==semi_gap and semi_gap>30) else 0)
    score += 2 if peak_n>=2 else (1 if peak_n>=1 else 0)
    score += 1 if semi_pct(sps)>=40 else 0
    signal='RED 보류' if score>=4 else ('YELLOW 주의' if score>=2 else 'GREEN 적용가능')
    row['timing_score']=score; row['signal']=signal
    # 로그 누적
    log=BASE/'gradecut_log.csv'
    prev=pd.read_csv(log,encoding='utf-8-sig') if log.exists() else pd.DataFrame()
    out=pd.concat([prev,pd.DataFrame([row])],ignore_index=True)
    out.to_csv(log,index=False,encoding='utf-8-sig')
    # 출력
    print('='*72); print('grade-cut 타이밍 트래커 (%s, 입력 %s)'%(row['date'],f.name)); print('='*72)
    print('등급 S+/S: %d종(각 %.1f%%) · S+/S/A: %d종(각 %.1f%%)'%(row['n_SpS'],row['wt_SpS_%'],row['n_SpSA'],row['wt_SpSA_%']))
    print('반도체복합 비중 — S+/S공격형 %.0f%% · S+/S/A %.0f%%'%(row['semi%_SpS'],row['semi%_SpSA']))
    print('피크플래그 TRIM %d · WATCH %d · 반도체 평균 MA200이격 %s%%'%(peak_n,watch_n,semi_gap))
    print('-'*72)
    print('타이밍 신호: %s  (점수 %d/5)'%(signal,score))
    if score>=4: print('→ 공격형 S+/S 전환 보류 권장: 반도체 과열·피크 집중이 공격형 집중과 겹침(최악 타이밍).')
    elif score>=2: print('→ 주의: 일부 과열. 피크명 동시 풀비중 회피 + 이격 정상화 모니터.')
    else: print('→ 적용 가능 구간: 과열·피크 집중 해소. grade-cut(+9.7%p) 검토 OK.')
    print('-'*72)
    if len(out)>1:
        print('최근 기록(패턴):')
        print(out[['date','signal','semi_gap_SMA%','peak_TRIM','semi%_SpS']].tail(6).to_string(index=False))
    print('\n저장: gradecut_log.csv (%d행 누적)'%len(out))
if __name__=='__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass
    run()
