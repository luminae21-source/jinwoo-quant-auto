# 진우퀀트 v4.0 — 영역 4 Phase 1 완료 핸드오프

> 작성일: 2026-05-24
> 작업: 영역 4 (Attribution + 교체룰) Phase 1 — CAPM β 분해
> 다음 단계: 진우님 PC 실 데이터 검증 → Phase 2 (산업 ETF) 진입 여부 결정

---

## 0. 영역 4 4-Phase 구조 (핸드오프 doc의 정의)

| Phase | 분해 단위 | 모델 | 상태 |
|---|---|---|---|
| **Phase 1** | 시장 vs 종목 | CAPM (단일 β) | ✅ **완료** (오늘) |
| Phase 2 | + 산업 | 2-factor (Market + Sector ETF) | 설계 완료, 데이터 매핑 대기 |
| Phase 3 | + 펀더멘털·모멘텀 | Multi-factor (Mkt + Sector + F + Mom + BAB) | 미착수 |
| Phase 4 | + 이벤트 | Event detection (DART 공시 + 뉴스 NLP) | 미착수 |

오늘 Phase 1을 끝낸 이유:
- **즉시 실용 가치**: 시장 vs 종목 분해만으로도 v3.6 매매룰의 trailing stop 헛수고 (T3 케이스)를 막을 수 있음
- **데이터 가벼움**: KOSPI + 18종목 일별 종가만 필요 → score_v37.py와 동일 데이터 소스
- **통계적 안전**: 단일 factor라 18종목 N 문제 없음 (각 종목 시계열 회귀)
- **후속 단계 기반**: Phase 2~4가 같은 분해 프레임워크 확장

---

## 1. 산출물 파일

```
진우퀀트/
├── attribution_v40_phase1.py         ← 메인 코드 (FDR + 분해 + 트리거 + HTML)
├── attribution_panel_SAMPLE.html     ← 합성데이터 결과 미리보기
├── 진우퀀트_v40_교체룰v0.md          ← T1~T5 트리거 명세서
└── 진우퀀트_v40_영역4_Phase1.md      ← 이 문서
```

기존 v3.6/v3.7 파일은 손대지 않음 (회귀 안전).

---

## 2. Phase 1 핵심 결과

### 분해 모델
```
r_i,t = α_i + β_{i,t-1} × r_KOSPI,t + ε_i,t
```
- β는 60영업일 rolling, **1일 lag** (look-ahead bias 차단)
- 출력: market_contrib, idio, idio_z (60일 rolling z-score)

### 5개 트리거 (교체룰 v0)

| 코드 | 조건 | 의미 | 액션 |
|---|---|---|---|
| **T1** | 단일일 \|idio_z\| ≥ 3.0 | 이벤트 의심 | 즉시 뉴스/공시 확인 |
| **T2** | 20일 Σ idio ≤ −10% | 종목 고유 약세 누적 | F-Score 재점검, 2개월 연속 시 비중 축소 |
| **T3** | 20일 Σ r ≤ −10% **AND** Σ idio > −3% | 시장 동조 약세 | **보유 유지** (trailing stop 무시 가능) |
| **T4** | 20일 Σ idio ≥ +10% | 종목 알파 발생 | Mom12와 교차 확인 |
| **T5** | β 30일 Δ ≥ 0.4 | 종목 성격 변화 | Kelly sizing 재계산 |

### 검증 결과 (sandbox 합성 데이터)

5가지 unit test 전부 통과:
- **β 추정** — true 1.2 → 추정 1.13 (60일 window 합리적 오차)
- **분해 항등식** — `r = market_contrib + idio` 오차 0 (정의상 보존)
- **T1 발동** — -8% idio shock 종목을 정확히 잡음
- **T2 발동** — -0.7%/일 × 20일 누적 약세 종목을 정확히 잡음
- **idio_z 분포** — 평균 -0.003, std 0.97 (이론값 0, 1)

`attribution_panel_SAMPLE.html`에서 18종목 합성 시나리오 결과 시각화 확인 가능.

---

## 3. v3.6 매매룰과의 통합 (즉시 적용 가능)

Phase 1 트리거가 v3.6 trailing stop의 false signal을 거른다:

| v3.6 신호 (가격) | Phase 1 교차 신호 | 권장 액션 |
|---|---|---|
| Trailing -8% 알림 | T3 (시장 동조) 발동 | **무시** |
| Trailing -8% 알림 | T2 (종목 약세) 발동 | 정밀조사 |
| Trailing -15% 축소 | T3 발동 + T2 없음 | **보류** (시장 회복 대기) |
| Trailing -15% 축소 | T2 발동 | 그대로 실행 |
| Trailing -25% 청산 | T1+T2 발동 | 그대로 실행 |

