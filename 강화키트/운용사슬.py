# -*- coding: utf-8 -*-
r"""운용사슬.py — 월간 운용 사슬이 어디까지 왔는지 잰다. (2026-08-20)

왜 만들었나
-----------
2026-08-20 발견: forward 원장이 2026-06 한 줄에서 멈춰 있었고 **아무도 몰랐다.**
진우는 "자동으로 도는 줄 알았다"고 했다. 실제로는 사슬 첫 칸(재무 수집)이 6월에서
끊겨서, 아래 단계는 돌려도 6월이 다시 나오는 상태였다.

교훈: **끊긴 것을 사람이 눈치채야 하는 구조는 언젠가 반드시 끊긴다.**
그래서 허브가 매번 이 사슬을 보여준다. 어디서 막혔는지 한 줄로.

사슬 (앞이 막히면 뒤는 못 간다)
    1 시총  → 2 재무  → 3 가격  → 4 스타일패널  → 5 신호·원장

    py 강화키트\운용사슬.py            # 콘솔 출력
    py 강화키트\운용사슬.py --selftest
"""
import os, io, csv, sys, argparse, html

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

# (라벨, 상대경로, 날짜컬럼, 막혔을 때 실행할 명령)
CHAIN = [
    ("① 시총",      "종목시총_30년.csv",                    "date",      "py fetch_mcap*.py"),
    ("② 재무",      "종목재무_KRX_KOSPI.csv",               "date",      "py fetch_fundamental_panel.py"),
    ("③ 가격",      "데이터수리/_월봉종가캐시_KOSPI_adj.csv", "ym",        "py 데이터수리\\collect_adjusted_monthly.py"),
    ("④ 스타일패널", "감사/미니샘플2/mini_style_panel.csv",    "ym",        "py build_style_panel.py --out 감사\\미니샘플2\\mini_style_panel.csv"),
    ("⑤ 신호·원장", "실전준비/forward_ledger.csv",           "date_asof", "py 실전준비\\forward_signal.py"),
]


def _maxmonth(path, col):
    """파일의 날짜컬럼 최대값을 YYYY-MM 으로. 없으면 None."""
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        return None
    best = ""
    try:
        with io.open(p, encoding="utf-8-sig", errors="replace", newline="") as f:
            rd = csv.DictReader(f)
            if not rd.fieldnames or col not in rd.fieldnames:
                return None
            for r in rd:
                v = (r.get(col) or "")[:7]
                if v > best:
                    best = v
    except Exception:
        return None
    return best or None


def status():
    """각 칸의 최신월. 앞 칸보다 뒤진 첫 칸이 병목."""
    rows = []
    for lab, path, col, cmd in CHAIN:
        rows.append(dict(라벨=lab, 경로=path, 최신월=_maxmonth(path, col), 명령=cmd))
    top = max((r["최신월"] for r in rows if r["최신월"]), default=None)
    block = None
    for r in rows:
        r["뒤짐"] = (top is not None and r["최신월"] is not None and r["최신월"] < top)
        r["없음"] = r["최신월"] is None
        if block is None and (r["뒤짐"] or r["없음"]):
            block = r["라벨"]
    for r in rows:
        r["병목"] = (r["라벨"] == block)
    return rows, top, block


def card_html():
    """허브에 넣을 카드 한 장."""
    rows, top, block = status()
    cells = ""
    for r in rows:
        m = r["최신월"] or "없음"
        if r["병목"]:
            mark, cls = "⛔", "background:rgba(224,163,46,.18)"
        elif r["뒤짐"] or r["없음"]:
            mark, cls = "·", "opacity:.75"
        else:
            mark, cls = "✓", ""
        cells += (f'<div class=lk style="{cls}">{html.escape(r["라벨"])}'
                  f'<span>{mark} {html.escape(m)}</span></div>')
    if block:
        cmd = next(r["명령"] for r in rows if r["병목"])
        note = (f'<div class=warn>⛔ <b>{html.escape(block)}</b> 에서 막혔다. '
                f'앞이 막히면 뒤는 돌려도 옛 달이 다시 나온다.<br>'
                f'→ <code>{html.escape(cmd)}</code> 부터.</div>')
    else:
        note = f'<div class=note>✅ 사슬 정상 · 전 단계 {html.escape(top or "?")}</div>'
    return ('<div class=card><h3>🔗 월간 운용 사슬</h3>'
            '<div class=note>앞 칸이 막히면 뒤 칸은 못 간다. 매달 이 줄이 같은 달을 가리켜야 정상.</div>'
            f'<div class=grid>{cells}</div>{note}</div>')


def selftest():
    ok = []
    def t(n, c): ok.append((n, bool(c)))
    rows, top, block = status()
    t("1 사슬 5칸", len(rows) == 5)
    t("2 최신월 형식", all(r["최신월"] is None or len(r["최신월"]) == 7 for r in rows))
    t("3 top 계산됨", top is None or len(top) == 7)
    t("4 병목은 최대 1개", sum(1 for r in rows if r["병목"]) <= 1)
    t("5 병목은 뒤졌거나 없는 칸", all((r["뒤짐"] or r["없음"]) for r in rows if r["병목"]))
    h = card_html()
    t("6 카드 생성", h.startswith("<div class=card>") and h.endswith("</div>"))
    t("7 카드에 5칸 전부", all(r["라벨"] in h for r in rows))
    t("8 명령이 전부 지정됨", all(r["명령"] for r in rows))
    t("9 없는파일 None", _maxmonth("존재하지않는파일.csv", "date") is None)
    t("10 없는컬럼 None", _maxmonth("종목시총_30년.csv", "없는컬럼") is None)
    n = sum(1 for _, c in ok if c)
    for name, c in ok:
        print(("  o " if c else "  X ") + name)
    print("자가검사 %d/%d %s" % (n, len(ok), "PASS" if n == len(ok) else "FAIL"))
    return 0 if n == len(ok) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest:
        sys.exit(selftest())
    rows, top, block = status()
    print("=" * 52)
    print(" 월간 운용 사슬")
    print("=" * 52)
    for r in rows:
        mark = "!!" if r["병목"] else ("  " if not (r["뒤짐"] or r["없음"]) else " ·")
        print("  %s %-14s %s" % (mark, r["라벨"], r["최신월"] or "없음"))
    print("-" * 52)
    if block:
        cmd = next(r["명령"] for r in rows if r["병목"])
        print("  막힌 곳: %s" % block)
        print("  다음: %s" % cmd)
    else:
        print("  사슬 정상 (전 단계 %s)" % top)
