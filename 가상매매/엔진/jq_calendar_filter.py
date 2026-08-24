# -*- coding: utf-8 -*-
r"""jq_calendar_filter.py — 하순 신규진입 보류 필터

★ 2026-07-14 갱신 — 30년 패널로 재검정 완료. 근거가 완전히 바뀌었다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
규칙 (한 줄)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    하순(월말 기준 역순 −9 ~ −5 거래일)에는 **신규 진입을 하지 않는다.**
    기존 보유·청산은 건드리지 않는다. 진입 시점만 −4일 이후로 미룬다.

    · 매매를 추가하는 게 아니다 → **비용 0**
    · 코스닥 **소·중형주**에 적용. **대형주엔 쓰지 않는다.**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
근거 — 30년 패널 (검정_30년_패널.py · 2026-07-14)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
데이터: 1996~2026 · **5,051종목 · 상폐 종목 포함**(생존편향 차단) · 1,470만 행
창(−9~−5): Lakonishok & Smidt (1988) 정의. **내가 고른 게 아니다.**

사전등록 관문 (30년_재검정_사전등록.md · 데이터 보기 전 확정)

  세그먼트   (A)IN 1996~2012   (B)이상치제거   (C)OOS 2013~2026   Bonferroni×12
  ────────────────────────────────────────────────────────────────────────
  시총 소      p=0.0046 ✅      p=0.0029 ✅      p=0.0002 ✅       0.0024 ✅
  시총 중      p=0.0121 ✅      p=0.0013 ✅      p=0.0041 ✅       0.049  ✅
  시총 대      p=0.0332         p=0.0172         p=0.1211 ❌       —      기각
  전체        p=0.0007 ✅      p=0.0005 ✅      p=0.0141 ✅       0.169

  → **소 > 중 > 대 순서가 30년 내내 유지된다.**
    차익거래는 유동성 큰 대형주부터 먹는다. 소형주엔 남아있다.
    경제 논리와 데이터가 같은 방향을 가리킨다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
같이 죽은 것들 — 왜 이것만 남았나
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ① 할로윈       기각 — 89개월 중 6개만 빼면 소멸(이상치 의존)
  ② 월초강세 TOM  기각 — **IN에서 t=5.49, p=0.0000** 이었는데 OOS에서 전멸
  ④ 월중 저점→고점 기각 — 전 세그먼트 OOS 실패

  ②가 교훈이다. IN에서 t=5.49면 누구라도 믿는다. OOS를 미리 봉인해두지
  않았다면 오늘 잘못된 규칙을 하나 더 얻었을 것이다.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 타이밍 규칙으로 쓰지 말 것 — (D) 비용 관문에서 기각
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"하순엔 전량 현금, 나머지는 보유" = 연 24회 왕복 매매.
한국은 매도세 0.18% + 수수료 + 슬리피지 → 왕복 0.45%가 현실.

  OOS 2013~2026 · 시총 소
    buy&hold                CAGR 11.81%  Sharpe 0.57  MDD −40.3%
    하순회피 (왕복 0.45%)     CAGR 11.89%  Sharpe 0.64  MDD −27.3%   ← +0.09%p (무승부)
    하순회피 (왕복 0.70%)     CAGR  8.47%  Sharpe 0.43  MDD −27.4%   ← 패배

  → **CAGR는 무승부. 비용이 우위를 다 먹는다.**
    (MDD가 좋아지지만 시간의 25%를 시장 밖에 있으니 일부는 기계적이다.)

  **진입 필터는 다르다.** 매매를 추가하지 않고 시점만 옮긴다 → 비용 0 → 채택.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
아직 모르는 것 — 규칙에 넣지 않았다
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"하순 눌림에서 사면 오히려 낫다"는 신호가 있다(20일 보유 시 +0.184%p).
**그러나 p=0.37로 유의하지 않다.** 유의하지 않은 걸 규칙으로 만들면
그게 바로 data snooping이다. **넣지 않는다.** 추가 검정 후 재고.


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
언젠가 죽을 수 있다
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
이건 1988년에 **공표된** 패턴이다. 대형주에선 이미 소진됐다(OOS p=0.1211).
소형주에서 38년간 살아남은 건 오히려 놀라운 일이고, 언제든 같은 일이
일어날 수 있다. **forward 추적 필수.** 24개월마다 재판정한다.

사용:
    from jq_calendar_filter import is_late_month, entry_blocked, why
    if entry_blocked(asof, trading_days, tier="소"):   # 신규 진입 보류
        ...
자가점검:  py jq_calendar_filter.py
"""
import datetime as _dt

