# Copia GEMINI_API_KEY do .env local para o Postgres (produção usa o mesmo banco).
# Também exibe passos para colar a chave no Render, se preferir variável de ambiente.

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$envFile = Join-Path $Root '.env'
if (-not (Test-Path $envFile)) {
    Write-Host 'Arquivo .env nao encontrado. Crie GEMINI_API_KEY=... no .env local.' -ForegroundColor Red
    exit 1
}

$geminiKey = $null
$geminiModel = 'gemini-2.5-flash'
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*GEMINI_API_KEY\s*=\s*(.+)\s*$') {
        $geminiKey = $matches[1].Trim().Trim('"').Trim("'")
    }
    if ($_ -match '^\s*GEMINI_MODEL\s*=\s*(.+)\s*$') {
        $geminiModel = $matches[1].Trim().Trim('"').Trim("'")
    }
}

if (-not $geminiKey) {
    Write-Host 'GEMINI_API_KEY nao encontrada no .env' -ForegroundColor Red
    exit 1
}

Write-Host '1/2 Gravando chave no Postgres (fallback para producao)...' -ForegroundColor Cyan
python manage.py migrate dashboard --noinput
python manage.py configurar_gemini --from-env
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host ''
Write-Host '2/2 Render (recomendado tambem):' -ForegroundColor Cyan
Write-Host '  Dashboard -> FinancasPessoais -> Environment'
Write-Host '  Adicione:'
Write-Host "    GEMINI_API_KEY = (mesma chave do .env, termina com ...$($geminiKey.Substring([Math]::Max(0, $geminiKey.Length - 4))))"
Write-Host "    GEMINI_MODEL = $geminiModel"
Write-Host '  Save -> Manual Deploy ou Restart'
Write-Host ''
Write-Host 'URL: https://dashboard.render.com/web/srv-d9hui8jtqb8s73a97d70' -ForegroundColor Yellow
Write-Host ''
Write-Host 'Apos deploy do codigo novo, producao usa env OU chave no Postgres.' -ForegroundColor Green
