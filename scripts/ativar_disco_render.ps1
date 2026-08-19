# Checklist: disco persistente de PDFs no Render (/var/data/media)
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host '=== Disco persistente (anexos PDF) ===' -ForegroundColor Cyan
Write-Host ''
Write-Host '1. render.yaml ja inclui:' -ForegroundColor Green
Write-Host '   - disk media-uploads, 10 GB, mount /var/data'
Write-Host '   - MEDIA_ROOT=/var/data/media'
Write-Host '   - RENDER=true'
Write-Host ''
Write-Host '2. No Render Dashboard:' -ForegroundColor Yellow
Write-Host '   Blueprints -> Sync  OU  FinancasPessoais -> Disks -> Add Disk'
Write-Host '   Mount: /var/data | 10 GB | env MEDIA_ROOT=/var/data/media'
Write-Host ''
Write-Host '3. Push + Manual Deploy (se ainda nao fez):' -ForegroundColor Yellow
Write-Host '   git push origin main'
Write-Host ''
Write-Host '4. Logs do deploy (esperado):' -ForegroundColor Yellow
Write-Host '   [startup] MEDIA_ROOT=/var/data/media exists=True writable=True'
Write-Host ''
Write-Host '5. Shell no Render (pos-deploy):' -ForegroundColor Yellow
Write-Host '   python manage.py verificar_anexos_media'
Write-Host '   python manage.py verificar_anexos_media --gravar-teste'
Write-Host '   # redeploy, depois:'
Write-Host '   python manage.py verificar_anexos_media --ler-teste'
Write-Host ''
Write-Host 'Dashboard: https://dashboard.render.com/web/srv-d9hui8jtqb8s73a97d70/disks' -ForegroundColor Magenta
Write-Host 'Guia: RENDER_DISCO_MEDIA.md' -ForegroundColor Magenta
Write-Host ''

if (Test-Path (Join-Path $Root 'render_db.url')) {
    Write-Host '6. Listar anexos faltando (banco producao, disco local vazio = normal no PC):' -ForegroundColor Yellow
    Write-Host '   Rode no Shell do Render, nao no PC.'
} else {
    Write-Host '6. Para listar anexos perdidos, use Shell do Render com verificar_anexos_media.' -ForegroundColor Yellow
}

Write-Host ''
Write-Host 'Anexos antigos perdidos: reenviar em Detalhes -> Anexar (nao ha recuperacao automatica).' -ForegroundColor Red
