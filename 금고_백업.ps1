# 금고_백업.ps1 — 연구 자료 비공개 백업 (v3)
#
# v3 에서 고친 것
#   v2 는 경로를 정규식으로 걸렀는데 한글 폴더에서 헛돌았고,
#   Get-Item 이 숨김 파일(desktop.ini)에서 멈췄다.
#   v3 는 정규식을 버리고 '경로 조각 이름 비교'로 바꿨다. 실패할 여지가 없다.
#   제외할 폴더 이름은 금고_제외폴더.txt 에서 읽는다.
#
# 무엇을 담나
#   이 폴더 전부. 아래만 뺀다.
#     금고_제외폴더.txt 에 적힌 폴더 (외부 논문 PDF·임시·백업)
#     20MB 초과 파일 (pykrx·DART 로 다시 받을 수 있는 원자료)
#     .pdf .gz .bin .aa .db .zip .7z / *.bak_* / API 키
#
# 쓰는 법
#   처음 한 번:  .\금고_백업.ps1 -RepoUrl https://github.com/luminae21-source/jinwoo-quant-vault.git
#   그 다음부터: .\금고_백업.ps1
#
param([string]$RepoUrl = "", [switch]$Force)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# git 은 정상 진행 상황도 stderr 로 쓴다. 작업스케줄러처럼 출력이 파일로 넘어가면
# PowerShell 이 그걸 '오류'로 판정해 스크립트를 죽인다. 그 판정을 끈다.
if (Test-Path variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

# 출력이 파일로 넘어갈 때 파이썬이 cp949 를 쓰다가 '—' 같은 글자에서 죽는다.
# UTF-8 로 못 박는다.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

Write-Host "금고 백업 v3 — $root" -ForegroundColor Cyan
Write-Host ("-" * 58)

if (-not (Test-Path ".git-vault")) {
    git --git-dir=.git-vault --work-tree=. init -b main | Out-Null
    Write-Host "금고 저장소를 새로 만들었습니다."
}
$env:GIT_DIR = ".git-vault"
$env:GIT_WORK_TREE = "."
# 이 창에서 다른 git 명령을 이어 쓰더라도 금고를 건드리지 않도록,
# 스크립트가 끝날 때(중간에 exit 해도) 반드시 되돌린다.
$global:__vaultCleanup = {
    Remove-Item Env:GIT_DIR       -ErrorAction SilentlyContinue
    Remove-Item Env:GIT_WORK_TREE -ErrorAction SilentlyContinue
}
Register-EngineEvent PowerShell.Exiting -Action $global:__vaultCleanup | Out-Null
trap { & $global:__vaultCleanup; break }

# 금고는 '있는 그대로' 보관한다. 줄바꿈을 CRLF 로 바꾸지 않는다(경고 수백 줄의 원인).
# quotepath 를 끄면 git 이 한글 경로를 8진수 이스케이프 대신 그대로 출력한다.
git config core.autocrlf false
git config core.quotepath false

Remove-Item ".git-vault\index.lock",".git-vault\HEAD.lock" -Force -ErrorAction SilentlyContinue
Get-ChildItem ".git-vault\objects" -Recurse -Filter "tmp_obj_*" -ErrorAction SilentlyContinue |
    Remove-Item -Force -ErrorAction SilentlyContinue

# ── 1) 색인·허브·백서 먼저 최신으로 ──────────────────────────
Write-Host "`n[1/5] 색인·허브·백서 갱신" -ForegroundColor Yellow
# 윈도우의 python 은 Microsoft Store 로 보내는 0바이트 껍데기일 때가 있다
# (C:\WINDOWS\system32\python). 그건 실행 파일이 아니라 걸러낸다.
$py = $null
foreach ($c in @("py","python3","python")) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if (-not $cmd) { continue }
    $src = $cmd.Source
    if (-not $src) { continue }
    if ($src -like "*WindowsApps*") { continue }
    if ((Get-Item -LiteralPath $src -Force -ErrorAction SilentlyContinue).Length -eq 0) { continue }
    $py = $src; break
}
if (-not $py) {
    Write-Host "  ! 쓸 수 있는 python 이 없습니다. 갱신은 건너뛰고 백업만 합니다." -ForegroundColor DarkYellow
    Write-Host "    (색인·허브·백서는 이미 만들어져 있으니 백업 자체엔 지장 없습니다.)" -ForegroundColor DarkGray
} elseif (Test-Path "연구보존_갱신.py") {
    Write-Host "  python: $py" -ForegroundColor DarkGray
    & $py "연구보존_갱신.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  ! 갱신 실패. 백업은 계속합니다." -ForegroundColor DarkYellow
    }
}

