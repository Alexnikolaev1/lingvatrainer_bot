# LINGVA.AI — деплой на Railway (PowerShell)
# Запуск: .\scripts\deploy_railway.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "=== LINGVA.AI Railway Deploy ===" -ForegroundColor Cyan

# 1. Railway CLI
if (-not (Get-Command railway -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Railway CLI..." -ForegroundColor Yellow
    npm install -g @railway/cli
}

# 2. Login
Write-Host "`n[1/4] Login to Railway (browser will open)..." -ForegroundColor Green
railway login

# 3. Init project (skip if already linked)
if (-not (Test-Path ".railway")) {
    Write-Host "`n[2/4] Creating Railway project..." -ForegroundColor Green
    railway init
} else {
    Write-Host "`n[2/4] Project already linked (.railway exists)" -ForegroundColor Green
}

# 4. Set variables (interactive)
Write-Host "`n[3/4] Set environment variables in Railway Dashboard:" -ForegroundColor Green
Write-Host @"

  TELEGRAM_BOT_TOKEN  = (from @BotFather)
  GEMINI_API_KEY      = (from aistudio.google.com)
  GROQ_API_KEY        = (from console.groq.com)
  GEMINI_MODEL        = gemini-2.5-flash-lite
  GROQ_LLM_MODEL      = llama-3.1-8b-instant
  DB_PATH             = /data/lingva.db

Also add Volume: mount /data (1 GB) in Railway Dashboard!

"@ -ForegroundColor White

$continue = Read-Host "Variables and Volume configured? (y/n)"
if ($continue -ne "y") {
    Write-Host "Configure at: https://railway.com/dashboard" -ForegroundColor Yellow
    exit 0
}

# 5. Deploy
Write-Host "`n[4/4] Deploying..." -ForegroundColor Green
railway up

Write-Host "`nDone! Check logs: railway logs" -ForegroundColor Cyan
Write-Host "Health: curl https://YOUR-APP.up.railway.app/health" -ForegroundColor Cyan
