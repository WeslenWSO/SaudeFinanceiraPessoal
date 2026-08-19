#!/usr/bin/env bash
set -o errexit

python manage.py migrate --noinput
python manage.py collectstatic --noinput

python - <<'PY'
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")
django.setup()
from django.conf import settings
from django.contrib.auth.models import User
from pathlib import Path
media = Path(settings.MEDIA_ROOT)
media.mkdir(parents=True, exist_ok=True)
writable = False
write_err = ""
try:
    test = media / ".startup_write_test"
    test.write_text("ok", encoding="utf-8")
    writable = test.read_text(encoding="utf-8") == "ok"
    test.unlink(missing_ok=True)
except OSError as exc:
    write_err = str(exc)
db = settings.DATABASES["default"]
engine = db.get("ENGINE", "")
host = db.get("HOST", "") or "(local)"
print(f"[startup] MEDIA_ROOT={media} exists={media.is_dir()} writable={writable}")
if write_err:
    print(f"[startup] MEDIA_ROOT write error: {write_err}")
print(f"[startup] ENGINE={engine.split('.')[-1]} HOST={host}")
print(f"[startup] auth_user count: {User.objects.count()}")
try:
    from faturamento_medico.services.media_storage import diagnosticar_media_storage
    st = diagnosticar_media_storage(limite_faltando=5)
    print(
        f"[startup] anexos total={st.total_anexos} ok={st.anexos_ok} "
        f"faltando={st.anexos_faltando} hint={st.disk_mount_hint}"
    )
    for item in st.faltando[:3]:
        print(
            f"[startup] anexo_faltando doc={item['documento_id']} "
            f"fat={item['faturamento_id']}"
        )
except Exception as exc:
    print(f"[startup] anexo_diagnostico erro: {exc}")
PY

exec gunicorn SaudeFinanceira.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-300}"
