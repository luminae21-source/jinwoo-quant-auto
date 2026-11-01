# -*- coding: utf-8 -*-
"""jq_monthly_remind.py — 매월 1일 월초 체크리스트 카톡 알림 (Claude 예약 작업 대체 · 토큰 0).
본문은 PC 폴더·프로젝트 문서의 진우퀀트_월초_체크리스트.md (루트 *.md는 .gitignore로 비공개). 카톡 텍스트는 짧게(분기초 여부만 달라짐).
사용: python jq_monthly_remind.py [--dry-run] [--self-test]
"""
import sys, datetime
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def build(d):
    q = d.month in (1, 4, 7, 10)
    lines = [f"📅 진우퀀트 {d.month}월 월초 루틴 (PC에서 실행)",
             "① 매월: score_v37_2 · v39 PEAD · 수퍼사이클 모니터 · live_tracker · MA200 점검",
             "② forward_signal → 원장 기록 (파라미터 수정 금지)",
             "③ 유니버스_월초생성.bat → 유니버스_규칙화_현재.csv"]
    if q:
        lines.append("④ 분기초: DART 증분 · score_univ30 --live · rule30 교체 ≤2종")
    lines.append("📄 진우퀀트_월초_체크리스트.md · 투자자문 아님")
    return "\n".join(lines)


def self_test():
    a, b = build(datetime.date(2026, 11, 1)), build(datetime.date(2027, 1, 1))
    assert "11월" in a and "분기초" not in a, a
    assert "분기초" in b, b
    assert len(b) < 400, len(b)
    print("self-test: OK"); return 0


def main():
    text = build(datetime.date.today())
    print(text)
    if "--dry-run" in sys.argv:
        return 0
    import jq_kakao as K
    cfg = K.load_config()
    link = cfg.get("CARD_LINK_URL", "").strip() or "https://k.kakaocdn.net"  # 카카오는 등록 도메인 링크만 허용
    ok, res = K.send_text(K.get_access_token(cfg), text, link)
    print("[카톡]", "OK" if ok else f"실패 {res}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
