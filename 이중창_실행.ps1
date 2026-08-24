# =====================================================================
#  이중창_실행.ps1 — 창 시작점 × 가격원천 × 마스크 행렬 백테 (2026-07-28)
#
#  왜: 진우 결정 "둘 다 산출해서 차이를 본다" (2008~2026 vs 2010~2026,
#      파라미터 동일). 여기에 B-1o 의 마스크 유/무를 곱한다.
#
#  파라미터는 6칸 전부 동일하다. 바뀌는 건 딱 셋이다:
#      --start   창 시작점
#      --price   가격 원천
#      --mask    마스크 적용 여부
#
#  쓰는 법 (진우퀀트 폴더에서):
#      powershell -ExecutionPolicy Bypass -File .\이중창_실행.ps1
#      powershell -ExecutionPolicy Bypass -File .\이중창_실행.ps1 -Signal momentum
#      powershell -ExecutionPolicy Bypass -File .\이중창_실행.ps1 -Quick   # 부트스트랩 생략
# =====================================================================

param(
    [string]$Signal = "multifactor",
    [switch]$Quick,
    [switch]$SkipPanel
)

$ErrorActionPreference = "Continue"
$stamp = Get-Date -Format "yyyyMMdd_HHmm"
$dir   = "이중창_$stamp"
New-Item -ItemType Directory -Path $dir -Force | Out-Null

$MASKS = "--mask", "_패널마스크_v1.csv", "--mask", "_출처불일치_v1.csv"
$boot  = if ($Quick) { @("--no-boot") } else { @("--boot", "200") }

# 6칸: (창, 원천, 마스크여부, 라벨)
$CELLS = @(
    @{ start="2008-01"; price="full"; mask=$false; tag="2008_full"       },
    @{ start="2008-01"; price="kis";  mask=$false; tag="2008_kis"        },
    @{ start="2008-01"; price="kis";  mask=$true;  tag="2008_kis_masked" },
    @{ start="2010-01"; price="full"; mask=$false; tag="2010_full"       },
    @{ start="2010-01"; price="kis";  mask=$false; tag="2010_kis"        },
    @{ start="2010-01"; price="kis";  mask=$true;  tag="2010_kis_masked" }
)

Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " 이중창 백테 행렬 · 6칸 · signal=$Signal" -ForegroundColor Cyan
Write-Host " 결과 폴더: $dir" -ForegroundColor Cyan
Write-Host "======================================================" -ForegroundColor Cyan

# ── 멀티팩터면 신호 패널도 원천별로 다시 만들어야 한다.
#    (div/bp/ep 는 전부 분모가 가격이므로 원천이 바뀌면 신호도 바뀐다)
if ($Signal -eq "multifactor" -and -not $SkipPanel) {
    foreach ($pr in @("cache", "kis")) {
        foreach ($mk in @($false, $true)) {
            if ($pr -eq "cache" -and $mk) { continue }
            $sfx = "$pr" + $(if ($mk) { "_masked" } else { "" })
            $outp = "$dir\panel_$sfx.csv"
            $args = @("build_style_panel.py", "--price", $pr, "--start", "2006-01", "--out", $outp)
            if ($mk) { $args += $MASKS }
            Write-Host ""
            Write-Host "[패널] $sfx" -ForegroundColor Yellow
            & py @args 2>&1 | Tee-Object -FilePath "$dir\log_panel_$sfx.txt"
        }
    }
    Write-Host ""
    Write-Host "⚠️ 주의: 운용사양_백테.py 는 mini_style_panel.csv 를 이름으로 찾습니다." -ForegroundColor Yellow
    Write-Host "   원천별 패널로 돌리려면 해당 panel_*.csv 를 mini_style_panel.csv 로" -ForegroundColor Yellow
    Write-Host "   복사한 뒤 각 칸을 돌려야 합니다. 아래 루프는 그렇게 합니다." -ForegroundColor Yellow
    if (Test-Path "감사\미니샘플2\mini_style_panel.csv") {
        Copy-Item "감사\미니샘플2\mini_style_panel.csv" "$dir\mini_style_panel.원본백업.csv" -Force
        Write-Host "   원본 패널 백업: $dir\mini_style_panel.원본백업.csv" -ForegroundColor Green
    }
}

foreach ($c in $CELLS) {
    $tag = $c.tag
    Write-Host ""
    Write-Host "=== [$tag] start=$($c.start) price=$($c.price) mask=$($c.mask) ===" -ForegroundColor Green

    if ($Signal -eq "multifactor" -and -not $SkipPanel) {
        $sfx = $(if ($c.price -eq "kis") { "kis" } else { "cache" }) + $(if ($c.mask) { "_masked" } else { "" })
        $src = "$dir\panel_$sfx.csv"
        if (Test-Path $src) { Copy-Item $src "감사\미니샘플2\mini_style_panel.csv" -Force }
        else { Write-Host "  ⚠️ 패널 없음: $src — 이 칸 건너뜀" -ForegroundColor Red; continue }
    }

    $args = @("운용사양_백테.py", "--start", $c.start, "--price", $c.price,
              "--signal", $Signal, "--out", "$dir\결과_$tag.md") + $boot
    if ($c.mask) { $args += $MASKS }
    & py @args 2>&1 | Tee-Object -FilePath "$dir\log_$tag.txt"
}

# ── 원본 패널 복원 (다른 작업이 깨지지 않게)
if (Test-Path "$dir\mini_style_panel.원본백업.csv") {
    Copy-Item "$dir\mini_style_panel.원본백업.csv" "감사\미니샘플2\mini_style_panel.csv" -Force
    Write-Host ""
    Write-Host "원본 mini_style_panel.csv 복원 완료" -ForegroundColor Green
}

Write-Host ""
Write-Host "======================================================" -ForegroundColor Cyan
Write-Host " 완료 → $dir" -ForegroundColor Cyan
Get-ChildItem $dir -Filter "결과_*.md" | ForEach-Object { Write-Host ("   " + $_.Name) }
Write-Host ""
Write-Host " 6칸을 나란히 놓고 읽으세요. 한 칸만 보고 결론 내지 마십시오." -ForegroundColor Yellow
Write-Host " 창(2008 vs 2010) 차이와 원천(full vs kis) 차이를 분리해서 봐야 합니다." -ForegroundColor Yellow
