# 영역 3 확장 모듈 시작 prompt (universe 확정 후 사용)

> **사용법**: ① universe 규칙화 대화에서 최종 종목 리스트가 확정되면 → ② Cowork 새 세션 열고
> **Desktop\진우퀀트 폴더 연결** → ③ 아래 prompt 복붙 + universe 리스트 첨부(또는 파일명 명시). 끝.

---

## 복붙용 prompt

```
새 모듈 작업: "영역 3 확장 = 확장 universe + DART 자동화 + 비용·합격선 재설계 + regime 재시험 1회".
이 작업은 모듈 D(v4.0 regime, 2026-06-05 공식 기각·종결)의 승인된 후속이다.

[먼저 읽을 것 — Desktop\진우퀀트]
1. 진우퀀트_v40_regime_결정메모.md §10 (승인된 로드맵·실행 트리거) + §8 (18종목 기각 사유)
2. fetch_regime_kosdaq_v40.py + regime_history_v40_kosdaq.csv (KOSDAQ detector — 어긋남 29% 실측 완료, 재사용)
3. 확정 universe 리스트: [여기에 파일명 또는 리스트 붙여넣기]

[작업 범위 — 결정메모 §10 승인 사항]
② DART 전 종목 자동화: 확정 universe의 F_korean·ModF·Sloan 등 재무 입력 자동화
   (기존 fetch_dart_quality.py·fetch_dart_eps.py 패턴 재사용, production 무수정)
③ 비용·합격선 재설계: 코스닥 왕복 0.5~0.7% 가정(등록된 prior), 합격선은 Stage 0에서
   사전 등록 후 변경 금지 (C·D 전례)
regime 재시험: 코스피 종목은 KOSPI detector, 코스닥 종목은 KOSDAQ detector
   (regime_market_cache_v40*.json 재사용). 18종목 기각과 별개 조합 — 1회만, 변형 2개 이내.

[원칙 — 전 모듈과 동일]
- production(score_v37_2)·C(v3.9 관찰)·D 산출물 무수정, 새 파일로만
- Stage 0 결정메모(합격선 사전 등록) → 데이터 → 코드+self-test → 공식 엔진 백테스트 순서
- 재현 게이트는 절대값 참조 비교 대신 **동시점 공식 엔진 병행 실행**으로 설계
  (D의 교훈: 참조 CAGR은 기록 시점 시장에 종속 — 2026-06 급락으로 게이트 오작동 경험)
- PC 실행 필요 단계는 명령어 수준으로 정리해서 전달

먼저 위 문서들 읽고 단계별 빌드 계획부터 정리해줘. 질문은 1~2개로 압축.
```

---

## 그 전까지 진우가 할 일 (D 관련 없음)

| 시기 | 할 일 |
|---|---|
| 매월 초 | 평소 루틴 그대로: score_v37_2 + score_v39_pead 실행, v3.9 관찰기록 1줄 기입 |
| 분기 초 (7월) | fetch_dart_eps.py 1회 (C 관찰용) |
| 2026-09 초 | v3.9 관찰 판정 + v3.7.2 옵션 B(ECHO 1.2) 검토 — 기존 일정 |
| 수시 | **universe 규칙화 대화 마무리** ← 영역 3 모듈의 유일한 선행 조건 |

작성: 2026-06-05 (모듈 D 종결 세션)
