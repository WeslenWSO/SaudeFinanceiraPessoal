#!/usr/bin/env bash
set -o errexit

# OCR (PDF Bradesco/Sicoob em imagem) — ignora falha se apt não estiver disponível
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq tesseract-ocr tesseract-ocr-por || true
fi

pip install -r requirements.txt

python manage.py collectstatic --noinput
if [ ! -f staticfiles/accounts/img/logo.png ] && [ ! -f staticfiles/media/fotos/2022/logo.png ]; then
  echo "ERRO: logo do login nao foi coletado. Confira accounts/static/ no Git."
  exit 1
fi
python manage.py migrate --noinput