# ── 2) 담을 파일 목록 만들기 ────────────────────────────────
Write-Host "`n[2/5] 담을 파일 고르는 중..." -ForegroundColor Yellow

# 제외 폴더: 이름을 그대로 비교한다 (정규식 아님 → 한글에서 헛돌지 않는다)
$skipDirs = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($d in @(".git",".git-vault","_to_delete","__pycache__","node_modules")) { [void]$skipDirs.Add($d) }
if (Test-Path "금고_제외폴더.txt") {
    Get-Content "금고_제외폴더.txt" -Encoding UTF8 |
        Where-Object { $_.Trim() -ne "" -and -not $_.StartsWith("#") } |
        ForEach-Object { [void]$skipDirs.Add($_.Trim()) }
}
Write-Host "  제외 폴더 $($skipDirs.Count) 개: $(($skipDirs -join ', '))"

$skipExt  = @(".pdf",".gz",".bin",".aa",".db",".zip",".7z",".pyc")
$skipFile = @("desktop.ini","thumbs.db",".ds_store")

# 인증정보 파일은 금고에도 넣지 않는다. 백업은 '다시 만들 수 있는 것'을 위한 것이고,
# 키는 다시 발급받는 것이지 보관하는 것이 아니다.
if (Test-Path "금고_제외파일.txt") {
    Get-Content "금고_제외파일.txt" -Encoding UTF8 |
        Where-Object { $_.Trim() -ne "" -and -not $_.StartsWith("#") } |
        ForEach-Object { $skipFile += $_.Trim().ToLower() }
}
Write-Host "  제외 파일 $($skipFile.Count) 개 (인증정보 포함)"
$SizeLimit = 20MB

