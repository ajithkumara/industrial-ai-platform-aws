#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Quick-kill script: destroys all billable dev resources on both Azure and AWS.

.DESCRIPTION
    Run this when you are done working to stop all cloud costs immediately.
    - Azure: deletes rg-industrial-ai-dev resource group
    - AWS:   terraform destroy -auto-approve on dev-stage1 environment

.USAGE
    cd C:\Users\Laptop\Documents\workspace\industrial-ai-platform-aws
    .\scripts\destroy-dev-env.ps1

    # AWS only:
    .\scripts\destroy-dev-env.ps1 -SkipAzure

    # Azure only:
    .\scripts\destroy-dev-env.ps1 -SkipAWS
#>

param(
    [switch]$SkipAzure,
    [switch]$SkipAWS,
    [switch]$Force   # skip confirmation prompts
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Red
Write-Host "  IAP DEV ENVIRONMENT TEARDOWN" -ForegroundColor Red
Write-Host "  This will DESTROY all billable dev resources." -ForegroundColor Red
Write-Host "============================================================" -ForegroundColor Red
Write-Host ""

if (-not $Force) {
    $confirm = Read-Host "Type YES to proceed"
    if ($confirm -ne "YES") {
        Write-Host "Aborted." -ForegroundColor Yellow
        exit 0
    }
}

# ── AZURE ─────────────────────────────────────────────────────────────────────
if (-not $SkipAzure) {
    Write-Host ""
    Write-Host "[AZURE] Deleting resource group rg-industrial-ai-dev ..." -ForegroundColor Cyan

    $rgExists = az group exists --name rg-industrial-ai-dev 2>$null
    if ($rgExists -eq "true") {
        az group delete --name rg-industrial-ai-dev --yes --no-wait
        Write-Host "[AZURE] rg-industrial-ai-dev deletion started (runs in background)." -ForegroundColor Green
    } else {
        Write-Host "[AZURE] rg-industrial-ai-dev does not exist — already clean." -ForegroundColor Green
    }
} else {
    Write-Host "[AZURE] Skipped." -ForegroundColor DarkGray
}

# ── AWS ───────────────────────────────────────────────────────────────────────
if (-not $SkipAWS) {
    Write-Host ""
    Write-Host "[AWS] Running terraform destroy on dev-stage1 ..." -ForegroundColor Cyan

    $tfDir = Join-Path $PSScriptRoot "..\terraform\environments\dev-stage1"
    $tfDir = Resolve-Path $tfDir

    if (-not (Test-Path $tfDir)) {
        Write-Host "[AWS] Terraform dir not found: $tfDir" -ForegroundColor Red
    } else {
        Push-Location $tfDir
        try {
            $env:AWS_PROFILE = "iap-dev"
            terraform destroy -auto-approve
            Write-Host "[AWS] Destroy complete." -ForegroundColor Green
        } catch {
            Write-Host "[AWS] Terraform destroy failed: $_" -ForegroundColor Red
            Write-Host "[AWS] Check manually: https://ca-central-1.console.aws.amazon.com/billing" -ForegroundColor Yellow
        } finally {
            Pop-Location
        }
    }
} else {
    Write-Host "[AWS] Skipped." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  TEARDOWN COMPLETE" -ForegroundColor Green
Write-Host "  Verify billing:" -ForegroundColor Green
Write-Host "    AWS:   https://console.aws.amazon.com/billing" -ForegroundColor Green
Write-Host "    Azure: https://portal.azure.com/#blade/Microsoft_Azure_CostManagement" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
