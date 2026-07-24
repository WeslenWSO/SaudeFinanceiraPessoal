#!/usr/bin/env python
"""
Script de teste para verificar a importação de XML com tratamento de duplicatas
"""

import os
import sys
import django
from decimal import Decimal

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from notasfiscais.models import NotaFiscalServico
from empresa.models import Empresa
from notasfiscais.utils import import_nfse_from_xml
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

def test_import_with_duplicates():
    """Testa a importação com notas duplicadas"""
    
    print("=== TESTE DE IMPORTAÇÃO COM DUPLICATAS ===")
    
    # Buscar empresa e usuário de teste
    try:
        empresa = Empresa.objects.first()
        if not empresa:
            print("❌ Nenhuma empresa encontrada no banco")
            return
        
        user = User.objects.first()
        if not user:
            print("❌ Nenhum usuário encontrado no banco")
            return
        
        print(f"✅ Empresa: {empresa.razao}")
        print(f"✅ Usuário: {user.username}")
        
    except Exception as e:
        print(f"❌ Erro ao buscar empresa/usuário: {str(e)}")
        return
    
    # Verificar notas existentes
    notas_existentes = NotaFiscalServico.objects.filter(empresa=empresa).count()
    print(f"📊 Notas existentes na empresa: {notas_existentes}")
    
    # Criar XML de teste com notas duplicadas
    xml_content = '''<?xml version="1.0" encoding="UTF-8"?>
<ConsultarNfseLoteResposta xmlns="http://www.abrasf.org.br/ABRASF/arquivos/nfse.xsd">
    <ListaNfse>
        <CompNfse>
            <Nfse>
                <InfNfse>
                    <Numero>1-406</Numero>
                    <Serie>1</Serie>
                    <DataEmissao>2025-01-15</DataEmissao>
                    <ValorLiquidoNfse>1000.00</ValorLiquidoNfse>
                    <ValorServicos>1000.00</ValorServicos>
                    <Discriminacao>Serviço de teste 1</Discriminacao>
                    <PrestadorServico>
                        <IdentificacaoPrestador>
                            <Cnpj>''' + empresa.cnpj + '''</Cnpj>
                        </IdentificacaoPrestador>
                    </PrestadorServico>
                    <TomadorServico>
                        <IdentificacaoTomador>
                            <CpfCnpj>
                                <Cnpj>12345678000199</Cnpj>
                            </CpfCnpj>
                        </IdentificacaoTomador>
                        <RazaoSocial>Cliente Teste 1</RazaoSocial>
                    </TomadorServico>
                </InfNfse>
            </Nfse>
        </CompNfse>
        <CompNfse>
            <Nfse>
                <InfNfse>
                    <Numero>1-407</Numero>
                    <Serie>1</Serie>
                    <DataEmissao>2025-01-16</DataEmissao>
                    <ValorLiquidoNfse>2000.00</ValorLiquidoNfse>
                    <ValorServicos>2000.00</ValorServicos>
                    <Discriminacao>Serviço de teste 2</Discriminacao>
                    <PrestadorServico>
                        <IdentificacaoPrestador>
                            <Cnpj>''' + empresa.cnpj + '''</Cnpj>
                        </IdentificacaoPrestador>
                    </PrestadorServico>
                    <TomadorServico>
                        <IdentificacaoTomador>
                            <CpfCnpj>
                                <Cnpj>98765432000188</Cnpj>
                            </CpfCnpj>
                        </IdentificacaoTomador>
                        <RazaoSocial>Cliente Teste 2</RazaoSocial>
                    </TomadorServico>
                </InfNfse>
            </Nfse>
        </CompNfse>
    </ListaNfse>
</ConsultarNfseLoteResposta>'''
    
    # Criar arquivo temporário
    xml_file = SimpleUploadedFile(
        "test_duplicates.xml",
        xml_content.encode('utf-8'),
        content_type='application/xml'
    )
    
    try:
        print("\n🔄 Testando importação...")
        resultado = import_nfse_from_xml(xml_file, user, empresa)
        
        print(f"\n📊 RESULTADO DA IMPORTAÇÃO:")
        print(f"Total processadas: {resultado['total_processadas']}")
        print(f"Total importadas: {resultado['total_importadas']}")
        print(f"Total ignoradas: {resultado['total_ignoradas']}")
        
        if resultado['notas_importadas']:
            print(f"\n✅ NOTAS IMPORTADAS:")
            for nota in resultado['notas_importadas']:
                print(f"  - {nota['numero_nota']}: {nota['cliente']} - R$ {nota['valor_liquido']}")
        
        if resultado['notas_ignoradas']:
            print(f"\n⚠️ NOTAS IGNORADAS:")
            for nota in resultado['notas_ignoradas']:
                print(f"  - {nota['numero_nota']}: {nota['cliente']} - Motivo: {nota['motivo']}")
        
        # Verificar se as notas foram realmente salvas
        notas_apos_importacao = NotaFiscalServico.objects.filter(empresa=empresa).count()
        print(f"\n📊 Notas após importação: {notas_apos_importacao}")
        print(f"📊 Novas notas adicionadas: {notas_apos_importacao - notas_existentes}")
        
        # Testar importação do mesmo XML novamente (deve ignorar todas)
        print(f"\n🔄 Testando importação do mesmo XML novamente...")
        xml_file.seek(0)  # Voltar ao início do arquivo
        resultado2 = import_nfse_from_xml(xml_file, user, empresa)
        
        print(f"\n📊 RESULTADO DA SEGUNDA IMPORTAÇÃO:")
        print(f"Total processadas: {resultado2['total_processadas']}")
        print(f"Total importadas: {resultado2['total_importadas']}")
        print(f"Total ignoradas: {resultado2['total_ignoradas']}")
        
        if resultado2['total_importadas'] == 0 and resultado2['total_ignoradas'] > 0:
            print("✅ TESTE PASSOU: Duplicatas foram corretamente ignoradas!")
        else:
            print("❌ TESTE FALHOU: Duplicatas não foram ignoradas corretamente!")
        
    except Exception as e:
        print(f"❌ Erro durante o teste: {str(e)}")
        import traceback
        traceback.print_exc()
    
    finally:
        xml_file.close()

if __name__ == "__main__":
    test_import_with_duplicates()



