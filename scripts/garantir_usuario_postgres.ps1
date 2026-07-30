# Define/atualiza usuario no PostgreSQL do Render (financas-db).
# Usa render_db.url (External URL) — arquivo local, nao commitar.
param(
    [Parameter(Mandatory = $true)]
    [string]$Username,
    [Parameter(Mandatory = $true)]
    [string]$Password,
    [switch]$Superuser,
    [switch]$VincularEmpresas
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)

$urlFile = Join-Path (Get-Location) 'render_db.url'
if (-not (Test-Path $urlFile)) {
    Write-Error "Crie render_db.url com a External Database URL do financas-db (Render -> Connect)."
}

$env:DATABASE_URL = (Get-Content $urlFile -Raw).Trim()
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'

$args = @(
    'manage.py', 'garantir_usuario', $Username,
    '--password', $Password,
    '--skip-checks'
)
if ($Superuser) { $args += '--superuser' }
if ($VincularEmpresas) { $args += '--vincular-empresas' }

Write-Host "Atualizando '$Username' no PostgreSQL (financas-db) ..."
python @args
python manage.py diagnostico_banco --testar-login $Username --senha $Password --skip-checks
