"""Consolida auth.User duplicados (Willian vs willian) e permissões de menu."""

from collections import defaultdict

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from usuario.auth_user import consolidar_auth_users_duplicados, usuario_login_canonico
from usuario.models import PermissaoMenuUsuario


class Command(BaseCommand):
    help = 'Move permissões de menu para o auth.User canônico (mesmo login, maiúsculas diferentes).'

    def add_arguments(self, parser):
        parser.add_argument(
            'username',
            nargs='?',
            help='Login específico (ex.: willian). Omita para processar todos.',
        )

    def handle(self, *args, **options):
        username = (options.get('username') or '').strip()
        if username:
            users = list(User.objects.filter(username__iexact=username).order_by('id'))
            if not users:
                self.stdout.write(self.style.WARNING(f'Nenhum auth.User para "{username}".'))
                return
            self._consolidar_grupo(users)
            return

        grupos: dict[str, list[User]] = defaultdict(list)
        for user in User.objects.order_by('id'):
            chave = (user.username or '').strip().lower()
            if chave:
                grupos[chave].append(user)

        total = 0
        for chave, users in grupos.items():
            if len(users) > 1:
                self._consolidar_grupo(users)
                total += 1
        self.stdout.write(self.style.SUCCESS(f'Grupos consolidados: {total}'))

    def _consolidar_grupo(self, users: list[User]):
        canonico = usuario_login_canonico(users[0])
        if not canonico:
            return
        duplicados = [u for u in users if u.pk != canonico.pk]
        if not duplicados:
            self.stdout.write(f'{canonico.username} (id={canonico.id}): já único.')
            return

        antes = PermissaoMenuUsuario.objects.filter(usuario=canonico).count()
        for dup in duplicados:
            self.stdout.write(
                f'  duplicado id={dup.pk} username="{dup.username}" -> '
                f'canonico id={canonico.pk} username="{canonico.username}"',
            )
        consolidar_auth_users_duplicados(canonico, login=canonico.username)
        depois = PermissaoMenuUsuario.objects.filter(usuario=canonico).count()
        self.stdout.write(
            self.style.SUCCESS(
                f'{canonico.username}: {max(0, depois - antes)} permissão(ões) consolidada(s).',
            ),
        )
