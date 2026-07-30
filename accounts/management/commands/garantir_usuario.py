from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from empresa.models import Empresa, UsuarioEmpresa


class Command(BaseCommand):
    help = (
        'Cria ou atualiza um usuario Django (senha, staff/superuser) '
        'e opcionalmente vincula empresas ativas.'
    )

    def add_arguments(self, parser):
        parser.add_argument('username', help='Nome de usuario (login).')
        parser.add_argument(
            '--password',
            required=True,
            help='Senha em texto puro (sera hasheada).',
        )
        parser.add_argument(
            '--email',
            default='',
            help='E-mail do usuario (opcional).',
        )
        parser.add_argument(
            '--superuser',
            action='store_true',
            help='Marca is_staff e is_superuser.',
        )
        parser.add_argument(
            '--vincular-empresas',
            action='store_true',
            help='Vincula o usuario a todas as empresas com status Ativa.',
        )

    def handle(self, *args, **options):
        username = options['username'].strip()
        password = options['password']
        if not username:
            raise CommandError('username nao pode ser vazio.')

        user, created = User.objects.get_or_create(
            username=username,
            defaults={'email': options['email'] or f'{username}@local'},
        )
        user.set_password(password)
        user.is_active = True
        if options['superuser']:
            user.is_staff = True
            user.is_superuser = True
        if options['email']:
            user.email = options['email']
        user.save()

        action = 'Criado' if created else 'Atualizado'
        self.stdout.write(self.style.SUCCESS(f'{action}: {username}'))

        if options['vincular_empresas']:
            links = 0
            for empresa in Empresa.objects.filter(status='Ativa'):
                _, link_created = UsuarioEmpresa.objects.get_or_create(
                    usuario=user,
                    empresa=empresa,
                    defaults={'ativo': True},
                )
                if link_created:
                    links += 1
            self.stdout.write(f'Vinculos novos com empresas ativas: {links}')