# ── 사전등록 파라미터 — 논문(Lakonishok & Smidt 1988) 정의. 튜닝 금지 ──────
LATE_START = -9   # 월말 역순 (마지막 거래일 = -1)
LATE_END = -5
ENABLED = True    # 기본 ON (비용 0). 끄려면 엔진 --no-late-filter

# 적용 대상 — 대형주는 OOS에서 기각(p=0.1211)됐다
APPLY_TIERS = ("소", "중")
SKIP_TIERS = ("대",)


def rdom_map(trading_days):
    """거래일 리스트 → {날짜: 월말역순인덱스}. 마지막 거래일 = -1. (완결월만)"""
    days = sorted({_as_date(d) for d in trading_days})
    by_m = {}
    for d in days:
        by_m.setdefault((d.year, d.month), []).append(d)
    out = {}
    for (y, m), ds in by_m.items():
        n = len(ds)
        for i, d in enumerate(ds):
            out[d] = (i + 1) - n - 1
    return out


def _as_date(d):
    if isinstance(d, _dt.datetime):
        return d.date()
    if isinstance(d, _dt.date):
        return d
    return _dt.date.fromisoformat(str(d)[:10])


def _month_bdays(y, m):
    """그 달의 평일(월~금) 전체. 공휴일은 모른다 → 상한 추정치."""
    import calendar
    n = calendar.monthrange(y, m)[1]
    return [_dt.date(y, m, d) for d in range(1, n + 1)
            if _dt.date(y, m, d).weekday() < 5]


def project_rdom(day, trading_days):
    """진행 중인 달도 판정한다 — 남은 평일을 세어 월말을 **투영**한다.

    실전에서 '오늘이 하순인가'를 물으면 그 달은 아직 안 끝났다. 월말을 모르면
    역순 인덱스를 못 만든다 → 백테스트에서만 도는 필터가 된다.
    (2026-07-13 발견: 매일 '판정불가'만 뱉고 한 번도 안 걸렸다.)

    ⚠️ 한계: 한국 공휴일 데이터가 없다. 남은 기간에 공휴일이 있으면 n̂이
       과대추정되고 rd가 실제보다 더 음수(=월초 쪽)로 치우친다.
       → 하순 진입을 **놓칠 수는 있어도, 하순이 아닌데 막지는 않는다**(보수적).
    """
    day = _as_date(day)
    obs = sorted({_as_date(d) for d in trading_days})
    same = [d for d in obs if (d.year, d.month) == (day.year, day.month)]
    if not same:
        return None, False

    last_obs = max(obs)
    month_last_bday = _month_bdays(day.year, day.month)[-1]
    finished = (last_obs > month_last_bday) or any(
        (d.year, d.month) != (day.year, day.month) and d > day for d in obs)

    if finished:
        n = len(same)
        projected = False
    else:
        remain = [d for d in _month_bdays(day.year, day.month) if d > max(same)]
        n = len(same) + len(remain)
        projected = True

    if day in same:
        t = same.index(day) + 1
    else:
        before = [d for d in _month_bdays(day.year, day.month) if d <= day]
        t = len(before)
        if day.weekday() >= 5:
            return None, projected
    if t <= 0 or n <= 0:
        return None, projected
    return t - n - 1, projected


def is_late_month(day, trading_days):
    """day 가 하순(−9~−5 거래일)인가. 진행 중인 달도 투영해서 판정."""
    rd, _ = project_rdom(day, trading_days)
    if rd is None:
        return False
    return LATE_START <= rd <= LATE_END


def entry_blocked(day, trading_days, enabled=None, tier=None):
    """신규 진입을 보류해야 하는가.

    tier: '소'/'중'/'대' (시총 3분위). '대'면 적용하지 않는다 —
          대형주는 OOS에서 기각됐다(p=0.1211). 차익거래로 소진된 것으로 보인다.
          None이면 시총 무관하게 적용(보수적).
    """
    on = ENABLED if enabled is None else enabled
    if not on:
        return False
    if tier in SKIP_TIERS:
        return False
    return is_late_month(day, trading_days)


def rdom_of(day, trading_days):
    rd, _ = project_rdom(day, trading_days)
    return rd


