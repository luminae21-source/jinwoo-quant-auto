#!/usr/bin/env python3
"""
진우퀀트 v3.7 vs v3.6 attribution 분석

목적: 백테스트 결과 JSON을 읽어서 v3.6 - v3.7 차이의 원인을 종목·시점별로 분해.

답할 질문:
  1. v3.7이 v3.6보다 가장 많이 뒤처진 시점은 언제? 그때 빠진 종목은?
  2. v3.7이 v3.6을 이긴 시점은 언제? 어떤 종목이 도왔나?
  3. 4년 누적으로 v3.6에 있었지만 v3.7에서 빠진 종목 TOP — 얼마나 손해?
  4. v3.7의 BAB 페널티가 실제로 어떤 종목에 어떻게 작용했나?
  5. 결론: v3.7 → production 갈지, BAB 임계값 조정해서 v3.7.1 만들지

실행:
  python3 analyze_v37_attribution.py
  python3 analyze_v37_attribution.py --json backtest_v37_vs_v36_YYYYMMDD_HHMM.json
"""

import sys
import argparse
import json
import glob
from datetime import datetime
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).parent.resolve()


def find_latest_backtest():
    """가장 최근 backtest JSON 자동 검색"""
    candidates = sorted(BASE.glob('backtest_v37_vs_v36_*.json'))
    if not candidates:
        return None
    return candidates[-1]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--json', type=str, default=None,
                   help='백테스트 JSON 경로 (없으면 자동 검색)')
    p.add_argument('--top-n', type=int, default=10,
                   help='출력할 TOP N 개수')
    p.add_argument('--save-html', action='store_true',
                   help='HTML 리포트 저장')
    return p.parse_args()


# ============================================
# 분석 함수
# ============================================
def cumulative_curve(monthly_rets):
    """월간 수익률 → 누적 곡선 (시작=1.0)"""
    curve = [1.0]
    for r in monthly_rets:
        curve.append(curve[-1] * (1 + r / 100.0))
    return curve


def find_worst_best_months(history, top_n=5):
    """v3.7 - v3.6 차이 가장 큰 / 작은 시점"""
    diffs = []
    for h in history:
        d = h['r_v37_%'] - h['r_v36_%']
        diffs.append((h['date'], d, h))
    worst = sorted(diffs, key=lambda x: x[1])[:top_n]   # v3.7이 뒤처진
    best = sorted(diffs, key=lambda x: -x[1])[:top_n]    # v3.7이 앞선
    return worst, best


def stock_contribution_summary(history):
    """
    각 종목의 v3.6·v3.7 누적 기여도(contrib_pct 합).
    포함 횟수, 평균 수익률, 총 기여 정리.
    """
    v36_stats = defaultdict(lambda: {'count': 0, 'sum_contrib': 0.0, 'sum_r': 0.0})
    v37_stats = defaultdict(lambda: {'count': 0, 'sum_contrib': 0.0, 'sum_r': 0.0})

    for h in history:
        for d in h.get('detail_v36', []):
            v36_stats[d['name']]['count'] += 1
            v36_stats[d['name']]['sum_contrib'] += d['contrib_pct']
            v36_stats[d['name']]['sum_r'] += d['r_pct']
        for d in h.get('detail_v37', []):
            v37_stats[d['name']]['count'] += 1
            v37_stats[d['name']]['sum_contrib'] += d['contrib_pct']
            v37_stats[d['name']]['sum_r'] += d['r_pct']

    all_names = set(v36_stats) | set(v37_stats)
    table = []
    for name in all_names:
        v36 = v36_stats.get(name, {'count': 0, 'sum_contrib': 0.0, 'sum_r': 0.0})
        v37 = v37_stats.get(name, {'count': 0, 'sum_contrib': 0.0, 'sum_r': 0.0})
        table.append({
            '종목': name,
            'v36_포함월': v36['count'],
            'v37_포함월': v37['count'],
            'Δ_포함월': v37['count'] - v36['count'],
            'v36_누적기여_%p': round(v36['sum_contrib'], 2),
            'v37_누적기여_%p': round(v37['sum_contrib'], 2),
            'Δ_기여_%p': round(v37['sum_contrib'] - v36['sum_contrib'], 2),
        })
    return sorted(table, key=lambda x: x['Δ_기여_%p'])


