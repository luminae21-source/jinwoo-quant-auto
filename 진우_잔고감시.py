# -*- coding: utf-8 -*-
r"""진우_잔고감시.py — 보유잔고 상시 감시 (G11 후보) · 2026-07-28 신설

[존재 이유] 리스크차단기는 '신규 주문'만 검사한다 — 이미 들고 있는 초과 보유는 영원히 안 잡힌다.
2026-07-19 잔고 기준 대덕전자 90%는 모든 한도(15%)의 6배인데 어떤 게이트도 경보하지 않았다.
이 스크립트는 my_holdings.csv를 매일 읽어 진우_통합한도.json 기준 위반을 경보한다.

[사용]  py 진우_잔고감시.py            → 콘솔 + 잔고감시_리포트.md 생성, 위반 시 exit 1
        py 진우_잔고감시.py --live     → pykrx로 현재가 조회 시도(실패 시 진입가 평가로 폴백)
[자동화] 일일 배치(일일_올인원 등) 앞단에 추가. exit 1이면 카톡 경보 연동 권장(jq_notify).
[의존성] 표준 라이브러리만 사용(pandas 불필요). --live만 pykrx 필요.
"""
import csv, json, os, sys, io, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def read_text_rows(path):
    """주석(#)·빈 줄 제거한 CSV 행 반환. utf-8-sig → cp949 폴백."""
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            with io.open(path, "r", encoding=enc) as f:
                rows = [r for r in csv.DictReader(
                    (ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")))]
            return rows
        except UnicodeDecodeError:
            continue
    raise IOError(f"인코딩 판별 실패: {path}")


def load_limits():
    p = os.path.join(BASE, "진우_통합한도.json")
    if not os.path.exists(p):
        print("⚠️ 진우_통합한도.json 없음 — 백서 6장 기본값으로 검사")
        return {"stock_cap_pct": 15.0, "max_positions": 15, "sector_cap_pct": 35.0}
    j = json.load(io.open(p, encoding="utf-8"))
    body = j.get("본체_월간포트", {})
    rg = j.get("집행_riskguard", {})
    return {
        "stock_cap_pct": body.get("stock_cap_pct", rg.get("max_weight_pct", 15.0)),
        "sector_cap_pct": body.get("sector_cap_pct", 35.0),
        "max_positions": body.get("max_positions", rg.get("max_positions", 15)),
    }


def get_live_price(code):
    try:
        from pykrx import stock
        today = datetime.date.today()
        for back in range(7):
            d = (today - datetime.timedelta(days=back)).strftime("%Y%m%d")
            df = stock.get_market_ohlcv(d, d, code)
            if df is not None and len(df):
                return float(df["종가"].iloc[-1])
    except Exception:
        return None
    return None


def main(live=False):
    lim = load_limits()
    hp = os.path.join(BASE, "my_holdings.csv")
    if not os.path.exists(hp):
        print("my_holdings.csv 없음 — 보유 0으로 간주(검사 통과)")
        return 0
    rows = read_text_rows(hp)

    pos = []
    for r in rows:
        code = (r.get("code") or "").strip().zfill(6)
        if not code or code == "000000":
            continue
        qty = float(r.get("qty") or 0)
        entry = float(r.get("entry_price") or 0)
        price, src = entry, "진입가"
        if live:
            lp = get_live_price(code)
            if lp:
                price, src = lp, "현재가"
        pos.append(dict(code=code, name=(r.get("name") or code).strip(),
                        track=(r.get("track") or "본체").strip() or "본체",
                        qty=qty, entry=entry, price=price, src=src,
                        value=qty * price,
                        stop=(r.get("stop") or "").strip(),
                        entry_date=(r.get("entry_date") or "").strip(),
                        credit=(r.get("credit") or "").strip()))

    # ── 예외 자산 분리 (2026-07-30) — 시스템 한도 계산에서 제외
    sys_pos = [p for p in pos if p["track"] != "예외"]
    exc_pos = [p for p in pos if p["track"] == "예외"]
    total_all = sum(p["value"] for p in pos)
    total = sum(p["value"] for p in sys_pos)      # 한도 분모 = 시스템 자산만
    violations, warns = [], []

    for p in exc_pos:
        p["w"] = p["value"] / total_all * 100 if total_all else 0
    if total > 0:
        for p in sys_pos:
            p["w"] = p["value"] / total * 100
            cap = lim["stock_cap_pct"]
            if p["w"] > cap + 1e-9:
                # 한도까지 낮추기 위한 감축액: (v - cap*T)/(1 - cap)  [매도 후 총액도 줄어듦 반영]
                sell = (p["value"] - cap / 100 * total) / (1 - cap / 100)
                sell_sh = int(sell // p["price"]) if p["price"] > 0 else 0
                violations.append(
                    f"🔴 {p['name']}({p['code']}) 비중 {p['w']:.1f}% > 한도 {cap:.0f}% "
                    f"— 감축 필요 약 {sell:,.0f}원 ({sell_sh}주, {p['src']} 평가)")
    if len(sys_pos) > lim["max_positions"]:
        violations.append(f"🔴 시스템 보유 {len(sys_pos)}종 > 최대 {lim['max_positions']}종")
    for p in sys_pos:
        if not p["stop"]:
            warns.append(f"🟡 {p['name']}: stop 미기재 → heat(총 리스크) 계산 불가")
        if not p["entry_date"]:
            warns.append(f"🟡 {p['name']}: entry_date 미기재 → 시간손절(20일) 판정 불가")
        if p["credit"].lower() in ("y", "1", "true", "신용"):
            warns.append(f"🟡 {p['name']}: 신용 보유 — 별도 점검")

    # ── 출력 ──
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# 잔고 감시 리포트 — {now}", ""]
    lines.append(f"평가 기준: {'현재가(pykrx)' if live else '진입가(오프라인)'}")
    lines.append(f"총 평가액 {total_all:,.0f}원 = 시스템 {total:,.0f}원({len(sys_pos)}종) + 예외 {total_all-total:,.0f}원({len(exc_pos)}종)")
    lines.append(f"한도: 종목 {lim['stock_cap_pct']:.0f}% · 최대 {lim['max_positions']}종 (진우_통합한도.json)")
    lines.append("")
    lines.append("## 시스템 자산 (한도 적용)")
    lines.append("")
    if sys_pos:
        lines.append("| 종목 | 수량 | 평가액 | 시스템내 비중 | 한도 대비 |")
        lines.append("|---|---:|---:|---:|---|")
        for p in sorted(sys_pos, key=lambda x: -x["value"]):
            flag = "🔴 초과" if p.get("w", 0) > lim["stock_cap_pct"] else "✅"
            lines.append(f"| {p['name']}({p['code']}) | {p['qty']:.0f} | {p['value']:,.0f} | {p.get('w',0):.1f}% | {flag} |")
    else:
        lines.append("_(없음 — 시스템 운용 미개시)_")
    if exc_pos:
        lines.append("")
        lines.append("## ⚪ 예외 자산 (한도 미적용 · 성과 분리 기록)")
        lines.append("")
        lines.append("| 종목 | 수량 | 평가액 | 계좌내 비중 | 상태 |")
        lines.append("|---|---:|---:|---:|---|")
        for p in sorted(exc_pos, key=lambda x: -x["value"]):
            lines.append(f"| {p['name']}({p['code']}) | {p['qty']:.0f} | {p['value']:,.0f} | {p.get('w',0):.1f}% | 동결 (추가매수 금지) |")
        lines.append("")
        lines.append("> 해제 조건: ①2026-12-31 F게이트 ②시스템 사다리 2단계 도달 ③청산규율 3단계(🔴) 발생")
        lines.append("> 청산규율 분산 경보는 계속 적용된다 — `py 청산규율_알림.py` 로 확인")
    lines.append("")
    if violations:
        lines.append("## 🔴 한도 위반 (조치 필요)")
        lines += [f"- {v}" for v in violations]
    else:
        lines.append("## ✅ 한도 위반 없음")
    if warns:
        lines.append("")
        lines.append("## 🟡 경고 (데이터 보강 필요)")
        lines += [f"- {w}" for w in warns]
    lines.append("")
    lines.append("> 규칙: 위반은 '언젠가'가 아니라 '계획을 세워 분할로' 해소한다 — 수익엔진_설계 §5 참조.")

    report = "\n".join(lines)
    print(report)
    with io.open(os.path.join(BASE, "잔고감시_리포트.md"), "w", encoding="utf-8") as f:
        f.write(report + "\n")
    print("\n저장: 잔고감시_리포트.md")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main(live="--live" in sys.argv))
