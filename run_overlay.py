#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_overlay.py — 독립 래퍼: 최신 점수 CSV에 밸류·피크 오버레이를 입혀 새 파일로 저장.
production(score_v40 등) 무수정. 매일 점수 산출 후 한 번 실행하면 됨.
실행: python run_overlay.py            (최신 *_scores_latest.csv 자동 탐지)
      python run_overlay.py v39_pead_scores_latest.csv   (파일 지정)
출력: overlay_scores_latest.csv  +  콘솔 요약(트림권고·순위변동)
⚠️ 투자자문 아님. 트림권고는 본인 판단용 신호."""
import sys
from pathlib import Path
import pandas as pd
BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))
from value_peak_overlay import apply_overlay, VAL_W, PEAK_PENALTY, PEAK_STRETCH

# 점수 파일 우선순위 (최신 엔진부터)
CANDIDATES = ['v40_regime_scores_latest.csv', 'v39_pead_scores_latest.csv',
              'v38_3_scores_latest.csv', 'v37_2_scores_latest.csv', 'v37_scores_latest.csv',
              'v36_scores_latest.csv']


def pick_file(arg=None):
    if arg:
        p = BASE / arg
        if p.exists():
            return p
        sys.exit('파일 없음: %s' % arg)
    for c in CANDIDATES:
        if (BASE / c).exists():
            return BASE / c
    # 아무 *_scores_latest.csv
    g = sorted(BASE.glob('*scores_latest.csv'))
    if g:
        return g[-1]
    sys.exit('점수 CSV(*_scores_latest.csv)를 찾을 수 없음 — 먼저 점수 산출 실행')


def pick_score_col(df):
    for c in ['체력_최종', '체력_v39', '체력_v37_2', '체력_v40']:
        if c in df.columns:
            return c
    cands = [c for c in df.columns if '체력' in c and df[c].dtype.kind in 'fi']
    if cands:
        return cands[-1]
    sys.exit('체력 점수 컬럼을 찾을 수 없음')


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    f = pick_file(arg)
    df = pd.read_csv(f, encoding='utf-8-sig')
    sc = pick_score_col(df)
    code_col = '코드' if '코드' in df.columns else None
    if code_col is None:
        sys.exit("'코드' 컬럼 필요")
    print('입력: %s  |  점수컬럼: %s  |  %d종목' % (f.name, sc, len(df)))
    out = apply_overlay(df, code_col=code_col, score_col=sc)

    # 오버레이 전/후 순위 비교
    out['순위_원본'] = out[sc].rank(ascending=False, method='min').astype(int)
    out['순위_조정'] = out['체력_밸류조정'].rank(ascending=False, method='min').astype(int)
    out['순위Δ'] = out['순위_원본'] - out['순위_조정']   # +면 상승, -면 하락
    out = out.sort_values('체력_밸류조정', ascending=False).reset_index(drop=True)

    cols = ['종목', sc, '밸류', '이격_SMA%', '피크플래그', '트림권고', '체력_밸류조정', '순위_원본', '순위_조정', '순위Δ']
    show = out[cols].copy()
    show[sc] = show[sc].round(2); show['체력_밸류조정'] = show['체력_밸류조정'].round(2)
    print('\n=== 밸류·피크 오버레이 적용 (VAL_W=%.1f, PEAK −%.1f @ +%d%% 과열) ===' % (VAL_W, PEAK_PENALTY, int(PEAK_STRETCH * 100)))
    print(show.to_string(index=False))

    trim = out[out['트림권고'] != '']
    print('\n■ 트림권고:', ', '.join('%s(%s)' % (r['종목'], r['트림권고']) for _, r in trim.iterrows()) if len(trim) else '없음')
    drop = out[out['순위Δ'] <= -2]
    if len(drop):
        print('■ 오버레이로 순위 2계단+ 하락:', ', '.join('%s(%+d)' % (r['종목'], r['순위Δ']) for _, r in drop.iterrows()))

    op = BASE / 'overlay_scores_latest.csv'
    out.to_csv(op, index=False, encoding='utf-8-sig')
    print('\n저장: %s' % op.name)


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    main()
