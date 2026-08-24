# -*- coding: utf-8 -*-
r"""서킷브레이커_점검.py — 시스템 사망 판정 (사전등록 2026-08-22 확정 문턱)

가상매매_원장.csv의 청산 완료 건(시간순)으로 상태를 계산해 서킷상태.json에 기록한다.
가상매매.py가 신규 진입 전에 이 파일을 읽어 '정지'면 코드가 진입을 거부한다.

  py 서킷브레이커_점검.py            → 상태 계산·기록·요약 출력
  py 서킷브레이커_점검.py --selftest → 합성 시계열 3종으로 발동 검증 (원장·상태파일 건드리지 않음)

문턱(사전등록 §2 — 사후 완화 금지):
  경보  : 롤링30건 평균 < -3.4%
  정지  : 롤링30건 평균 < -9.0%  또는 연패 >= 22건
  계좌  : 평가포함자산 고점比 -15%
"""
import os, sys, csv, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
TH_WARN = -0.034
TH_HALT = -0.090
TH_STREAK = 22
TH_ACCT = -0.15
N_ROLL = 30


def read_rows(path):
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def judge(returns, acct_dd):
    """returns: 청산 완료 건 수익률(소수, 시간순) · acct_dd: 계좌 고점比 낙폭(소수, 음수)."""
    out = dict(상태="정상", 사유=[], 표본=len(returns),
               롤링30=None, 연패=0, 계좌낙폭=round(acct_dd, 4))
    # 연패 (현재 진행 중인 연속 손실)
    streak = 0
    for r in reversed(returns):
        if r < 0: streak += 1
        else: break
    out["연패"] = streak
    # 롤링 30
    if len(returns) >= N_ROLL:
        rm = sum(returns[-N_ROLL:]) / N_ROLL
        out["롤링30"] = round(rm, 4)
        if rm < TH_HALT:
            out["상태"] = "정지"; out["사유"].append(f"롤링30 {rm*100:+.2f}% < {TH_HALT*100:.1f}%")
        elif rm < TH_WARN:
            out["상태"] = "경보"; out["사유"].append(f"롤링30 {rm*100:+.2f}% < {TH_WARN*100:.1f}%")
    else:
        out["사유"].append(f"롤링 판정 보류(표본 {len(returns)}<{N_ROLL})")
    if streak >= TH_STREAK:
        out["상태"] = "정지"; out["사유"].append(f"연패 {streak} ≥ {TH_STREAK}")
    if acct_dd <= TH_ACCT:
        out["상태"] = "정지"; out["사유"].append(f"계좌 고점比 {acct_dd*100:.1f}% ≤ {TH_ACCT*100:.0f}%")
    return out


def load_live():
    """원장에서 청산 완료 건 수익률(시간순), 자본곡선에서 계좌 낙폭."""
    rows = read_rows(os.path.join(HERE, "가상매매_원장.csv"))
    done = [r for r in rows if r.get("상태") == "청산"]
    def key(r): return (r.get("청산일") or r.get("갱신일") or r.get("진입일") or "")
    done.sort(key=key)
    rets = []
    for r in done:
        for col in ("수익률", "수익률pct", "총수익률"):
            v = r.get(col)
            if v not in (None, ""):
                try:
                    x = float(v)
                    rets.append(x/100 if abs(x) > 1.0 else x)  # % 표기/소수 표기 모두 수용
                except ValueError: pass
                break
    eq = read_rows(os.path.join(HERE, "가상매매_자본곡선.csv"))
    vals = []
    for r in eq:
        try: vals.append(float(r.get("평가포함자산", "") or 0))
        except ValueError: pass
    dd = 0.0
    if vals:
        peak = vals[0]
        for v in vals:
            peak = max(peak, v)
            dd = min(dd, v/peak - 1)
    return rets, dd


def selftest():
    ok = True
    def chk(name, res, want):
        nonlocal ok
        good = (res["상태"] == want)
        ok &= good
        print(f"  [{'PASS' if good else 'FAIL'}] {name}: 기대 {want} → 실제 {res['상태']} {res['사유']}")
    print("셀프테스트 — 합성 시계열 주입 (원장·상태파일 무변경)")
    # ① 정상: 30년식 평범한 흐름 (+2.4% 평균, 소폭 손실 섞임)
    normal = ([0.05, -0.03, 0.08, -0.02, 0.04] * 8)[:35]
    chk("정상 시나리오", judge(normal, -0.03), "정상")
    # ② 경보: 롤링30 = -5%대
    warn = [ -0.05 ]*18 + [ 0.01 ]*12          # 평균 -2.6%... 조정
    warn = [ -0.08 ]*18 + [ 0.005 ]*12         # (-.08*18+.005*12)/30 = -4.6%
    chk("경보 시나리오(롤링30 -4.6%)", judge(warn, -0.05), "경보")
    # ③ 정지A: 롤링30 -10%
    haltA = [ -0.10 ]*30
    chk("정지 시나리오A(롤링30 -10%)", judge(haltA, -0.05), "정지")
    # ④ 정지B: 연패 22
    haltB = [ 0.03 ]*20 + [ -0.01 ]*22
    chk("정지 시나리오B(연패 22)", judge(haltB, -0.05), "정지")
    # ⑤ 정지C: 계좌 -16%
    chk("정지 시나리오C(계좌 -16%)", judge(normal, -0.16), "정지")
    # ⑥ 표본 부족: 롤링 보류, 연패·계좌만
    chk("표본부족(5건, 이상 없음)", judge([0.02, -0.01, 0.03, 0.01, -0.02], -0.02), "정상")
    print("셀프테스트", "전부 통과 ✅" if ok else "실패 ❌")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    if a.selftest:
        sys.exit(selftest())
    rets, dd = load_live()
    res = judge(rets, dd)
    res["문턱"] = dict(경보=TH_WARN, 정지=TH_HALT, 연패=TH_STREAK, 계좌=TH_ACCT)
    with open(os.path.join(HERE, "서킷상태.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    icon = {"정상": "✅", "경보": "🟡", "정지": "🔴"}[res["상태"]]
    print(f"서킷브레이커: {icon} {res['상태']} · 청산표본 {res['표본']}건 · "
          f"롤링30 {('%+.2f%%' % (res['롤링30']*100)) if res['롤링30'] is not None else '보류'} · "
          f"연패 {res['연패']} · 계좌낙폭 {res['계좌낙폭']*100:.1f}%")
    if res["사유"]: print("  " + " / ".join(res["사유"]))
    print("저장: 서킷상태.json")


if __name__ == "__main__":
    main()