NAVER 디커플링 케이스 (v3.6 매매룰 명시 케이스) — 이게 정확히 T2 vs T3 구분 문제. Phase 1이 이런 판단을 정량화함.

---

## 4. 진우님 검증 실행 순서 (PC에서)

### Step 1: 실 데이터로 첫 실행
```bash
cd "C:\Users\긍정적인_삶의자세\OneDrive\문서\Claude\Projects\진우퀀트"
python3 attribution_v40_phase1.py --save-html
```

**예상 출력:**
- 콘솔: 18종목 현재 β 분포, 20일 누적 분해, 발동 트리거
- `attribution_v40_YYYYMMDD_HHMM.json` — 일별 이력 누적
- `attribution_panel.html` — 모바일 친화 패널

**예상 시간:** 4~7분 (FDR 18종목 × 400일)

### Step 2: 결과 검증 포인트

1. **β 값 sanity check**
   - KT&G β ≈ 0.5~0.8 (안정주, 예상 부합?)
   - 한미반도체·ISC β ≈ 1.3~1.7 (반도체 변동성)
   - 카카오·NAVER β ≈ 0.9~1.2 (인터넷)
   
2. **트리거 발동 분포**
   - 0~2개 발동: 정상 시장 상태
   - 5+ 발동: 시장 전체 격동 → 모든 룰 보수적 적용
   
3. **NAVER/카카오 케이스**
   - 최근 인터넷 약세 시기에 T2 발동 → 진짜 약세
   - T3 발동 → 시장 동조 → 보유

### Step 3: 1~2주 trial run

매일 실행해서 트리거 변화 관찰. False positive 케이스 메모:
- "T2 발동했는데 다음 주 회복" → 임계값 너무 민감
- "T1 이벤트인데 진짜 별 일 없었음" → z=3.0이 너무 관대

### Step 4: GitHub Actions 통합 (선택)

`github_setup/.github/workflows/daily.yml`에 추가:
```yaml
- name: Phase 1 Attribution
  run: |
    cd github_setup
    python3 attribution_v40_phase1.py --save-html
```

대시보드 페이지에 `attribution_panel.html`을 iframe으로 또는 통합 페이지로 embed.

---

## 5. 알려진 한계 (Phase 2~4로 해결)

### Phase 1만으로는 풀 수 없는 케이스

**Case A — 산업 동조를 종목 고유로 오인**
- 카카오 -5%, KOSPI +1%, NAVER -4% (인터넷 약세)
- Phase 1: "카카오 종목 고유 -6%" → T2 발동 (잘못된 경고)
- **Phase 2 해결**: 인터넷 ETF (KODEX 인터넷 등) factor 추가하면 -4%는 산업, -2%만 종목

**Case B — 펀더멘털 변화 미감지**
- 분기 실적이 컨센서스 하회했는데 주가는 아직 반영 전
- Phase 1: 트리거 발동 안 함 (가격 변동 없음)
- **Phase 3 해결**: F-Score 변화·실적 발표 시점을 factor에 추가

**Case C — 이벤트 자동 분류 불가**
- T1이 "이벤트 의심"까지만 알림. M&A인지 자사주 매입인지 분류 못 함
- **Phase 4 해결**: DART 공시 + 뉴스 NLP

### 통계적 한계

- 18종목으로 cross-sectional factor 추정 불가능 (N 부족)
- → 모든 factor를 **관측 가능한 ETF/지수**로 사용 (자체 합성 X)
- 산업 ETF 매핑이 Phase 2의 가장 큰 작업

---

## 6. Phase 2 진입 조건 (모두 충족 시 시작)

- [ ] Phase 1 3개월 운용 — 트리거 발동 빈도와 false positive 측정
- [ ] 18종목 산업 ETF 매핑 확정
- [ ] 산업 ETF FDR 5년치 데이터 가용성 확인
- [ ] Phase 1의 false signal 케이스 분석 → 산업 추가 시 해결 사례 ≥ 30%

### Phase 2 사전 작업 (지금 해둘 수 있는 것)

산업 ETF 후보 (확정 전):
- 반도체 → KODEX 반도체 (091160) ✅
- 바이오 → KODEX 바이오 (244580) 또는 KOSDAQ150 바이오
- 자동차 → KODEX 자동차 (091180) ✅
- 인터넷 → KODEX 인터넷 (157490) ✅
- 방산 → SOL K방산 / KODEX K방산 (신규 ETF, 데이터 길이 짧을 수 있음)
- 금융 → KODEX 은행 (091170) + KODEX 증권 (102970) 평균
- 2차전지 → KODEX 2차전지산업 (305720) ✅
- 화장품 → 마땅한 ETF 없음 — KOSPI200 대체 또는 합성
- 식품 → 마땅한 ETF 없음 — 동일
- 원전 → HANARO 원자력iSelect (453950) — 신규
- 종합상사 (삼성물산) → KOSPI200 대체
- 필수소비재 (KT&G) → KOSPI200 또는 마이너스 변동 인덱스

