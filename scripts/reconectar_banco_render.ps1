# Reconecta o Web Service SaudeFinanceira ao Postgres financas-db no Render.
#
# Modo manual (padrao): valida render_db.url, gera Internal URL e mostra o passo a passo.
# Modo automatico: define DATABASE_URL via API Render (precisa RENDER_API_KEY).
#
# Uso:
#   .\scripts\reconectar_banco_render.ps1
#   .\scripts\reconectar_banco_render.ps1 -AplicarViaApi
#   $env:RENDER_API_KEY = "rnd_..."; .\scripts\reconectar_banco_render.ps1 -AplicarViaApi
#
# API key: Render Dashboard -> Account Settings -> API Keys

param(
    [string]$DatabaseUrl = '',
    [string]$ServiceId = 'srv-d9hui8jtqb8s73a97d70',
    [switch]$AplicarViaApi,
    [switch]$DispararDeploy
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$urlFile = Join-Path $Root 'render_db.url'

function ConvertTo-RenderInternalDatabaseUrl {
    param([Parameter(Mandatory)][string]$Url)
    $u = $Url.Trim()
    if ($u -notmatch '^postgres(ql)?://') {
        throw 'URL invalida: deve comecar com postgresql://'
    }
    # External: ...@dpg-xxx-a.oregon-postgres.render.com:5432/db
    # Internal: ...@dpg-xxx-a:5432/db
    $interno = $u -replace '@([a-z0-9-]+)\.oregon-postgres\.render\.com', '@$1'
    $interno = $interno -replace '@([a-z0-9-]+)\.virginia-postgres\.render\.com', '@$1'
    $interno = $interno -replace '@([a-z0-9-]+)\.frankfurt-postgres\.render\.com', '@$1'
    if ($interno -notmatch '@[^:]+:[0-9]+/') {
        throw 'URL malformada (falta @host:porta/banco). Copie de novo no Render -> Connect.'
    }
    return $interno
}

function Test-DatabaseUrlFormat {
    param([string]$Url)
    if ($Url -match '^postgresql://([^:]+):([^@]+)@([^:/]+)(:[0-9]+)?/(.+)$') {
        return @{
            User = $Matches[1]
            Host = $Matches[3]
            Db   = $Matches[5]
        }
    }
    return $null
}

if (-not $DatabaseUrl) {
    if (-not (Test-Path $urlFile)) {
        Write-Host ""
        Write-Host "Arquivo render_db.url nao encontrado." -ForegroundColor Yellow
        Write-Host "Render -> financas-db (PostgreSQL) -> Connect -> External Database URL"
        Write-Host "Salve em: $urlFile"
        Write-Host ""
        Write-Host "Ou rode: .\scripts\conectar_postgres_render.ps1"
        exit 1
    }
    $DatabaseUrl = (Get-Content $urlFile -Raw).Trim()
}

$info = Test-DatabaseUrlFormat -Url $DatabaseUrl
if (-not $info) {
    Write-Host "DATABASE_URL invalida (senha/host colados?)." -ForegroundColor Red
    Write-Host "Corrija render_db.url com a External URL completa do Render." -ForegroundColor Yellow
    exit 1
}

try {
    $internalUrl = ConvertTo-RenderInternalDatabaseUrl -Url $DatabaseUrl
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "=== Reconectar SaudeFinanceira ao Postgres ===" -ForegroundColor Cyan
Write-Host "Banco (external): $($info.Db) @ $($info.Host)"
Write-Host "Usuario:          $($info.User)"
Write-Host ""
Write-Host "Internal URL (para o Web Service no Render):" -ForegroundColor Green
Write-Host $internalUrl
Write-Host ""

if (-not $AplicarViaApi) {
    Write-Host "Passos no Dashboard:" -ForegroundColor Cyan
    Write-Host "  1. https://dashboard.render.com/web/$ServiceId -> Environment"
    Write-Host "  2. Remova DATABASE_URL antiga"
    Write-Host "  3. Preferivel: Add from Database -> financas-db -> Internal Database URL"
    Write-Host "     (ou cole a Internal URL acima em uma variavel DATABASE_URL)"
    Write-Host "  4. Save -> Manual Deploy"
    Write-Host ""
    Write-Host "Automatico: `$env:RENDER_API_KEY='rnd_...'; .\scripts\reconectar_banco_render.ps1 -AplicarViaApi -DispararDeploy"
    exit 0
}

$apiKey = $env:RENDER_API_KEY
if (-not $apiKey) {
    Write-Error "Defina RENDER_API_KEY (Render -> Account Settings -> API Keys)"
}

$headers = @{
    Authorization = "Bearer $apiKey"
    Accept        = 'application/json'
    'Content-Type' = 'application/json'
}

Write-Host "Atualizando DATABASE_URL via API (servico $ServiceId)..." -ForegroundColor Cyan

$list = Invoke-RestMethod -Method Get -Uri "https://api.render.com/v1/services/$ServiceId/env-vars?limit=100" -Headers $headers
$existente = $null
foreach ($row in $list) {
    $ev = $row.envVar
    if ($ev.key -eq 'DATABASE_URL') {
        $existente = $ev
        break
    }
}

$body = @{ envVar = @{ key = 'DATABASE_URL'; value = $internalUrl } } | ConvertTo-Json -Depth 5

if ($existente) {
    Invoke-RestMethod -Method Put -Uri "https://api.render.com/v1/services/$ServiceId/env-vars/$($existente.id)" -Headers $headers -Body $body | Out-Null
    Write-Host "DATABASE_URL atualizada." -ForegroundColor Green
} else {
    Invoke-RestMethod -Method Post -Uri "https://api.render.com/v1/services/$ServiceId/env-vars" -Headers $headers -Body $body | Out-Null
    Write-Host "DATABASE_URL criada." -ForegroundColor Green
}

if ($DispararDeploy) {
    $deployBody = '{}' | ConvertFrom-Json | ConvertTo-Json
    Invoke-RestMethod -Method Post -Uri "https://api.render.com/v1/services/$ServiceId/deploys" -Headers $headers -Body '{}' | Out-Null
    Write-Host "Deploy disparado. Acompanhe em Logs." -ForegroundColor Green
} else {
    Write-Host "Reinicie ou faca Manual Deploy no servico." -ForegroundColor Yellow
}
