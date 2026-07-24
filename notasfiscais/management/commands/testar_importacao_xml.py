from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from empresa.models import Empresa
from notasfiscais.utils import import_nfse_from_xml
from django.core.files.base import ContentFile

class Command(BaseCommand):
    help = 'Testa a importação de XML de NFSe'

    def add_arguments(self, parser):
        parser.add_argument(
            '--usuario',
            type=str,
            default='admin',
            help='Nome do usuário para teste'
        )
        parser.add_argument(
            '--cnpj',
            type=str,
            default='28703945000199',
            help='CNPJ da empresa para teste'
        )

    def handle(self, *args, **options):
        username = options['usuario']
        cnpj_empresa = options['cnpj']
        
        try:
            # Busca usuário
            user = User.objects.get(username=username)
            self.stdout.write(f'Usuário encontrado: {user.username}')
            
            # Busca empresa pelo CNPJ
            empresa = Empresa.objects.get(cnpj=cnpj_empresa)
            self.stdout.write(f'Empresa encontrada: {empresa.razao} (CNPJ: {empresa.cnpj})')
            
            # Cria XML de teste no formato de lote
            xml_content = self.criar_xml_lote_teste(empresa.cnpj)
            xml_file = ContentFile(xml_content.encode('utf-8'), name='teste_lote.xml')
            
            self.stdout.write('XML de teste (lote) criado com sucesso')
            
            # Testa importação
            try:
                nfse = import_nfse_from_xml(xml_file, user, empresa)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Importação bem-sucedida! NFSe {nfse.numero_nota} criada.'
                    )
                )
                
                # Salva a NFSe
                nfse.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f'NFSe salva no banco com ID: {nfse.id}'
                    )
                )
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Erro na importação: {str(e)}'
                    )
                )
                
        except User.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Usuário {username} não encontrado.')
            )
        except Empresa.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Empresa com CNPJ {cnpj_empresa} não encontrada.')
            )

    def criar_xml_lote_teste(self, cnpj_empresa):
        """Cria um XML de teste para lote de NFSe no formato real"""
        xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<ConsultarNfseLote>
  <ListaNfse>
    <CompNfse>
      <Nfse>
        <InfNfse>
          <Numero>12345</Numero>
          <Serie>1</Serie>
          <DataEmissao>2025-01-15T10:00:00.000-03:00</DataEmissao>
          <Servico>
            <Valores>
              <ValorServicos>150.00</ValorServicos>
              <ValorLiquidoNfse>150.00</ValorLiquidoNfse>
            </Valores>
            <Discriminacao>Serviço de teste para validação</Discriminacao>
          </Servico>
          <PrestadorServico>
            <IdentificacaoPrestador>
              <Cnpj>{cnpj_empresa}</Cnpj>
            </IdentificacaoPrestador>
            <RazaoSocial>Empresa Teste LTDA</RazaoSocial>
          </PrestadorServico>
          <TomadorServico>
            <IdentificacaoTomador>
              <CpfCnpj>
                <Cnpj>12345678000199</Cnpj>
              </CpfCnpj>
            </IdentificacaoTomador>
            <RazaoSocial>Cliente Teste Ltda</RazaoSocial>
          </TomadorServico>
        </InfNfse>
      </Nfse>
    </CompNfse>
  </ListaNfse>
</ConsultarNfseLote>'''
        
        return xml_content
