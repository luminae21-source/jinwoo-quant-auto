# 병합 준비 — 뜨거운 테마 + 진입 시스템 (2026-06-14)

> push는 **진우 확인 후**. 이 문서는 병합 준비(파일 분리·커밋 그룹·절차·주의)만.
> 작업트리 현황: **변경(M) 142 · 신규(??) 86** — 이번 세션 외 기존 미커밋이 다수. 전부 한 번에 올리지 말 것.

## 1. 이번 세션 신규 파일 (커밋 그룹 = "theme_heat + entry")
**코드(핵심)**
- `theme_heat.py` — 뜨거운 테마 모니터 + 주봉 차트 + 진입신호 연결 (셀프테스트 7/7)
- `entry_signals.py` — 진입 상태머신(SEPA·돌파·손절·R·regime) (셀프테스트 9/9)
- `verify_weekly_reconcile.py` — 주봉↔월봉 정합 게이트 (셀프테스트 통과, KOSDAQ·KOSPI PASS)
- `fetch_kospi_daily_full.py` — KOSPI 전 시장 일봉 fetch(PC용) (오프라인 셀프테스트 4/4)

**문서**
- `진우퀀트_진입상태머신_설계메모_2026-06-14.md` — 진입 설계 합의본

**산출물(재생성 가능 — 커밋 선택)**
- `theme_heat_latest.csv` · `theme_heat_members_latest.csv` · `verify_weekly_reconcile_result.json`
- `뜨거운테마_브리핑_2026-06-30.md` · `뜨거운테마_패널_2026-06-30.html`
- `진입_워치리스트_핸드오프_후보.md`
- `진우퀀트_작업개요_2026-06-14.html` (본 세션 개요)

**의존(이미 있던 untracked, 이번 작업이 사용)**: `supercycle_overlay.py` · `theme_classify.py` · `theme_universe.csv` · `regime_history_v40.csv` · `kosdaq_pit_daily.csv` · `fundamentals_pit.csv`.

## 2. ⚠️ gitignore 권고
- `kospi_pit_daily.csv` = **44MB** (fetch로 재생성 가능) → **커밋 비권장**. `.gitignore`에 추가 제안:
  ```
  kospi_pit_daily.csv
  ```
  (kosdaq_pit_daily.csv도 14–27MB로 이미 추적 중이면 동일 검토.)

## 3. 권장 커밋 그룹 (제안 메시지)
```
git add theme_heat.py entry_signals.py verify_weekly_reconcile.py \
        fetch_kospi_daily_full.py 진우퀀트_진입상태머신_설계메모_2026-06-14.md
git commit -m "feat(theme): 뜨거운 테마 모니터 + 주봉 차트 + 진입 상태머신(SEPA/돌파/손절·R) + 주봉↔월봉 정합 게이트(KOSPI/KOSDAQ PASS) (2026-06-14)"
# 산출물 커밋(선택):
git add theme_heat_latest.csv theme_heat_members_latest.csv verify_weekly_reconcile_result.json 진입_워치리스트_핸드오프_후보.md
git commit -m "chore(theme): heat/entry 산출물 갱신 2026-06-14"
```

## 4. 안전 push 절차 (기존 핸드오프 §3 동일)
```
git stash -u
git pull --rebase origin main
git stash pop        # 충돌 시 해결
git add ...          # 위 그룹
git commit -m "..."
git push
```
- CI(daily.yml)가 생성파일로 rebase 막으면 `--autostash` 사용(기존 이슈 해결 패턴).

## 5. 병합 전 점검 체크리스트
- [ ] `python theme_heat.py --selftest` → 7/7
- [ ] `python entry_signals.py --selftest` → 9/9
- [ ] `python verify_weekly_reconcile.py --self-test` → 통과
- [ ] `kospi_pit_daily.csv` gitignore 여부 결정
- [ ] 기존 142 M / 나머지 ?? 는 **별도 검토** (이 커밋에 섞지 않기)
- [ ] production·C·D·발굴트랙 정본 **무수정** 확인 (이번 작업은 신규 파일만)

## 6. 무수정 보장
이번 세션은 **신규 파일만 추가**. production 스코어엔진·C/PEAD·D regime·영역3·v41·active 워치리스트 정본 손대지 않음. theme_classify/supercycle_overlay는 **읽기만**(소스 직접 컴파일 로드, .pyc 회피).
