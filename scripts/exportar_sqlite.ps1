# Exporta db.sqlite3 local para backup_render.json
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "Exportando SQLite -> backup_render.json ..."
python manage.py dumpdata `
  --skip-checks `
  --natural-foreign --natural-primary `
  -e contenttypes -e auth.permission `
  --indent 2 `
  -o backup_render.json

$mb = [math]::Round((Get-Item backup_render.json).Length / 1MB, 2)
Write-Host "OK: backup_render.json ($mb MB)"
