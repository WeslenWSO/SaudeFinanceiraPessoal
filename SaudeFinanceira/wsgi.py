"""
WSGI config for SaudeFinanceira project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from SaudeFinanceira.google_grpc_env import silenciar_logs_grpc_google

silenciar_logs_grpc_google()
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')

# Compatibilidade: alguns ambientes (ex.: servidor com pacotes mistos) tentam
# importar lazy_annotations de django.utils.inspect, que só existe no Django 5.2+.
# Em Django 4.2 esse nome não existe e gera ImportError/500. Adicionamos um stub se faltar.
import django.utils.inspect as _django_inspect
if not hasattr(_django_inspect, 'lazy_annotations'):
    def _lazy_annotations(func):
        return func
    _django_inspect.lazy_annotations = _lazy_annotations

from django.core.wsgi import get_wsgi_application


def _on_render() -> bool:
    return os.environ.get('RENDER', '').strip().lower() in ('true', '1', 'yes')


def _log_database_backend() -> None:
    if not _on_render():
        return
    import django
    django.setup()
    from django.conf import settings
    from django.contrib.auth.models import User

    db = settings.DATABASES['default']
    engine = db.get('ENGINE', '')
    print(f'[startup] DATABASE ENGINE: {engine}', flush=True)
    if 'sqlite' in engine:
        print(
            '[startup] AVISO: SQLite no Render — configure DATABASE_URL no Environment.',
            flush=True,
        )
    else:
        print(f'[startup] auth_user count: {User.objects.count()}', flush=True)


def _bootstrap_database_and_static() -> None:
    """Migrate/collectstatic no Render (mesmo sem DATABASE_URL configurado ainda)."""
    if not (_on_render() or os.environ.get('DATABASE_URL', '').strip()):
        return
    import django
    django.setup()
    from django.core.management import call_command
    call_command('migrate', '--noinput', verbosity=0)
    call_command('collectstatic', '--noinput', verbosity=0)


_log_database_backend()


_bootstrap_database_and_static()
application = get_wsgi_application()
