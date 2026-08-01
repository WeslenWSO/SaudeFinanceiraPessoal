from django.apps import AppConfig


def _configurar_sqlite(sender, connection, **kwargs):
    if connection.vendor != 'sqlite':
        return
    with connection.cursor() as cursor:
        cursor.execute('PRAGMA journal_mode=WAL;')
        cursor.execute('PRAGMA busy_timeout=60000;')
        cursor.execute('PRAGMA synchronous=NORMAL;')


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        from django.db.backends.signals import connection_created

        connection_created.connect(
            _configurar_sqlite,
            dispatch_uid='dashboard_sqlite_pragmas',
        )
