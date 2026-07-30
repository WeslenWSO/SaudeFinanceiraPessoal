# Copia hash de senha do SQLite local para PostgreSQL (Render)
# Uso: .\scripts\sincronizar_senha_postgres.ps1 -DatabaseUrl "postgresql://..." -Username saude
param(
    [Parameter(Mandatory = $true)]
    [string]$DatabaseUrl,
    [string]$Username = 'saude'
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$env:DATABASE_URL = $DatabaseUrl
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

Write-Host "Sincronizando senha de '$Username' (SQLite -> PostgreSQL) ..."
python scripts/sincronizar_senha_postgres.py $Username
