# 진우퀀트 v3.6 자동 운영

> 한국 주식 18종목 자동 점수 산출 시스템. 매일 4:30 PM KST 자동 실행.

## 🎯 운영 결과 (α 검증)

- **연 평균 알파:** +18.89% (vs 시장 1,356종목)
- **4년 누적 알파:** +210.82%
- **Information Ratio:** 1.59
- **패배 연도:** 0/4

## 📊 대시보드 접속

매일 자동 갱신되는 대시보드:
**`https://[유저명].github.io/[repo명]/`**

모바일 브라우저에 북마크해서 확인.

## 🏗 아키텍처

```
[GitHub Actions cron, 매일 07:30 UTC = 16:30 KST]
    ↓ score_v36.py 실행
    ↓ FDR로 18종목 1M 수익률 수집
    ↓ FAR 신호 계산 (백승엽 2019)
    ↓ 체력_최종 = F_korean × 12/9.001 + ModF + FAR + Sloan
    ↓ docs/dashboard.html 생성
    ↓ GitHub Pages 자동 배포
    ↓
[모바일 브라우저] 대시보드 확인
```

## 📁 파일 구성

```
.
├── score_v36.py              # 메인 스크립트 (점수 산출)
├── requirements.txt          # Python 의존성
├── .github/workflows/daily.yml  # GitHub Actions cron
├── docs/                     # GitHub Pages 서빙 (자동 생성)
│   ├── index.html
│   ├── dashboard.html
│   ├── v36_scores_latest.csv
│   └── v36_summary_latest.json
└── README.md
```

## 🚀 셋업 가이드 (1회)

### 1. GitHub 저장소 생성

1. https://github.com/new 접속
2. Repository name: `jinwoo-quant-auto`
3. Private 또는 Public 선택 (Pages는 Public이 무료)
4. Create repository

### 2. 파일 업로드

이 폴더의 모든 파일을 새 저장소에 업로드:
```bash
cd /path/to/github_setup
git init
git add .
git commit -m "Initial commit: 진우퀀트 v3.6 자동화"
git remote add origin https://github.com/[유저명]/jinwoo-quant-auto.git
git push -u origin main
```

또는 GitHub 웹에서 "Upload files" 사용.

### 3. DART API 키 등록 (현재 미사용, 추후 분기 갱신용)

저장소 → Settings → Secrets and variables → Actions → New repository secret
- Name: `DART_API_KEY`
- Secret: [발급받은 DART 키]

### 4. GitHub Pages 활성화

저장소 → Settings → Pages
- Source: GitHub Actions
- (저장 후 첫 Actions 실행 후 자동 활성화)

### 5. Actions 권한 확인

저장소 → Settings → Actions → General
- Workflow permissions: **Read and write permissions** 선택
- "Allow GitHub Actions to create and approve pull requests" 체크

### 6. 첫 실행

저장소 → Actions → "진우퀀트 v3.6 자동 점수 갱신" → "Run workflow"

성공하면 `docs/dashboard.html`이 생성되고 GitHub Pages에 배포됨.

## 📅 분기 갱신 (수동)

매 분기 (3·6·9·12월) DART 재무 갱신 시 `score_v36.py`의 `JINWOO_v36` 딕셔너리 업데이트:
- `F_korean` 값 갱신
- `ModF`·`Sloan` 매트릭스 갱신

Cowork·Colab으로 새 점수 계산 후 코드 수정 → 커밋.

## 🔄 v3.7+ 진화 계획

- v3.7: BAB + NOA + Asset Growth 모듈 추가
- v3.8: 12M Momentum 통합
- v4.0: universe 30~50종목 확장
- v5.0: AI 에이전트 자율 발굴

## 📚 학술 백본

- Piotroski (2000), 한상욱 (2015) — F-Score
- Sloan (1996) — Accrual Anomaly
- 백승엽 (2019) — FAR (1M reversal + F)
- 최이름 (2019) — Modified F (산업 보정)
- Mizuno (2020) — β slope (시장 상황)
- Mohanram (2005) — G-Score

## ⚠️ 면책

- 본 시스템은 진우 개인 운용용 의사결정 *지원* 도구
- 실제 매매는 진우퀀트_v36_매매룰.md 참조 + 본인 판단
- 자동 매매 X
