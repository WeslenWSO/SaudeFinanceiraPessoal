from django.apps import AppConfig


class ContasareceberConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contasareceber'
    verbose_name = 'Contas a Receber'

    def ready(self):
        import contasareceber.signals  # noqa: F401
