# 진우 셋업 가이드 — 1회 30분

## 1단계: GitHub 계정 (없으면)

1. https://github.com 접속
2. Sign up (이메일·비밀번호)
3. Verify email

## 2단계: 새 저장소 만들기 (3분)

1. https://github.com/new 접속
2. 입력:
   - **Repository name:** `jinwoo-quant-auto`
   - **Description:** `진우퀀트 v3.6 자동 운영`
   - **Public** 선택 (GitHub Pages 무료)
   - "Add a README file" **체크 해제** (이미 있음)
3. **Create repository** 클릭

## 3단계: 파일 업로드 — 가장 쉬운 방법 (10분)

### 방법 A — 웹 업로드

1. 만든 저장소 페이지에서 **"uploading an existing file"** 클릭
2. **드래그&드롭**: `github_setup` 폴더 안의 파일들 전부:
   - `score_v36.py`
   - `requirements.txt`
   - `README.md`
   - `SETUP_GUIDE_진우.md`
   - `.github/workflows/daily.yml`
3. ⚠️ **주의:** `.github/workflows/daily.yml`은 GitHub 웹에서 새 파일 만들기 필요:
   - "Create new file" → 파일명에 `.github/workflows/daily.yml` 입력 (슬래시가 폴더 만듦)
   - 내용 복사·붙여넣기
4. Commit changes

### 방법 B — Git 명령어 (Git 익숙하면)

```bash
cd "C:\Users\긍정적인_삶의자세\OneDrive\문서\Claude\Projects\진우퀀트\github_setup"
git init
git branch -M main
git add .
git commit -m "Initial commit: 진우퀀트 v3.6 자동화"
git remote add origin https://github.com/[유저명]/jinwoo-quant-auto.git
git push -u origin main
```

## 4단계: Actions 권한 설정 (1분)

1. 저장소 → **Settings** 탭
2. 왼쪽 메뉴 → **Actions** → **General**
3. **Workflow permissions** 섹션:
   - ✅ **Read and write permissions** 선택
   - ✅ **Allow GitHub Actions to create and approve pull requests** 체크
4. **Save** 클릭

## 5단계: GitHub Pages 활성화 (1분)

1. **Settings** → 왼쪽 메뉴 → **Pages**
2. **Build and deployment** 섹션:
   - **Source:** GitHub Actions 선택
3. 끝 (별도 저장 버튼 없음)

## 6단계: 첫 실행 — 수동 테스트 (5분)

1. 저장소 상단 **Actions** 탭
2. 왼쪽에 "진우퀀트 v3.6 자동 점수 갱신" 클릭
3. 오른쪽 위 **"Run workflow"** 버튼 클릭
4. **"Run workflow"** 한번 더 클릭 (초록 버튼)
5. 2~3분 기다림
6. 실행 결과 확인 (초록 ✓ = 성공, 빨간 ✗ = 실패)

## 7단계: 대시보드 접속 (1분)

성공하면:
- **URL:** `https://[유저명].github.io/jinwoo-quant-auto/`
- 모바일 브라우저 **북마크 추가**

## 8단계: 자동 실행 확인

- 매일 KST **16:30 자동 실행** (=07:30 UTC)
- Actions 탭에서 매일 새 실행 확인
- 실패 시 이메일 알림 (GitHub 기본 설정)

## 셋업 완료 체크리스트

- [ ] GitHub 계정
- [ ] `jinwoo-quant-auto` 저장소 (Public)
- [ ] 4개 파일 업로드: `score_v36.py`, `requirements.txt`, `README.md`, `.github/workflows/daily.yml`
- [ ] Actions 권한 (Read and write)
- [ ] Pages Source: GitHub Actions
- [ ] 첫 수동 실행 성공
- [ ] Pages URL 접속 가능
- [ ] 모바일 북마크

## 문제 발생 시

### Actions 실행 실패
- Actions 탭 → 빨간 X 클릭 → 로그 확인
- 가장 흔한 원인: 권한 설정 누락 (4단계)

### Pages 접속 안 됨
- 첫 실행 후 1~2분 대기
- Settings → Pages에서 URL 확인

### FDR 데이터 수집 실패
- KRX 거래일 아닐 때 발생 가능 (주말·공휴일)
- 다음 거래일 자동 재시도

## 다음 단계

운영 1~2주 후 (2026-06):
- 등급 변동 패턴 누적
- 실제 매매 결과 검증
- v3.7 BAB·NOA 모듈 추가 검토
