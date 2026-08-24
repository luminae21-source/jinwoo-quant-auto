# 연구보존_자동등록.ps1 — 매일 밤 10시 자동 실행 등록
#
# 무엇을 등록하나
#   연구보존_자동.bat  →  금고_백업.ps1 -Force
#   즉 색인·허브·백서 갱신 + 금고(GitHub Private) 백업까지 한 번에.
#
# 왜 schtasks 가 아니라 Register-ScheduledTask 인가
#   'PC가 꺼져 있어 놓친 실행을 다음 부팅 때 따라잡기'(StartWhenAvailable)를
#   schtasks 기본 문법으로는 켤 수 없다. 진우님 PC는 밤에 꺼져 있을 수 있으니
#   이 옵션이 없으면 그날 백업이 통째로 건너뛰어진다.
#
# 해제:  .\연구보존_자동등록.ps1 -Remove

param([switch]$Remove, [string]$At = "22:00")

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $root

$name = "JinwooQuant_ResearchIndex"

if ($Remove) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "해제 완료: $name" -ForegroundColor Green
    exit 0
}

$target = Join-Path $root "연구보존_자동.bat"
if (-not (Test-Path $target)) {
    Write-Host "연구보존_자동.bat 이 없습니다." -ForegroundColor Red
    exit 1
}

$action  = New-ScheduledTaskAction -Execute $target -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Daily -At $At
$set     = New-ScheduledTaskSettingsSet `
             -StartWhenAvailable `
             -AllowStartIfOnBatteries `
             -DontStopIfGoingOnBatteries `
             -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
             -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger `
    -Settings $set -Force `
    -Description "진우퀀트 연구 색인·허브·백서 갱신 + 금고 백업 (매일 $At)" | Out-Null

Write-Host "등록 완료" -ForegroundColor Green
Write-Host ("-" * 58)
Write-Host "  작업 이름 : $name"
Write-Host "  실행 시각 : 매일 $At"
Write-Host "  실행 내용 : 연구보존_자동.bat  ->  금고_백업.ps1 -Force"
Write-Host "  놓친 실행 : 다음에 PC 켜질 때 자동으로 따라잡음"
Write-Host "  로그      : 연구보존_자동_log.txt"
Write-Host ""
Write-Host "지금 한 번 시험 실행:" -ForegroundColor Yellow
Write-Host "  Start-ScheduledTask -TaskName $name" -ForegroundColor Cyan
Write-Host "상태 확인:" -ForegroundColor Yellow
Write-Host "  Get-ScheduledTaskInfo -TaskName $name" -ForegroundColor Cyan
Write-Host "해제:" -ForegroundColor Yellow
Write-Host "  .\연구보존_자동등록.ps1 -Remove" -ForegroundColor Cyan
