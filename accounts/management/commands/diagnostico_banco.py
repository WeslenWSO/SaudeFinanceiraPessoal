from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Mostra qual banco a app usa e se existem usuarios (util no Shell do Render).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--usuario',
            metavar='NOME',
            help='Detalhes de um usuario (ex.: saude).',
        )
        parser.add_argument(
            '--testar-login',
            metavar='USUARIO',
            help='Testa authenticate() com a senha informada em --senha.',
        )
        parser.add_argument(
            '--senha',
            help='Senha para --testar-login (nao e exibida nos logs).',
        )

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        engine = db.get('ENGINE', '')
        name = db.get('NAME', '')
        host = db.get('HOST', '')

        self.stdout.write('=== Diagnostico de banco / login ===')
        self.stdout.write(f'ENGINE: {engine}')
        self.stdout.write(f'NAME: {name}')
        if host:
            self.stdout.write(f'HOST: {host}')

        if 'sqlite' in engine:
            self.stdout.write(
                self.style.WARNING(
                    'ATENCAO: usando SQLite. No Render isso costuma ser banco vazio '
                    '(ephemeral). Verifique DATABASE_URL no Environment.'
                )
            )
        elif 'postgres' in engine:
            self.stdout.write(self.style.SUCCESS('Usando PostgreSQL (DATABASE_URL ok).'))

        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM auth_user')
            total = cursor.fetchone()[0]

        self.stdout.write(f'Usuarios (auth_user): {total}')
        for username, is_active, is_superuser in User.objects.values_list(
            'username', 'is_active', 'is_superuser'
        ).order_by('username'):
            flags = []
            if is_active:
                flags.append('ativo')
            if is_superuser:
                flags.append('superuser')
            self.stdout.write(f'  - {username} ({", ".join(flags) or "inativo"})')

        detail_user = options.get('usuario')
        if detail_user:
            self._detalhar_usuario(detail_user.strip())

        test_user = options.get('testar_login')
        test_password = options.get('senha')
        if test_user:
            exists = User.objects.filter(username=test_user).exists()
            self.stdout.write(f'\nUsuario "{test_user}" existe: {exists}')
            if test_password:
                ok = bool(authenticate(username=test_user, password=test_password))
                if ok:
                    self.stdout.write(self.style.SUCCESS('authenticate(): OK'))
                else:
                    self.stdout.write(
                        self.style.ERROR(
                            'authenticate(): FALHOU (senha errada ou usuario inativo).'
                        )
                    )
            else:
                self.stdout.write('Passe --senha para testar authenticate().')

    def _detalhar_usuario(self, username: str) -> None:
        self.stdout.write(f'\n--- Detalhe: {username} ---')
        qs = User.objects.filter(username__iexact=username)
        if not qs.exists():
            self.stdout.write(self.style.ERROR('Nao encontrado neste banco.'))
            return
        user = qs.first()
        self.stdout.write(f'username exato: {user.username!r}')
        self.stdout.write(f'is_active: {user.is_active}')
        self.stdout.write(f'is_superuser: {user.is_superuser}')
        self.stdout.write(f'senha utilizavel: {user.has_usable_password()}')
        if user.password:
            algo = user.password.split('$', 1)[0] if '$' in user.password else '?'
            self.stdout.write(f'algoritmo hash: {algo}')
        empresa_links = user.usuarioempresa_set.filter(ativo=True).count()
        self.stdout.write(f'vinculos UsuarioEmpresa ativos: {empresa_links}')
