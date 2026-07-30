# Importa backup_render.json para PostgreSQL (Render ou outro)
# Uso: .\scripts\importar_para_postgres.ps1 -DatabaseUrl "postgresql://..."
param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$env:DATABASE_URL = $DatabaseUrl
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

if (-not (Test-Path "backup_render.json")) {
    Write-Error "Arquivo backup_render.json nao encontrado. Rode scripts\exportar_sqlite.ps1 antes."
}

Write-Host "1/3 migrate no PostgreSQL ..."
python manage.py migrate --skip-checks --noinput

Write-Host "2/3 import ordenado (scripts/importar_postgres_completo.py) ..."
python scripts/importar_postgres_completo.py

Write-Host "Importacao concluida."
