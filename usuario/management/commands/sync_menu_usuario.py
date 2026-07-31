"""Sincroniza permissões de menu de um usuário de login."""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from usuario.menu import CODIGOS_MENU
from usuario.models import PermissaoMenuUsuario, Usuario
from usuario.permissoes_menu import MARCADOR_CONFIGURADO, permissoes_salvas, salvar_permissoes_menu


class Command(BaseCommand):
    help = 'Lista ou redefine permissões de menu de um auth.User (ex.: willian).'

    def add_arguments(self, parser):
        parser.add_argument('username', help='Login do usuário (auth.User)')
        parser.add_argument(
            '--codigos',
            help='Códigos separados por vírgula (ex.: cliente,cobranca,socio). Omita para listar.',
        )

    def handle(self, *args, **options):
        username = (options['username'] or '').strip()
        user = User.objects.filter(username__iexact=username).first()
        if not user:
            raise CommandError(f'Usuário de login "{username}" não encontrado.')

        if not options.get('codigos'):
            perms = sorted(permissoes_salvas(user))
            marcador = PermissaoMenuUsuario.objects.filter(
                usuario=user,
                codigo=MARCADOR_CONFIGURADO,
            ).exists()
            self.stdout.write(f'{user.username} (id={user.id}) superuser={user.is_superuser}')
            self.stdout.write(f'configurado={marcador} total={len(perms)}')
            for codigo in perms:
                self.stdout.write(f'  - {codigo}')
            return

        codigos = [
            c.strip()
            for c in options['codigos'].split(',')
            if c.strip()
        ]
        invalidos = [c for c in codigos if c not in CODIGOS_MENU]
        if invalidos:
            raise CommandError(f'Códigos inválidos: {", ".join(invalidos)}')

        perfil = Usuario.objects.filter(usuario__iexact=user.username).first()
        if not perfil:
            perfil = Usuario(usuario=user.username)

        salvar_permissoes_menu(perfil, codigos, user=user)
        self.stdout.write(
            self.style.SUCCESS(
                f'Permissões de {user.username} atualizadas ({len(codigos)} itens).',
            ),
        )