def next_late_window(day, trading_days):
    """이번 달 하순 구간의 (시작일, 종료일). 판정 불가면 None."""
    day = _as_date(day)
    cand = [d for d in _month_bdays(day.year, day.month)
            if is_late_month(d, trading_days)]
    return (min(cand), max(cand)) if cand else None


def why(day, trading_days, tier=None):
    """사람이 읽는 사유 문자열."""
    rd, proj = project_rdom(day, trading_days)
    if rd is None:
        return "월중 위치 판정불가(데이터 없음 또는 주말)"
    tag = " (투영: 공휴일 미반영 ±1일)" if proj else ""
    win = next_late_window(day, trading_days)
    ws = f" · 이번 달 하순 {win[0]}~{win[1]}" if win else ""

    if tier in SKIP_TIERS:
        return (f"대형주 — 필터 미적용 ({rd}거래일). "
                f"대형주는 30년 OOS에서 기각(p=0.1211). 차익거래로 소진된 것으로 보임.")

    if LATE_START <= rd <= LATE_END:
        return (f"하순({rd}거래일, 월말 역순){tag} — 신규진입 보류. "
                f"근거: 30년패널(5,051종목·상폐포함) OOS p=0.0002(소형)/0.0041(중형), "
                f"Bonferroni×12 통과. 진입은 −4일 이후로. "
                f"⚠️ 기존 보유·청산은 무관. 타이밍 규칙(전량 현금)은 비용에 패배 → 쓰지 말 것.")
    return f"진입 가능 구간({rd}거래일){tag}{ws}"


# ---------------------------------------------------------------------------
def _self_test():
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1
        ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    days = [_dt.date(2026, 6, d) for d in range(1, 31)
            if _dt.date(2026, 6, d).weekday() < 5]
    rm = rdom_map(days)
    last = max(days)
    chk("마지막 거래일 = -1", rm[last] == -1)
    chk("첫 거래일 rd = -(n)", rm[min(days)] == -len(days))
    late = [d for d in days if is_late_month(d, days)]
    chk("하순 구간 = 정확히 5일", len(late) == 5)
    chk("하순 = 월말 -9~-5", all(-9 <= rm[d] <= -5 for d in late))
    chk("월말 -1일은 하순 아님", not is_late_month(last, days))
    chk("월초 첫날은 하순 아님", not is_late_month(min(days), days))
    chk("entry_blocked = 하순", entry_blocked(late[0], days) is True)
    chk("enabled=False면 차단 안함", entry_blocked(late[0], days, enabled=False) is False)
    chk("데이터 없는 날 -> 차단 안함", entry_blocked(_dt.date(1999, 1, 1), days) is False)

    chk("시총 소 -> 차단", entry_blocked(late[0], days, tier="소") is True)
    chk("시총 중 -> 차단", entry_blocked(late[0], days, tier="중") is True)
    chk("시총 대 -> 차단 안함 (OOS 기각)", entry_blocked(late[0], days, tier="대") is False)
    chk("대형주 사유 문자열", "대형주" in why(late[0], days, tier="대"))
    chk("소형주 사유에 30년 근거", "0.0002" in why(late[0], days, tier="소"))

    jul_obs = [_dt.date(2026, 7, d) for d in (1, 2, 3, 6, 7, 8, 9, 10)]
    today = _dt.date(2026, 7, 13)
    rd_t, proj = project_rdom(today, jul_obs)
    chk("진행 중인 달도 판정된다", rd_t is not None)
    chk("투영 플래그 ON", proj is True)
    chk("2026-07-13 -> rd=-15 (하순 아님)", rd_t == -15)
    chk("2026-07-13 진입 차단 안함", entry_blocked(today, jul_obs) is False)
    win = next_late_window(today, jul_obs)
    chk("2026-07 하순 = 07-21~07-27",
        win == (_dt.date(2026, 7, 21), _dt.date(2026, 7, 27)))
    chk("07-21 하순 -> 차단", entry_blocked(_dt.date(2026, 7, 21), jul_obs) is True)
    chk("07-28 하순 아님 -> 통과", entry_blocked(_dt.date(2026, 7, 28), jul_obs) is False)

    print(f"\n  [6월 완결월] 하순: {[str(d) for d in late]}")
    print(f"  [7월 진행월] 오늘 2026-07-13 -> rd={rd_t}  ·  하순 {win[0]} ~ {win[1]}")
    print(f"\n  근거: 30년패널 OOS p=0.0002(소)/0.0041(중) · 대형주 기각(0.1211)")
    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


if __name__ == "__main__":
    _self_test()
