# 진우퀀트 v3.7.2 GitHub Actions 설정 가이드

작성일: 2026-05-29

---

## 🎯 목표

진우퀀트 v3.7.2를 GitHub Actions로 매일 자동 실행 + GitHub Pages로 dashboard 배포.

```
매일 16:30 KST → GitHub Actions 트리거 → score_v37_2.py 실행
              → dashboard_v37_2.html 생성 → GitHub Pages 자동 배포
              → 진우님 모바일에서 dashboard URL 확인
```

---

## 📋 사전 준비 (1회만)

### 1. GitHub Repository 확인/생성

**옵션 A**: 기존 repo 활용
- `luminae21-source/jinwoo-quant-auto` (메모리 reference)
- 진우님이 기존 repo 사용 중이면 그대로 활용

**옵션 B**: 새 repo 생성
- GitHub에서 새 repo 생성: `jinwoo-quant-v37-2`
- private 또는 public 둘 다 가능
- README.md 초기 추가

### 2. 로컬 폴더 → GitHub repo로 push

```powershell
cd "C:\Users\긍정적인_삶의자세\OneDrive\문서\Claude\Projects\진우퀀트"

# Git 초기화 (이미 init된 경우 skip)
git init

# .gitignore 추가 (개인정보 보호)
@'
# DART API 키 보호
dart_config.json

# Quality data cache (분기마다 갱신)
quality_data_cache.json
quality_timeseries_cache.json

# Backtest 결과 (큰 파일)
backtest_*.json
validate_*.json
factor_correlation_*.json

# Python
__pycache__/
*.pyc

# Logs
*.log
'@ | Out-File .gitignore -Encoding utf8

# 원격 추가
git remote add origin https://github.com/<username>/<repo-name>.git

# 첫 push
git add .
git commit -m "Initial commit: v3.7.2 production setup"
git branch -M main
git push -u origin main
```

### 3. DART API key를 GitHub Secrets에 추가

1. GitHub repo 페이지 → **Settings**
2. 좌측 메뉴 → **Secrets and variables** → **Actions**
3. **New repository secret** 클릭
4. **Name**: `DART_API_KEY`
5. **Secret**: 진우님 DART API key (40자리)
6. **Add secret** 클릭

⚠️ **중요**: DART API key는 절대 코드에 직접 입력하지 말 것. Secrets로만 관리.

### 4. GitHub Pages 활성화

1. GitHub repo 페이지 → **Settings**
2. 좌측 메뉴 → **Pages**
3. **Source**: GitHub Actions 선택
4. (자동 활성화)

---

## 🚀 워크플로우 활성화

### Workflow 파일 위치 확인

이미 작성된 파일:
```
진우퀀트/.github/workflows/jinwoo-quant-v37-2.yml
```

이 파일을 GitHub에 push하면 자동으로 Actions에 등록됩니다.

### 첫 수동 실행 테스트

1. GitHub repo → **Actions** 탭
2. 좌측 워크플로우 목록에서 **Jinwoo Quant v3.7.2 Auto** 선택
3. 우측 **Run workflow** 버튼 클릭
4. **Run workflow** 확인
5. 약 2-3분 대기 → 실행 결과 확인

### 매일 자동 실행

활성화 후:
- **매일 16:30 KST (평일만)** 자동 실행
- 결과:
  - `dashboard_v37_2.html` 생성
  - GitHub Pages 자동 배포
  - URL: `https://<username>.github.io/<repo-name>/`

---

## 📱 진우님 모바일 접근

### Dashboard URL

GitHub Pages 배포 후:
```
https://luminae21-source.github.io/jinwoo-quant-v37-2/
```

(또는 진우님 GitHub username + repo name 기반)

### 모바일 사용법

1. URL을 모바일 브라우저로 접속
2. **홈 화면에 추가** (iOS Safari · Android Chrome)
3. 매일 자동 갱신 (16:30 KST 이후)
4. 매월 첫 영업일에 dashboard 확인 → 매매 결정

---

## 🔄 v3.6 / v3.7.1 / v3.7.2 병행 실행

워크플로우는 3가지 버전 모두 실행:

