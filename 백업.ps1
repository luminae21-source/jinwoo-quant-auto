# =====================================================================
#  진우퀀트 백업 스크립트  (2026-07-28)
#
#  쓰는 법 (PowerShell, 진우퀀트 폴더에서):
#     powershell -ExecutionPolicy Bypass -File .\백업.ps1 -CheckOnly
#     powershell -ExecutionPolicy Bypass -File .\백업.ps1 -Dest E:\
#
#     -Dest       백업 파일을 놓을 곳 (USB / 외장하드 / 클라우드 동기화 폴더)
#     -Full       대용량 CSV까지 전부 (기본은 "다시 만들기 비싼 것"만)
#     -CheckOnly  백업 안 하고 비밀값 점검만
#
#  이 스크립트는 API 키 파일을 백업에 절대 넣지 않습니다.
#  키는 USB에조차 넣지 않는 게 원칙입니다 - 키는 재발급이 되지만
#  유출된 키는 회수가 안 됩니다.
# =====================================================================

param(
    [string]$Dest = "",
    [switch]$Full,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $ROOT) { $ROOT = (Get-Location).Path }
if (-not (Test-Path (Join-Path $ROOT "백서_빌더"))) { $ROOT = (Get-Location).Path }
Write-Host "대상 폴더: $ROOT" -ForegroundColor Cyan

# ---------------------------------------------------------------- 비밀값 목록
$SECRETS = @(
    ".kis_key", ".kis_token", ".kis_key.json", ".dart_key",
    "ecos_key.txt", "krx_authkey.txt",
    "jq_kakao_token.json", "jq_kakao_config.txt",
    "jq_kakao_auth_log.txt", "jq_kakao_log.txt",
    "naver_api.json", "재무_APIKEY.txt", "진우_KIS키.json",
    ".env"
)

Write-Host ""
Write-Host "===== 1. 비밀값 점검 =====" -ForegroundColor Yellow

