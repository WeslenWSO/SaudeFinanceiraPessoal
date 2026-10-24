# Instala Playwright + Chromium (relatório PDF Análises). Execute na raiz do repo.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Instalando pacote playwright..." -ForegroundColor Cyan
python -m pip install "playwright==1.62.0"

Write-Host "Baixando Chromium (~190 MB). Pode demorar alguns minutos..." -ForegroundColor Cyan
python -m playwright install chromium

Write-Host "Verificando..." -ForegroundColor Cyan
python -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop(); print('OK: Chromium funcionando.')"

Write-Host "Concluido." -ForegroundColor Green
