from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from empresa.models import Empresa, UsuarioEmpresa
from cobranca.models import Cobranca
from notasfiscais.models import NotaFiscalServico

class Command(BaseCommand):
    help = 'Migra dados existentes para o sistema multi-empresa'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--empresa-nome',
            type=str,
            default='Empresa Padrão',
            help='Nome da empresa padrão para migração'
        )
        parser.add_argument(
            '--empresa-cnpj',
            type=str,
            default='00000000000000',
            help='CNPJ da empresa padrão para migração'
        )
    
    def handle(self, *args, **options):
        self.stdout.write('Iniciando migração para sistema multi-empresa...')
        
        # 1. Cria empresa padrão se não existir
        empresa, created = Empresa.objects.get_or_create(
            cnpj=options['empresa_cnpj'],
            defaults={
                'razao': options['empresa_nome'],
                'nome_fantasia': options['empresa_nome'],
                'status': 'Ativa'
            }
        )
        
        if created:
            self.stdout.write(f'Empresa criada: {empresa.razao}')
        else:
            self.stdout.write(f'Empresa existente: {empresa.razao}')
        
        # 2. Associa todos os usuários à empresa
        usuarios = User.objects.filter(is_active=True)
        for usuario in usuarios:
            usuario_empresa, created = UsuarioEmpresa.objects.get_or_create(
                usuario=usuario,
                empresa=empresa,
                defaults={'ativo': True}
            )
            if created:
                self.stdout.write(f'Usuário {usuario.username} associado à empresa {empresa.razao}')
        
        # 3. Cobrança (formas de pagamento) é global no sistema; não possui vínculo por empresa
        formas_pgto = Cobranca.objects.all()
        self.stdout.write(f'Formas de pagamento (Cobrança): {formas_pgto.count()} cadastradas')

        # 4. Atualiza NFSe existentes
        nfses = NotaFiscalServico.objects.filter(empresa__isnull=True)
        for nfse in nfses:
            nfse.empresa = empresa
            nfse.save()
            self.stdout.write(f'NFSe {nfse.numero_nota} associada à empresa {empresa.razao}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Migração concluída! Empresa: {empresa.razao}, '
                f'Usuários: {usuarios.count()}, '
                f'Cobranças: {formas_pgto.count()}, '
                f'NFSe: {nfses.count()}'
            )
        )













