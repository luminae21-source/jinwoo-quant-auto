# 공개저장소_재생성.ps1 — jinwoo-quant-auto 를 히스토리 없이 새로 만든다
#
# 왜
#   연구 문서 96개를 추적에서 내렸지만 과거 커밋에는 그대로 남아 있다.
#   git rm 은 "앞으로 안 올린다"일 뿐, 이미 올라간 것을 지우지 않는다.
#   저장소를 지우고 다시 만드는 것이 유일하게 확실한 방법이다.
#
# 무엇이 올라가나
#   공개파일목록.txt 에 적힌 197개만. 목록에 없으면 절대 올라가지 않는다.
#   (파이프라인 .py / docs/ / 원자료 csv / README / 워크플로)
#
# 무엇이 사라지나
#   Actions 실행 기록, Issues, 커밋 히스토리. Pages 주소는 그대로.
#   ★ Secrets(DART_API_KEY)도 사라진다 — 다시 넣어야 한다.
#     키는 강화키트\재무_APIKEY.txt 에 있다.
#
param([switch]$Yes)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

# 같은 PowerShell 창에서 금고_백업.ps1 을 먼저 돌렸다면 GIT_DIR 이 .git-vault 로
# 남아 있다. 그대로 두면 여기의 git init 이 공개 저장소가 아니라 금고를 건드린다.
Remove-Item Env:GIT_DIR       -ErrorAction SilentlyContinue
Remove-Item Env:GIT_WORK_TREE -ErrorAction SilentlyContinue

$url  = "https://github.com/luminae21-source/jinwoo-quant-auto.git"
$list = Join-Path $root "공개파일목록.txt"

if (-not (Test-Path $list)) { Write-Host "공개파일목록.txt 가 없습니다." -ForegroundColor Red; exit 1 }
$n = (Get-Content $list | Where-Object { $_.Trim() -ne "" }).Count

Write-Host "공개 저장소 재생성" -ForegroundColor Cyan
Write-Host ("-" * 58)
Write-Host "올릴 파일: $n 개 (공개파일목록.txt 기준 — 목록에 없으면 절대 안 올라감)"
Write-Host "원격      : $url"
Write-Host ""
Write-Host "먼저 GitHub 에서 아래를 끝내셨나요?" -ForegroundColor Yellow
Write-Host "  1. 기존 jinwoo-quant-auto 삭제 (Settings -> Danger Zone -> Delete)"
Write-Host "  2. 같은 이름으로 새로 생성 (Public, README/gitignore/license 전부 체크 해제)"
Write-Host ""

if (-not $Yes) {
    $a = Read-Host "위 둘을 마쳤으면 yes 를 입력하세요"
    if ($a -ne "yes") { Write-Host "중단합니다." -ForegroundColor DarkGray; exit 0 }
}

# 1) 옛 .git 을 지우지 않고 옆으로 치운다 (되돌릴 여지를 남긴다)
if (Test-Path ".git") {
    git rev-parse --verify HEAD *> $null
    if ($LASTEXITCODE -eq 0) {
        $bak = "_보관\git_공개_구본_" + (Get-Date -Format "yyyyMMdd_HHmm")
        New-Item -ItemType Directory -Force -Path "_보관" | Out-Null
        Move-Item ".git" $bak
        Write-Host "`n[1/5] 옛 히스토리를 $bak 로 치웠습니다 (삭제 아님)"
    } else {
        Write-Host "`n[1/5] 커밋 없는 빈 .git 입니다. 그대로 다시 씁니다."
    }
}

# 2) 빈 저장소로 다시 시작
git init -b main | Out-Null
if (-not (Test-Path ".git")) {
    Write-Host "  .git 이 만들어지지 않았습니다. 중단합니다." -ForegroundColor Red
    exit 1
}
git remote add origin $url
New-Item -ItemType Directory -Force -Path ".git\info" | Out-Null

# 내린 194개를 .git\info\exclude 에 적어 실수로 다시 딸려가지 않게 한다.
# .gitignore 가 아니라 info\exclude 인 이유: 이 목록 자체가 연구 목록이라
# 공개 저장소에 올라가면 안 된다. info\exclude 는 절대 push 되지 않는다.
if (Test-Path "공개에서_내린_목록.txt") {
    Copy-Item "공개에서_내린_목록.txt" ".git\info\exclude" -Force
}
Write-Host "[2/5] 새 저장소 초기화 (+ 내린 목록을 info\exclude 에 고정)"

# 3) 목록에 있는 것만 스테이징 — .gitignore 를 무시하고 목록을 절대 기준으로 삼는다
# -f 로 .gitignore 를 무시한다. 올릴 것은 공개파일목록.txt 가 정하지 .gitignore 가 정하지 않는다.
# (docs/v36_scores_latest.csv 처럼 옛 규칙에 걸려 조용히 빠지는 파일이 있었다.)
git add -f --pathspec-from-file="공개파일목록.txt"
$staged = (git diff --cached --name-only | Measure-Object -Line).Lines
Write-Host "[3/5] 스테이징 $staged 개"
if ($staged -ne $n) {
    Write-Host "  ! 목록($n)과 스테이징($staged)이 다릅니다. 확인 후 진행하세요." -ForegroundColor Red
    git status --short
    exit 1
}

# 4) 단일 커밋
git -c user.name="진우" -c user.email="luminae21@gmail.com" `
    commit -q -m "진우퀀트 자동 대시보드 — 배포 파이프라인

이 저장소는 매일 16:30 KST 점수 갱신과 GitHub Pages 배포만 담당한다.
매매룰·팩터명세·실전기록 등 연구 문서는 비공개 금고에 있다."
Write-Host "[4/5] 커밋 완료"

# 5) 올리기
Write-Host "[5/5] 올리는 중..."
git push -u origin main

Write-Host ""
Write-Host ("-" * 58)
Write-Host "완료. 남은 GitHub 설정 3가지:" -ForegroundColor Green
Write-Host "  a) Settings -> Secrets and variables -> Actions -> New secret"
Write-Host "     이름 DART_API_KEY / 값은 강화키트\재무_APIKEY.txt"
Write-Host "  b) Settings -> Pages -> Source 를 'GitHub Actions' 로"
Write-Host "  c) Actions 탭 -> 워크플로 활성화 -> Run workflow 수동 1회"
Write-Host ""
Write-Host "옛 히스토리는 _보관\ 안에 있습니다. 확인 끝나면 지우셔도 됩니다."