$found = @()
foreach ($s in $SECRETS) {
    $hits = Get-ChildItem -LiteralPath $ROOT -Recurse -Force -File -Filter $s -ErrorAction SilentlyContinue
    foreach ($h in $hits) {
        $rel = $h.FullName.Substring($ROOT.Length).TrimStart('\')
        $found += $rel
        Write-Host ("  키파일 존재: {0}" -f $rel)
    }
}
if ($found.Count -eq 0) { Write-Host "  (키 파일 없음)" }

Write-Host ""
if (Test-Path (Join-Path $ROOT ".git")) {
    Push-Location $ROOT
    # 2026-08-11: template/example 은 의도적으로 올린 양식이라 제외 (오탐 수정 —
    # 진우_KIS키.json.template 이 걸렸었음. 내용 검사로 실제 값 없음 확인 완료)
    $tracked = @(git ls-files 2>$null | Select-String -Pattern "kis_key|kis_token|dart_key|authkey|ecos_key|APIKEY|kakao_token|kakao_config|naver_api|진우_KIS키" | Where-Object { $_ -notmatch "\.template$|\.example$" })
    Pop-Location
    if ($tracked.Count -gt 0) {
        Write-Host "  [!!] git 이 아래 파일을 추적하고 있습니다 - 공개 저장소로 나갔을 수 있습니다:" -ForegroundColor Red
        $tracked | ForEach-Object { Write-Host ("      " + $_) -ForegroundColor Red }
        Write-Host "  -> 즉시: 해당 키 전부 재발급 + git 히스토리 제거(git filter-repo)" -ForegroundColor Red
    } else {
        Write-Host "  [OK] git 이 추적 중인 키 파일 없음" -ForegroundColor Green
    }

    $gi = Join-Path $ROOT ".gitignore"
    $need = @(".kis_key", ".kis_token", "ecos_key.txt", "krx_authkey.txt",
              "jq_kakao_token.json", "jq_kakao_config.txt", "재무_APIKEY.txt")
    if (Test-Path $gi) {
        $txt = Get-Content $gi -Raw -Encoding UTF8
        $missing = $need | Where-Object { $txt -notmatch [regex]::Escape($_) }
        if ($missing.Count -gt 0) {
            Write-Host "  [!] 루트 .gitignore 에 규칙이 없는 키 파일:" -ForegroundColor Yellow
            $missing | ForEach-Object { Write-Host ("      " + $_) -ForegroundColor Yellow }
        } else {
            Write-Host "  [OK] .gitignore 가 키 파일을 덮고 있음" -ForegroundColor Green
        }
    }
} else {
    Write-Host "  (git 저장소 아님)"
}

if ($CheckOnly) { Write-Host ""; Write-Host "점검만 하고 종료합니다."; exit 0 }

if (-not $Dest) {
    Write-Host ""
    Write-Host "[X] -Dest 를 안 주셨습니다. 예: -Dest E:\  (USB 드라이브)" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $Dest)) {
    Write-Host "[X] 대상 경로가 없습니다: $Dest" -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------- 스테이징
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$stage = Join-Path $env:TEMP "jq_backup_$stamp"
New-Item -ItemType Directory -Path $stage -Force | Out-Null

Write-Host ""
Write-Host "===== 2. 백업 대상 모으는 중 =====" -ForegroundColor Yellow

$XD = @("__pycache__", "__jqpyc__", ".git", "_보관", "_archive", "node_modules", ".vscode", ".idea")
if (-not $Full) { $XD += @("_백업", "카드뉴스") }

$XF = @($SECRETS) + @("*.pyc", "*.log", "Thumbs.db", ".DS_Store")

$rcArgs = @($ROOT, $stage, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:1", "/W:1")
$rcArgs += "/XD"; $rcArgs += $XD
$rcArgs += "/XF"; $rcArgs += $XF
if (-not $Full) {
    $rcArgs += @("종목일봉_30년_*.csv", "_일봉*.csv", "kospi_pit_daily.csv", "kosdaq_pit_daily.csv", "*_pykrx.csv", "*.db")
}
robocopy @rcArgs | Out-Null

# ---------------------------------------------------------------- 안전망
Write-Host "===== 3. 스테이징 재검사 (키가 섞였는지) =====" -ForegroundColor Yellow
$leak = @()
foreach ($s in $SECRETS) {
    $leak += Get-ChildItem -LiteralPath $stage -Recurse -Force -File -Filter $s -ErrorAction SilentlyContinue
}
if ($leak.Count -gt 0) {
    Write-Host "  [X] 키 파일이 스테이징에 들어왔습니다. 백업을 중단합니다:" -ForegroundColor Red
    $leak | ForEach-Object { Write-Host ("      " + $_.FullName) -ForegroundColor Red }
    Remove-Item -LiteralPath $stage -Recurse -Force
    exit 2
}
Write-Host "  [OK] 키 파일 0건 - 안전" -ForegroundColor Green

# ---------------------------------------------------------------- 목록/압축
$files = Get-ChildItem -LiteralPath $stage -Recurse -File
$mb = [math]::Round(($files | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host ("  파일 {0:N0}개 · {1} MB" -f $files.Count, $mb)

$manifest = Join-Path $stage "_백업목록_$stamp.txt"
"진우퀀트 백업 $stamp" | Out-File $manifest -Encoding UTF8
("원본: " + $ROOT) | Out-File $manifest -Append -Encoding UTF8
("파일 {0} · {1} MB" -f $files.Count, $mb) | Out-File $manifest -Append -Encoding UTF8
"" | Out-File $manifest -Append -Encoding UTF8
$files | Where-Object { $_.Length -gt 200KB } | Sort-Object Length -Descending |
    ForEach-Object { "{0,12:N0}  {1}" -f $_.Length, $_.FullName.Substring($stage.Length).TrimStart('\') } |
    Out-File $manifest -Append -Encoding UTF8

$zip = Join-Path $Dest "진우퀀트_백업_$stamp.zip"
Write-Host ""
Write-Host "===== 4. 압축 중 -> $zip =====" -ForegroundColor Yellow
Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $zip -CompressionLevel Optimal -Force

$h = Get-FileHash $zip -Algorithm SHA256
$zmb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Remove-Item -LiteralPath $stage -Recurse -Force

Write-Host ""
Write-Host "===== 완료 =====" -ForegroundColor Green
Write-Host ("  {0}" -f $zip)
Write-Host ("  {0} MB" -f $zmb)
Write-Host ("  SHA256 {0}" -f $h.Hash)
Write-Host ""
Write-Host "  이 SHA256 값을 어딘가에 적어두세요 (카톡 나에게 보내기 등)." -ForegroundColor Cyan
Write-Host "  나중에 복원할 때 파일이 안 깨졌는지 확인하는 유일한 방법입니다." -ForegroundColor Cyan
