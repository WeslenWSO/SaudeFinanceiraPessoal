from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from empresa.models import Empresa, UsuarioEmpresa

class Command(BaseCommand):
    help = 'Cria empresas de teste para desenvolvimento'

    def add_arguments(self, parser):
        parser.add_argument(
            '--usuario',
            type=str,
            help='Nome do usuário que terá acesso às empresas',
        )

    def handle(self, *args, **options):
        # Busca ou cria um usuário
        username = options['usuario'] or 'admin'
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            self.stdout.write(
                self.style.WARNING(f'Usuário {username} não encontrado. Criando...')
            )
            user = User.objects.create_user(
                username=username,
                email=f'{username}@exemplo.com',
                password='admin123',
                first_name='Administrador',
                last_name='Sistema'
            )
            self.stdout.write(
                self.style.SUCCESS(f'Usuário {username} criado com sucesso!')
            )

        # Empresas de teste
        empresas_teste = [
            {
                'razao': 'Empresa Teste Ltda',
                'cnpj': '12345678000195',
                'nome_fantasia': 'Empresa Teste',
                'endereco': 'Rua das Flores, 123 - Centro - São Paulo/SP',
                'telefone': '(11) 99999-9999',
                'email': 'contato@empresateste.com',
                'status': 'Ativa'
            },
            {
                'razao': 'Comércio Exemplo S.A.',
                'cnpj': '98765432000187',
                'nome_fantasia': 'Comércio Exemplo',
                'endereco': 'Av. Principal, 456 - Jardim - Rio de Janeiro/RJ',
                'telefone': '(21) 88888-8888',
                'email': 'contato@comercioexemplo.com',
                'status': 'Ativa'
            },
            {
                'razao': 'Indústria Modelo Ltda',
                'cnpj': '45678912000134',
                'nome_fantasia': 'Indústria Modelo',
                'endereco': 'Rua Industrial, 789 - Zona Industrial - Belo Horizonte/MG',
                'telefone': '(31) 77777-7777',
                'email': 'contato@industriamodelo.com',
                'status': 'Ativa'
            }
        ]

        empresas_criadas = 0
        for dados_empresa in empresas_teste:
            # Verifica se a empresa já existe
            if not Empresa.objects.filter(cnpj=dados_empresa['cnpj']).exists():
                empresa = Empresa.objects.create(**dados_empresa)
                
                # Cria o relacionamento UsuarioEmpresa
                UsuarioEmpresa.objects.create(
                    usuario=user,
                    empresa=empresa,
                    ativo=True
                )
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Empresa "{empresa.razao}" criada com sucesso!'
                    )
                )
                empresas_criadas += 1
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f'Empresa com CNPJ {dados_empresa["cnpj"]} já existe.'
                    )
                )

        if empresas_criadas > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n{empresas_criadas} empresa(s) criada(s) com sucesso!'
                )
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Usuário {username} tem acesso a todas as empresas criadas.'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING('Nenhuma nova empresa foi criada.')
            )
