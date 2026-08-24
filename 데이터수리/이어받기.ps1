# KIS 전수 수집 이어받기 (2026-07-28)
# 패치로 네트워크 예외는 6회 재시도하지만, 그래도 죽으면 자동으로 다시 띄운다.
# 체크포인트 기반이라 몇 번을 다시 돌려도 이미 받은 코드는 건너뛴다.
$ErrorActionPreference = "Continue"
Set-Location -LiteralPath $PSScriptRoot
for ($i = 1; $i -le 20; $i++) {
    Write-Host ""
    Write-Host "===== 시도 $i / 20 =====" -ForegroundColor Cyan
    py collect_kis_monthly.py
    if ($LASTEXITCODE -eq 0) {
        Write-Host "정상 종료 (exit 0). 더 돌리지 않습니다." -ForegroundColor Green
        break
    }
    Write-Host "비정상 종료 (exit $LASTEXITCODE). 70초 후 이어받기..." -ForegroundColor Yellow
    Start-Sleep -Seconds 70   # KIS 토큰 발급 분당 1회 제한 회피
}
Write-Host ""
py collect_kis_monthly.py --report