def diff_pick_stocks(history):
    """각 시점에서 v36에만 있던 / v37에만 있던 종목 빈도"""
    only_v36_freq = defaultdict(int)
    only_v37_freq = defaultdict(int)
    for h in history:
        for name in h.get('only_v36', []):
            only_v36_freq[name] += 1
        for name in h.get('only_v37', []):
            only_v37_freq[name] += 1
    return dict(only_v36_freq), dict(only_v37_freq)


# ============================================
# 출력
# ============================================
def print_report(report, args):
    cfg = report.get('config', {})
    metrics = report.get('metrics', {})
    history = report.get('history', [])
    if not history:
        print("❌ history 데이터 없음 — 백테스트 다시 실행 필요")
        return

    print("=" * 78)
    print(f"진우퀀트 v3.7 vs v3.6 Attribution 분석")
    print(f"백테스트: {cfg.get('years','?')}년 · {cfg.get('rebalance','?')} 리밸런스 · "
          f"등급 {cfg.get('top_grades','?')}")
    print(f"분석 시점: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 78)

    # 1. 메트릭 재출력
    print(f"\n📊 핵심 지표 요약")
    print(f"  연환산:  v36 {metrics['v36']['연환산']:>6.2f}%  vs  v37 {metrics['v37']['연환산']:>6.2f}%  "
          f"(차이 {metrics['v37']['연환산'] - metrics['v36']['연환산']:+.2f}%p)")
    print(f"  Sharpe: v36 {metrics['v36']['Sharpe']:>6.2f}   vs  v37 {metrics['v37']['Sharpe']:>6.2f}   "
          f"(차이 {metrics['v37']['Sharpe'] - metrics['v36']['Sharpe']:+.2f})")
    print(f"  MDD:    v36 {metrics['v36']['MDD']:>6.2f}%  vs  v37 {metrics['v37']['MDD']:>6.2f}%  "
          f"(차이 {metrics['v37']['MDD'] - metrics['v36']['MDD']:+.2f}%p)")
    print(f"  변동성: v36 {metrics['v36']['변동성']:>6.2f}%  vs  v37 {metrics['v37']['변동성']:>6.2f}%  "
          f"(차이 {metrics['v37']['변동성'] - metrics['v36']['변동성']:+.2f}%p)")

    # 2. 누적 곡선 일부 print
    rets_v36 = [h['r_v36_%'] for h in history]
    rets_v37 = [h['r_v37_%'] for h in history]
    curve_v36 = cumulative_curve(rets_v36)
    curve_v37 = cumulative_curve(rets_v37)

    print(f"\n📈 누적 자본 곡선 (1.0 시작, 분기 sample)")
    print(f"  {'시점':<12} {'v36':>8} {'v37':>8} {'gap':>7}")
    sample = max(1, len(history) // 12)
    for i in range(0, len(history), sample):
        d = history[i]['date']
        c36 = curve_v36[i+1]
        c37 = curve_v37[i+1]
        gap = (c37 / c36 - 1) * 100
        print(f"  {d:<12} {c36:>8.3f} {c37:>8.3f} {gap:>+6.2f}%")
    # 마지막
    d = history[-1]['date']
    print(f"  {d:<12} {curve_v36[-1]:>8.3f} {curve_v37[-1]:>8.3f} "
          f"{(curve_v37[-1]/curve_v36[-1]-1)*100:>+6.2f}%  ← 최종")

    # 3. 최악·최선 시점
    worst, best = find_worst_best_months(history, top_n=args.top_n)
    print(f"\n🔻 v3.7이 v3.6보다 가장 뒤처진 월 TOP {args.top_n}")
    print(f"  {'시점':<12} {'v36':>6} {'v37':>6} {'gap':>6} | 빠진 종목 (v37에만)")
    for d, gap, h in worst:
        only36 = ', '.join(h.get('only_v36', [])) or '-'
        only37 = ', '.join(h.get('only_v37', [])) or '-'
        print(f"  {d:<12} {h['r_v36_%']:>+5.2f}% {h['r_v37_%']:>+5.2f}% {gap:>+5.2f}%p"
              f" | v36-only: {only36}  /  v37-only: {only37}")

    print(f"\n🔺 v3.7이 v3.6보다 가장 앞선 월 TOP {args.top_n}")
    print(f"  {'시점':<12} {'v36':>6} {'v37':>6} {'gap':>6} | 차이 종목")
    for d, gap, h in best:
        only36 = ', '.join(h.get('only_v36', [])) or '-'
        only37 = ', '.join(h.get('only_v37', [])) or '-'
        print(f"  {d:<12} {h['r_v36_%']:>+5.2f}% {h['r_v37_%']:>+5.2f}% {gap:>+5.2f}%p"
              f" | v36-only: {only36}  /  v37-only: {only37}")

    # 4. 종목별 기여도
    table = stock_contribution_summary(history)
    print(f"\n📉 v3.7에서 영향 부정적인 종목 TOP {args.top_n} (Δ_기여 음수)")
    print(f"  {'종목':<14} {'v36월':>6} {'v37월':>6} {'Δ월':>4} {'v36기여':>10} {'v37기여':>10} {'Δ기여':>8}")
    for r in table[:args.top_n]:
        if r['Δ_기여_%p'] >= 0: break
        print(f"  {r['종목']:<14} {r['v36_포함월']:>6d} {r['v37_포함월']:>6d} "
              f"{r['Δ_포함월']:>+4d} {r['v36_누적기여_%p']:>+9.2f}%p {r['v37_누적기여_%p']:>+9.2f}%p "
              f"{r['Δ_기여_%p']:>+7.2f}%p")

    print(f"\n📈 v3.7에서 영향 긍정적인 종목 TOP {args.top_n} (Δ_기여 양수)")
    print(f"  {'종목':<14} {'v36월':>6} {'v37월':>6} {'Δ월':>4} {'v36기여':>10} {'v37기여':>10} {'Δ기여':>8}")
    for r in reversed(table[-args.top_n:]):
        if r['Δ_기여_%p'] <= 0: break
        print(f"  {r['종목']:<14} {r['v36_포함월']:>6d} {r['v37_포함월']:>6d} "
              f"{r['Δ_포함월']:>+4d} {r['v36_누적기여_%p']:>+9.2f}%p {r['v37_누적기여_%p']:>+9.2f}%p "
              f"{r['Δ_기여_%p']:>+7.2f}%p")

    # 5. 등급에서 빠진/추가된 빈도
    only36, only37 = diff_pick_stocks(history)
    if only36:
        print(f"\n📋 v3.7에서 빠진 빈도 (v36엔 있는데 v37에선 없음)")
        for name, n in sorted(only36.items(), key=lambda x: -x[1])[:args.top_n]:
            pct = n / len(history) * 100
            print(f"  {name:<14}  {n:>3}개월 / {len(history)}  ({pct:.1f}%)")
    if only37:
        print(f"\n📋 v3.7에서 추가된 빈도 (v36엔 없는데 v37엔 있음)")
        for name, n in sorted(only37.items(), key=lambda x: -x[1])[:args.top_n]:
            pct = n / len(history) * 100
            print(f"  {name:<14}  {n:>3}개월 / {len(history)}  ({pct:.1f}%)")

    # 6. 결론 가이드
    print(f"\n💡 해석 가이드")
    delta_ann = metrics['v37']['연환산'] - metrics['v36']['연환산']
    delta_sharpe = metrics['v37']['Sharpe'] - metrics['v36']['Sharpe']
    delta_mdd = metrics['v37']['MDD'] - metrics['v36']['MDD']

    if delta_ann < -1 and delta_sharpe > 0:
        verdict = "v3.7은 risk-adjusted 우위지만 절대 수익 손해. 강세장 가정이라면 v3.6 유지, 약세장 대비라면 v3.7."
    elif delta_ann > 0 and delta_sharpe > 0:
        verdict = "v3.7 모든 면에서 우위. production 전환 권장."
    elif delta_ann < 0 and delta_sharpe < 0:
        verdict = "v3.7이 모든 면에서 열등. 임계값 재조정 필요."
    else:
        verdict = "혼합 결과. 종목별 기여 분석 필요."
    print(f"  {verdict}")
    print(f"  Δ연환산 {delta_ann:+.2f}%p · ΔSharpe {delta_sharpe:+.2f} · ΔMDD {delta_mdd:+.2f}%p")

    return {
        'metrics': metrics,
        'top_negative': [r for r in table if r['Δ_기여_%p'] < 0][:args.top_n],
        'top_positive': list(reversed([r for r in table if r['Δ_기여_%p'] > 0][-args.top_n:])),
        'worst_months': [{'date': d, 'gap': g, 'only_v36': h['only_v36'],
                          'only_v37': h['only_v37']} for d, g, h in worst],
        'best_months':  [{'date': d, 'gap': g, 'only_v36': h['only_v36'],
                          'only_v37': h['only_v37']} for d, g, h in best],
        'pick_diff_frequency': {'only_v36': only36, 'only_v37': only37},
        'curve_v36_final': curve_v36[-1],
        'curve_v37_final': curve_v37[-1],
        'verdict': verdict,
    }


def save_html(summary, history, out_path):
    """간단한 HTML 리포트 (Chart.js 누적 곡선)"""
    cfg_dates = [h['date'] for h in history]
    rets_v36 = [h['r_v36_%'] for h in history]
    rets_v37 = [h['r_v37_%'] for h in history]
    curve_v36 = cumulative_curve(rets_v36)
    curve_v37 = cumulative_curve(rets_v37)
    rets_kospi = [h['r_kospi_%'] for h in history]
    curve_kospi = cumulative_curve(rets_kospi)

    html = f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<title>진우퀀트 v3.7 Attribution</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
  body {{ font-family: -apple-system, sans-serif; background:#0f1419; color:#e0e6ed;
         padding:16px; }}
  h1 {{ color:#4fc3f7; }}
  .verdict {{ background:#2c1f0f; border-left:3px solid #ffb74d; padding:10px;
              margin:14px 0; border-radius:4px; }}
  canvas {{ background:#1a232e; padding:8px; border-radius:8px; }}
</style></head><body>
<h1>v3.7 vs v3.6 누적 곡선</h1>
<div class="verdict">📌 {summary['verdict']}</div>
<canvas id="curve" width="900" height="380"></canvas>
<script>
new Chart(document.getElementById('curve'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(['시작'] + cfg_dates)},
    datasets: [
      {{ label:'v3.6', data:{json.dumps(curve_v36)}, borderColor:'#ffd54f', tension:0.1 }},
      {{ label:'v3.7', data:{json.dumps(curve_v37)}, borderColor:'#4fc3f7', tension:0.1 }},
      {{ label:'KOSPI', data:{json.dumps(curve_kospi)}, borderColor:'#9e9e9e', tension:0.1, borderDash:[5,5] }},
    ]
  }},
  options: {{
    responsive: false,
    plugins: {{ legend: {{ labels: {{ color:'#e0e6ed' }} }} }},
    scales: {{
      x: {{ ticks: {{ color:'#9e9e9e' }} }},
      y: {{ ticks: {{ color:'#9e9e9e' }} }}
    }}
  }}
}});
</script>
</body></html>"""
    out_path.write_text(html, encoding='utf-8')


# ============================================
# 메인
# ============================================
def main():
    args = parse_args()

    if args.json:
        json_path = Path(args.json)
    else:
        json_path = find_latest_backtest()

    if json_path is None or not json_path.exists():
        print("❌ backtest_v37_vs_v36_*.json 파일을 찾을 수 없음")
        print("   먼저 `python3 backtest_v37_vs_v36.py` 실행 필요")
        sys.exit(1)

    print(f"📂 분석 대상: {json_path.name}")
    report = json.loads(json_path.read_text(encoding='utf-8'))

    if not report.get('history') or 'detail_v36' not in (report['history'][0] if report['history'] else {}):
        print("⚠️ JSON에 detail 정보 없음 — backtest_v37_vs_v36.py 보강 버전으로 재실행 필요")
        sys.exit(1)

    summary = print_report(report, args)
    if summary is None:
        return

    # 저장
    out_json = BASE / f'attribution_v37_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                        encoding='utf-8')
    print(f"\n💾 분석 결과 저장: {out_json}")

    if args.save_html:
        out_html = BASE / f'attribution_v37_{datetime.now().strftime("%Y%m%d_%H%M")}.html'
        save_html(summary, report['history'], out_html)
        print(f"📊 HTML 차트:       {out_html}")


if __name__ == '__main__':
    main()