진우님이 Phase 1 검증 중에 진우 PC에서 시험 다운로드해보면 좋음:
```python
import FinanceDataReader as fdr
df = fdr.DataReader('091160', '2021-01-01')  # KODEX 반도체
print(df.head(), df.shape)
```

---

## 7. 영역 4 후속 Phase 우선순위

핸드오프 doc은 Phase 1 → 2 → 3 → 4 순서 권장하지만, **운용 경험상 우선순위**:

1. **Phase 1 (오늘 완료) + 3개월 운용** — 가장 ROI 높음 (즉시 trailing stop 정밀화)
2. **Phase 2 (산업)** — 의의 큼 (인터넷·반도체 동조 분류). 데이터 매핑 작업이 핵심
3. **Phase 4 (이벤트 detection)** ← Phase 3보다 먼저 권장. 이유: T1 이벤트를 자동 분류하면 진우의 주말 검토 시간 단축
4. **Phase 3 (multi-factor)** — Phase 2·4 완료 후. 가장 무거운 통계 작업

---

## 8. 영역 1·2·3과의 관계

영역 4 Phase 1이 다른 영역에 기여:

### 영역 1 (v3.7 신규 팩터) 보강
- BAB는 β 기반 → Phase 1의 β 추정과 일관성 검증 가능
- Phase 1 트리거 T5 (β 급변)가 BAB 점수 갱신 시점 자동 알림 역할

### 영역 2 (매매룰)에 직접 입력
- T3 발동 시 trailing stop 무시 → v3.6 매매룰 자동 보강
- T1 발동 시 4분할 매수 일시 정지 (이벤트 정밀조사 후 재개)

### 영역 3 (Universe 확장)에 신호 제공
- T2 3개월 연속 종목 = universe 교체 후보 자동 식별
- T4 발동 종목 = 동일 산업 다른 강세주 발굴 신호

---

## 9. 다음 세션 시작 시 첨부할 파일

영역 4 Phase 2 시작할 때:
- 이 핸드오프 (`진우퀀트_v40_영역4_Phase1.md`)
- 교체룰 v0 (`진우퀀트_v40_교체룰v0.md`)
- Phase 1 코드 (`attribution_v40_phase1.py`)
- Phase 1 운용 결과 JSON 누적 이력 (최소 1개월치)
- (만약 진행했다면) 산업 ETF 매핑 표

---

## 10. 체크리스트

오늘 (2026-05-24) 완료:
- [x] 한국시장 factor model 리서치 (FF3·FF5·Carhart·q-factor)
- [x] Phase 1 데이터 인프라 설계 (score_v37.py 패턴 재사용)
- [x] `attribution_v40_phase1.py` 작성 (450 lines)
- [x] 5개 unit test 통과 (합성 데이터)
- [x] 교체룰 v0 명세 (`진우퀀트_v40_교체룰v0.md`)
- [x] 합성 HTML 패널 (`attribution_panel_SAMPLE.html`)
- [x] 핸드오프 문서 (이 파일)

진우님이 다음에 할 것:
- [ ] PC에서 `python3 attribution_v40_phase1.py --save-html` 실행
- [ ] 18종목 실제 β 분포 검증 (KT&G 낮을지, 반도체 높을지)
- [ ] 1~2주 trial run → 트리거 발동 패턴 관찰
- [ ] (선택) GitHub Actions 통합
- [ ] 3개월 운용 후 Phase 2 진입 결정

---

## 11. 진우님 자기 진단 (영역 4 시작 전 doc의 체크리스트)

핸드오프 doc 7장의 자기 진단 적용:

- ✅ **이 영역의 목적이 명확한가?** → 매도 false signal 거르기 + 진짜 약세 정밀 감지
- ✅ **백테스트로 검증 가능한가?** → 매월 발동 트리거 vs 실제 종목 결과 비교 (1년 누적 후 본격 calibration)
- ✅ **실제 운용에 반영 가능한가?** → 모바일 패널 1번 확인, 주말 5분 검토. v3.6과 통합 쉬움
- ✅ **v3.6보다 진짜 나아지는가?** → trailing stop의 가장 큰 약점(시장 동조 판단 불가)을 해결

→ 4개 모두 YES. 진행 가치 있음.

---

**Phase 1 완료. 다음 작업은 진우님 PC에서 실 데이터 검증.**
**작성: 2026-05-24**