$prefix = $root.TrimEnd('\') + '\'
$sel = Get-ChildItem -Path $root -Recurse -File -ErrorAction SilentlyContinue | Where-Object {
    $rel = $_.FullName.Substring($prefix.Length)
    $keep = $true
    foreach ($seg in $rel.Split([char]'\')) { if ($skipDirs.Contains($seg)) { $keep = $false } }
    if ($keep -and $skipExt -contains $_.Extension.ToLower())      { $keep = $false }
    if ($keep -and $skipFile -contains $_.Name.ToLower())          { $keep = $false }
    if ($keep -and $_.Name -match '\.bak_')                        { $keep = $false }
    if ($keep -and $_.Name -match '(?i)apikey|api_key|authkey|secret|credential|(^|_)key(\.|$)|token' -and $_.Extension -notin @(".py",".md",".html",".bat",".ps1")) { $keep = $false }
    if ($keep -and $_.Length -gt $SizeLimit)                       { $keep = $false }
    $keep
}
$files = $sel | ForEach-Object { $_.FullName.Substring($prefix.Length).Replace('\','/') }
$mb = [math]::Round((($sel | Measure-Object -Property Length -Sum).Sum) / 1MB, 1)
Write-Host "  대상 $($files.Count) 개 · $mb MB"
if ($files.Count -lt 1500) {
    Write-Host "  🔴 너무 적습니다(1500개 미만). 무언가 잘못 걸러졌습니다. 중단합니다." -ForegroundColor Red
    exit 1
}

$listPath = Join-Path $env:TEMP "vault_pathspec.txt"
[System.IO.File]::WriteAllLines($listPath, $files, (New-Object System.Text.UTF8Encoding($false)))

# ── 3) 강제 스테이징 (.gitignore 를 거치지 않는다) ──────────
Write-Host "`n[3/5] 스테이징 (수천 개라 1~3분 걸립니다)" -ForegroundColor Yellow
# 색인을 비우고 목록대로 다시 채운다 → 커밋 내용이 항상 위 목록과 일치한다.
git rm -r --cached -q --ignore-unmatch . 2>&1 | Out-Null
git add -f --pathspec-from-file="$listPath"
$tracked = (git ls-files | Measure-Object -Line).Lines
Write-Host "  금고에 담긴 파일 $tracked 개"

# ── 3b) 안전 점검 ───────────────────────────────────────────
$must = @("진우퀀트_v37_2_매매룰.md","진우퀀트_v37_팩터명세.md","진우퀀트_v37_2_실전기록.md",
          "백서_빌더/진우퀀트_백서.md","강화키트/진우퀀트_허브_자립형.html")
$miss = @()
foreach ($m in $must) {
    git ls-files --error-unmatch -- $m 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { $miss += $m }
}
# 주의: git ls-files 출력을 PowerShell 문자열로 걸러선 안 된다.
# 한글 경로가 8진수로 이스케이프돼 나오면 -like "*.md" 가 전부 빗나간다.
# 세는 일은 git 에게 맡긴다.
$mdCount = (git ls-files -- "*.md" | Measure-Object -Line).Lines
Write-Host "  금고 안 .md 문서: $mdCount 개"
if ($miss.Count -gt 0 -or $mdCount -lt 300) {
    Write-Host "`n  🔴 연구 문서가 제대로 안 들어갔습니다. 중단합니다." -ForegroundColor Red
    $miss | ForEach-Object { Write-Host "     없음: $_" }
    exit 1
}
Write-Host "  ✅ 핵심 문서 5종 확인 (매매룰·팩터명세·실전기록·백서·허브)" -ForegroundColor Green

# 마지막 관문: 인증정보가 한 개라도 색인에 있으면 커밋하지 않는다.
$leak = @()
foreach ($k in @(".dart_key",".kis_key",".kis_token","dart_config.json","ecos_key.txt",
                 "jq_kakao_token.json","jq_kakao_config.txt","krx_authkey.txt","naver_api.json")) {
    $found = git ls-files -- "*$k" 
    if ($found) { $leak += $found }
}
if ($leak.Count -gt 0) {
    Write-Host "`n  🔴 인증정보가 색인에 들어갔습니다. 커밋하지 않고 중단합니다:" -ForegroundColor Red
    $leak | ForEach-Object { Write-Host "     $_" }
    exit 1
}
Write-Host "  ✅ 인증정보 유입 없음" -ForegroundColor Green

# ── 4) 커밋 ─────────────────────────────────────────────────
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[4/5] 바뀐 것이 없습니다. 커밋 건너뜀." -ForegroundColor DarkGray
} else {
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
    git -c user.name="진우" -c user.email="luminae21@gmail.com" `
        commit -q -m "금고 백업 $stamp — 추적 $tracked 개 (문서 $mdCount)"
    Write-Host "`n[4/5] 커밋 완료"
}

# ── 5) 올리기 ───────────────────────────────────────────────
if (-not ((git remote) -contains "vault")) {
    if ($RepoUrl -eq "") {
        Write-Host "`n[5/5] 원격이 없습니다. -RepoUrl 로 주소를 주세요." -ForegroundColor Red
        exit 1
    }
    git remote add vault $RepoUrl
}

Write-Host "[5/5] 올리는 중 (처음에는 몇 분 걸립니다)" -ForegroundColor Yellow
if ($Force) {
    # 금고는 '이 폴더의 현재 전체 스냅샷'이다. PC 한 대가 유일한 정본이므로 거울처럼 덮어쓴다.
    # fetch 로 원격 상태를 최신화한 뒤 밀어넣는다. 버려지는 커밋이 있으면 먼저 보여준다.
    git fetch vault 2>&1 | Out-Null
    $lost = git log --format='   %h %ad | %s' --date=format:'%m-%d %H:%M' "main..vault/main" 2>&1
    if ($lost) {
        Write-Host "  원격에서 덮어쓰는 커밋:" -ForegroundColor DarkYellow
        $lost | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
    }
    git push --force-with-lease -u vault main
} else {
    git push -u vault main
}
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "🔴 push 실패." -ForegroundColor Red
    git fetch vault 2>&1 | Out-Null
    $c = (git rev-list --left-right --count vault/main...main) -split "\s+"
    Write-Host "   원격에만 있는 커밋 $($c[0])개 · 로컬에만 있는 커밋 $($c[1])개"
    if ([int]$c[0] -gt 0) {
        Write-Host "   원격 쪽 커밋:" -ForegroundColor DarkGray
        git log --format='     %h %ad | %s' --date=format:'%m-%d %H:%M' "main..vault/main"
        Write-Host ""
        Write-Host "   전부 '🤖 자동 갱신' 이면 금고에서 GitHub Actions 가 돌고 있는 것입니다." -ForegroundColor Yellow
        Write-Host "   금고 Settings -> Actions -> General -> Disable actions 로 끄고," -ForegroundColor Yellow
        Write-Host "   아래처럼 한 번 덮어쓰면 됩니다:" -ForegroundColor Yellow
        Write-Host "     .\금고_백업.ps1 -Force" -ForegroundColor Cyan
    }
    exit 1
}

Write-Host ""
Write-Host ("-" * 58)
Write-Host "✅ 금고 백업 완료 — $tracked 개 (문서 $mdCount)" -ForegroundColor Green
Write-Host "   GitHub 에서 jinwoo-quant-vault 를 열어 진우퀀트_v37_2_매매룰.md 가"
Write-Host "   눈에 보이는지 직접 확인하세요. 그게 확인돼야 공개 저장소를 지웁니다."

# 환경변수 원복 — 같은 창에서 공개저장소_재생성.ps1 을 이어 돌려도 안전하게.
& $global:__vaultCleanup
