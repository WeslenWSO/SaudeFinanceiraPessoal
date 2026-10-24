#!/usr/bin/env bash
set -o errexit

# OCR (PDF Bradesco/Sicoob em imagem) — ignora falha se apt não estiver disponível
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq tesseract-ocr tesseract-ocr-por || true
fi

pip install -r requirements-render.txt

# Playwright — PDF do relatório de Análises (/dash/)
if [ -z "${PLAYWRIGHT_BROWSERS_PATH:-}" ]; then
  export PLAYWRIGHT_BROWSERS_PATH="/opt/render/project/src/.playwright-browsers"
fi
mkdir -p "$PLAYWRIGHT_BROWSERS_PATH"
if command -v apt-get >/dev/null 2>&1; then
  python -m playwright install-deps chromium || true
fi
python -m playwright install chromium

python manage.py collectstatic --noinput
if [ ! -f staticfiles/accounts/img/logo.png ] && [ ! -f static/accounts/img/logo.png ]; then
  echo "ERRO: logo do login nao foi coletado. Confira accounts/static/ no Git."
  exit 1
fi
python manage.py migrate --noinput
