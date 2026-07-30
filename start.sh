#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn SaudeFinanceira.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout 120
