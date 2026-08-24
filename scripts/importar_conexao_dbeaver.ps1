# Importa conexao financas-db no DBeaver e testa (SSL require).
# Requer render_db.url na raiz do projeto.

$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
$urlFile = Join-Path $Root 'render_db.url'

if (-not (Test-Path $urlFile)) {
    Write-Error "Crie render_db.url (copie de render_db.url.example) com a External Database URL do Render."
}

$raw = (Get-Content $urlFile -Raw).Trim()
if ($raw -match '^postgres(?:ql)?://([^:]+):([^@]+)@([^/]+)/(.+)$') {
    $user = $Matches[1]
    $pass = [uri]::UnescapeDataString($Matches[2])
    $hostPart = $Matches[3]
    $db = ($Matches[4] -split '\?')[0].TrimEnd('/')
    if ($hostPart -match '^([^:]+):(\d+)$') {
        $dbHost = $Matches[1]
        $port = $Matches[2]
    } else {
        $dbHost = $hostPart
        $port = '5432'
    }
} else {
    Write-Error "URL invalida em render_db.url. Use External Database URL do Render."
}

$dbeaverExe = Join-Path $env:LOCALAPPDATA 'DBeaver\dbeaver.exe'
if (-not (Test-Path $dbeaverExe)) {
    Write-Error "DBeaver nao encontrado. Instale: winget install DBeaver.DBeaver.Community"
}

$spec = @(
    "driver=postgresql"
    "host=$dbHost"
    "port=$port"
    "database=$db"
    "user=$user"
    "password=$pass"
    "ssl=true"
    "sslmode=require"
    "name=financas-db (Render)"
    "create=true"
    "openConsole=false"
    "connect=true"
) -join '|'

Write-Host "Abrindo DBeaver e testando conexao financas-db (Render)..." -ForegroundColor Cyan
& $dbeaverExe -nosplash -q -con $spec
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
    Write-Warning "DBeaver retornou codigo $LASTEXITCODE. Se a janela abriu, confira Database Navigator -> financas-db (Render)."
} else {
    Write-Host "Conexao enviada ao DBeaver. Verifique o painel esquerdo." -ForegroundColor Green
}

Write-Host ""
Write-Host "Importar manualmente (alternativa): File -> Import -> DBeaver -> Project export"
Write-Host "Arquivo: scripts/dbeaver/financas-db.dbeaver-data-sources.json"
