# 진우퀀트 — KOSDAQ 테마 발굴 시스템 (체계화)

> 2026-06-06 | 목적: 진우의 forward 테마 강점을 **반복 가능한 발굴 파이프라인**으로. backward 알파 모델 아님(그건 v4.1이 실력 미입증 판명). production·C·D·영역3·v41 무수정.

---

## 0. 한 줄

**테마는 진우가 forward로 찾고(top-down), 시스템은 그 테마를 KOSDAQ 종목군으로 매핑·가드레일·선반영 체크·측정한다.** "넓게 surfacing + 좁게 확신 매수."

## 1. 방법론 근거 (web)

- 테마투자 = 산업분류를 **가로지르는 구조적 트렌드**(AI·로봇·2차전지). 종목은 **value-chain 전체**에 분포 → 산업 1개가 아니라 가치사슬로 매핑. ([BlackRock](https://www.blackrock.com/us/individual/insights/thematic-investing), [Alpha Architect](https://alphaarchitect.com/thematic-investing/))
- 최대 리스크 = **crowding/집중**: 트렌드가 안 풀리거나 이미 쏠리면 손실. → **선반영 체크가 핵심 규율.** ([Schwab](https://www.schwab.com/learn/story/what-is-thematic-investing))
- 2026 KR 라이브 테마: 2차전지/ESS(AI데이터센터 ESS 수요)·로봇(physical AI)·반도체 소부장/AI인프라(HBM·데이터센터)·바이오·AI. 정부 **150조 성장펀드**가 AI·반도체·로봇·모빌리티·바이오·2차전지 지원. ([KED](https://www.kedglobal.com/korean-stock-market/newsView/ked202512180006), [Korea Herald](https://www.koreaherald.com/article/10640375))

## 2. 5단계 발굴 파이프라인

| 단계 | 내용 | 도구/소스 |
|---|---|---|
| ① **테마 식별** (top-down) | 메가트렌드·정책(성장펀드)·수급(외국인/기관 쏠림)·신제품/수주 뉴스에서 테마 포착 | 진우(forward) + §5 소스 |
| ② **value-chain 매핑** | 테마 → 산업 키워드 → 가드레일 통과 KOSDAQ 후보군 surfacing | `kosdaq_theme_discover.py` |
| ③ **가드레일** | 부도·동전주·관리 배제(생존/실행) | `kosdaq_theme_guardrail.py` |
| ④ **선반영(crowding) 체크** ⭐ | 급등(+100%↑)·고점근접·밸류·수급누적·뉴스 보편화 → 늦었나? | 툴 플래그 + 진우 판단 |
| ⑤ **thesis→실행→측정** | 무효화 트리거 등록 → cap ≤10% → Track W 반사실 측정 | watchlist + 실전기록 §3-1 |

## 3. 테마 taxonomy (라이브, 2026-06 발굴 툴 실측)

| 테마 | value-chain 산업 키워드 | 가드레일 통과 후보 | 대표 KOSDAQ(분류용·매수신호 아님) |
|---|---|---|---|
| 로봇 | 로봇·특수목적기계 | 108 | 레인보우로보틱스·로보티즈·로보스타·휴림로봇 |
| 2차전지 | 전지·축전지·이차전지 | 10 | 에코프로비엠·에코프로·비나텍·비츠로셀 |
| 반도체소부장 | 반도체·전자부품·특수목적기계 | 212 | 주성엔지니어링·원익IPS·이오테크닉스·테스·기가비스 |
| 바이오 | 의약·의료·바이오·생물 | 101 | 펩트론·HLB·알테오젠·씨어스·올릭스 |
| AI소프트웨어 | 소프트웨어·자연과학·정보서비스 | 132 | (키워드 노이즈 有 — §8, --kw로 정밀화) |
| 에너지ESS | 전기·에너지·발전·전력 | 31 | 서진시스템·에스피지·우리기술 |
| 우주방산 | 항공·우주·무기·방위 | 9 | 쎄트렉아이·켄코아에어로스페이스 |

## 4. 도구 cheat sheet

```bash
python kosdaq_theme_discover.py --list-themes        # 테마→키워드
python kosdaq_theme_discover.py                       # 전 테마 후보수+모멘텀상위
python kosdaq_theme_discover.py --theme 로봇          # 테마 후보 표(시총·성장·모멘텀·고점대비·선반영)
python kosdaq_theme_discover.py --kw 반도체,전자부품   # 커스텀 산업 키워드(정밀)
```
출력 `kosdaq_theme_discover_<테마>.csv` — thesis·무효화 빈칸=진우 기입.

## 5. 월간 cadence + 모니터 소스

- **월 1회** 테마 스캔: ① 수급(외국인/기관 순매수 쏠림 섹터) ② 신규/유입 ETF(테마 ETF 출시·자금) ③ 정책(성장펀드·국가전략기술) ④ 산업뉴스(수주·신제품·CAPEX) → 테마 후보 갱신
- `--theme` 실행 → 후보군 + 선반영 플래그 갱신 → watchlist 반영
- 분기: thesis 재심사(무효화 트리거 점검)

## 6. 선반영(crowding) rubric — early vs late ⭐

| 신호 | early(좋음) | late/위험(선반영) |
|---|---|---|
| 12-1 모멘텀 | 완만 상승 | **+100%↑ 급등** |
| 12m 고점 대비 | 여유 있음 | **-5% 이내 근접** |
| 뉴스/관심 | 초기·소수 | 모두 아는 보편화 |
| 수급 | 유입 시작 | 이미 대량 누적 |
| 밸류 | 합리 | 과열 |

→ 툴이 `급등`/`고점근접`/`소외(역발상?)` 자동 플래그. **late일수록 thesis·무효화 트리거를 더 엄격히.** (대부분 고모멘텀 테마名은 이미 급등=선반영 — 카탈리스트가 *남았는지*가 관건)

## 7. 정직 가드

1. **매수신호 아님** — 툴은 후보 surfacing·맥락 표기일 뿐. thesis·매수는 진우.
2. **모멘텀 ≠ 미래** — 고모멘텀=이미 반영일 수 있음(선반영 플래그). backward 지표를 알파로 쓰지 않는다(v4.1 교훈).
3. **백테스트 없음** — 테마는 forward. 검증은 Track W 반사실(같은 돈 시스템 픽 대비) 6~12개월 측정.
4. **키워드 매핑 한계** — 산업분류가 coarse(예: AI에 바이오 R&D 혼입). --kw로 정밀화, 진우 검토 필수.
5. **hindsight 금지** — "샀어야"는 무의미. 지금부터 forward만.

## 8. 다음 정밀화 (선택)
- 산업 키워드 정제(AI/바이오 분리), 종목별 테마 태깅 보강
- 수급 데이터(외국인/기관) 연동 → 선반영 자동 강화
- 밸류 지표(PSR 등) 추가 — 단, 선정 알파 아니라 crowding 보조로만

---
> 연계: `진우퀀트_종목선정_강점플레이북.md`(전략)·`진우퀀트_하이브리드_테마lane_스케치.md`(lane 설계)·`kosdaq_theme_watchlist.csv`(기록). 이 문서 = 그 lane의 **발굴 엔진**.