| URL | 버전 | 용도 |
|---|---|---|
| `/index.html` 또는 `/v37_2.html` | **v3.7.2 (production)** | 매일 갱신 |
| `/v36.html` | v3.6 (baseline) | 비교 reference |
| `/v37_1.html` | v3.7.1 (backup) | 안전망 |

진우님이 매월 매매 시 v3.7.2 primary 사용, v3.6 비교 확인 가능.

---

## ⚙️ 환경변수 설정 (필수)

워크플로우 실행 시 다음 secrets 필요:

| Secret | 용도 | 설정 |
|---|---|---|
| `DART_API_KEY` | DART API key | https://opendart.fss.or.kr 발급 |
| (선택) `SLACK_WEBHOOK` | 실패 알림 | Slack 통합 시 |
| (선택) `EMAIL_RECIPIENT` | 이메일 알림 | 향후 추가 |

---

## 🛠️ 트러블슈팅

### 케이스 1: DART API 호출 실패
- Secrets에 `DART_API_KEY` 설정 확인
- DART API key 유효성 확인 (만료 가능성)
- DART API 일일 호출 한도 (10,000회) 확인

### 케이스 2: GitHub Actions 분 한도 초과
- Free tier: 월 2,000분
- 매일 실행 (월 22회) × 약 3분 = 66분/월 (한도 내)
- 분 추가 필요 시 GitHub Pro 또는 Self-hosted runner

### 케이스 3: 워크플로우가 매일 자동 실행 안 됨
- GitHub repo가 60일 이상 inactivity 시 schedule 자동 비활성화
- 매월 1회 수동 push 또는 manual trigger 권장

### 케이스 4: GitHub Pages 배포 실패
- Settings → Pages → Source가 "GitHub Actions"인지 확인
- repo가 public이거나 GitHub Pro 계정인지 확인 (private + free는 Pages 불가)

---

## 🔐 보안 권장사항

### 절대 GitHub에 push하면 안 되는 것
- `dart_config.json` (API key 포함)
- `quality_data_cache.json` (큰 파일)
- 개인 매매 내역
- (모두 `.gitignore`에 포함됨)

### Public repo 사용 시 추가 고려
- 18종목 universe (`JINWOO_v37` dict)는 학술적 목적이라 공개 OK
- 매매 비중·실전 결과는 별도 private 폴더에 보관

---

## 📊 모니터링

### Workflow 실행 상태 확인

GitHub repo → **Actions** 탭:
- 녹색 ✅: 정상 실행
- 빨간색 ❌: 실패 (클릭해서 로그 확인)
- 노란색 🟡: 진행 중

### 실패 시 알림 (선택)

`.github/workflows/jinwoo-quant-v37-2.yml`에 추가:
```yaml
- name: Notify on failure
  if: failure()
  uses: 8398a7/action-slack@v3
  with:
    status: ${{ job.status }}
    webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

---

## 🎯 첫 운영 후 체크리스트

활성화 후 1주일 내:

- [ ] GitHub Actions 매일 정상 실행 (5/5 영업일)
- [ ] Dashboard URL이 진우님 모바일에서 정상 로드
- [ ] DART API 데이터 정상 수집
- [ ] 18종목 점수표 합리성 검증
- [ ] 권장비중 컬럼 정상 표시 (8.33% × 12)
- [ ] v3.6 / v3.7.1 baseline도 정상 실행

이상 없으면 **GitHub Actions 통합 완료**.

---

## 📚 다음 단계

1. Workflow 활성화 후 1-2주 모니터링
2. 안정 확인 시 매월 매매를 dashboard 기반으로 진행
3. 옵션 B 전환 시 (2026-07-29 ~ 08-29) workflow는 그대로, score_v37_2.py만 수정
4. v3.9 진입 시 score_v37_2.py → score_v39.py로 교체

---

## 진우님 액션 (지금)

1. **GitHub repo 확인/생성**
2. **DART API key를 Secrets에 추가**
3. **이 폴더 (진우퀀트) git push** (워크플로우 파일 포함)
4. **Actions 탭에서 첫 수동 실행 테스트**
5. **GitHub Pages URL 확인 후 모바일 등록**

진우님 GitHub 계정 정보 + repo 이름 공유 부탁드립니다. Claude가 워크플로우 추가 디버깅 가능.
