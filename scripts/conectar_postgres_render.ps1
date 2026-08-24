# Configura conexão local com PostgreSQL financas-db (Render) e testa.
# Uso:
#   .\scripts\conectar_postgres_render.ps1
#   .\scripts\conectar_postgres_render.ps1 -DatabaseUrl "postgresql://..."
#
# Pré-requisito: banco financas-db Available no Render (Upgrade se suspenso).

param(
    [string]$DatabaseUrl = ''
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$urlFile = Join-Path $Root 'render_db.url'

if (-not $DatabaseUrl) {
    if (Test-Path $urlFile) {
        $DatabaseUrl = (Get-Content $urlFile -Raw).Trim()
    } else {
        Write-Host ""
        Write-Host "=== PostgreSQL Render (financas-db) ===" -ForegroundColor Cyan
        Write-Host "1. Render Dashboard -> financas-db -> Connect"
        Write-Host "2. Se Status = Suspended: Upgrade database"
        Write-Host "3. Copie a External Database URL (nao a Internal)"
        Write-Host ""
        $DatabaseUrl = Read-Host "Cole a External Database URL"
        $DatabaseUrl = $DatabaseUrl.Trim()
        if (-not $DatabaseUrl) {
            Write-Error "URL vazia. Copie de Render -> financas-db -> Connect -> External Database URL"
        }
        Set-Content -Path $urlFile -Value $DatabaseUrl -Encoding UTF8 -NoNewline
        Write-Host "Salvo em render_db.url" -ForegroundColor Green
    }
}

$env:DATABASE_URL = $DatabaseUrl
$env:PYTHONIOENCODING = 'utf-8'

Write-Host ""
Write-Host "Testando conexao Django..." -ForegroundColor Cyan
python manage.py diagnostico_banco --skip-checks 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Falha na conexao. Verifique:" -ForegroundColor Yellow
    Write-Host "  - Banco financas-db Available no Render (nao Suspended)"
    Write-Host "  - External Database URL (nao Internal)"
    Write-Host "  - Senha correta (icone olho no Render)"
    exit 1
}

Write-Host ""
Write-Host "=== DBeaver (conexao manual) ===" -ForegroundColor Cyan
Write-Host "Host:     dpg-d9hurgo4n6ts73bj8pkg-a.oregon-postgres.render.com"
Write-Host "Port:     5432"
Write-Host "Database: financas_db_adei"
Write-Host "User:     financas_db_adei_user"
Write-Host "Password: (Render -> Connect -> Password)"
Write-Host "SSL:      require (aba SSL no DBeaver)"
Write-Host ""
Write-Host "Arquivo de referencia: docs/dbeaver-financas-db.md"
Write-Host "Datasource export:     scripts/dbeaver/financas-db.dbeaver-data-sources.json"
Write-Host ""
Write-Host "Para usar manage.py nesta sessao:" -ForegroundColor Green
Write-Host '  $env:DATABASE_URL = (Get-Content render_db.url -Raw).Trim()'
