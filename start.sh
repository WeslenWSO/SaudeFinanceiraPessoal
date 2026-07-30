#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput
python manage.py collectstatic --noinput

python - <<'PY' || true
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
django.setup()
from django.conf import settings
from django.contrib.auth.models import User
db = settings.DATABASES["default"]
engine = db.get("ENGINE", "")
host = db.get("HOST", "") or "(local)"
print(f"[startup] ENGINE={engine.split('.')[-1]} HOST={host}")
print(f"[startup] auth_user count: {User.objects.count()}")
PY

exec gunicorn SaudeFinanceira.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout 120
