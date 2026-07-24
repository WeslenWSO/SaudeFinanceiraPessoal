#!/usr/bin/env python3
"""
Script para debugar a importação de NFSe do lote
"""
import os
import sys
import django
from django.conf import settings

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'SaudeFinanceira.settings')
django.setup()

from notasfiscais.utils import import_lote_nfse, extract_lote_preview
from empresa.models import Empresa
import xml.etree.ElementTree as ET

def test_import_lote():
    """Testa a importação do lote de NFSe"""

    # XML fornecido pelo usuário
    xml_content = '''<LoteNotaFiscal xmlns:ns2="http://www.w3.org/2000/09/xmldsig#" xmlns:ns3="http://www.abrasf.org.br/nfse.xsd">
<CompNfse>
<ns3:Nfse versao="2.01">
<ns3:InfNfse Id="4712246SNLTFPYYQL7FV211TF1G461TB">
<ns3:Numero>54</ns3:Numero>
<ns3:CodigoVerificacao>TDGCB6YV3</ns3:CodigoVerificacao>
<ns3:DataEmissao>2025-08-30T12:02:22</ns3:DataEmissao>
<ns3:OutrasInformacoes>Val. Aprox. Tributos:</ns3:OutrasInformacoes>
<ns3:ValoresNfse>
<ns3:BaseCalculo>225.00</ns3:BaseCalculo>
<ns3:Aliquota>4.0751</ns3:Aliquota>
<ns3:ValorIss>9.17</ns3:ValorIss>
<ns3:ValorLiquidoNfse>225.00</ns3:ValorLiquidoNfse>
</ns3:ValoresNfse>
<ns3:PrestadorServico>
<ns3:IdentificacaoPrestador>
<ns3:CpfCnpj>
<ns3:Cnpj>41283279000145</ns3:Cnpj>
</ns3:CpfCnpj>
<ns3:InscricaoMunicipal>24943</ns3:InscricaoMunicipal>
</ns3:IdentificacaoPrestador>
<ns3:RazaoSocial>BW PRESTAÇÃO DE SERVIÇOS MÉDICOS LTDA</ns3:RazaoSocial>
<ns3:NomeFantasia>DIRON SERVICOS MEDICOS</ns3:NomeFantasia>
<ns3:Endereco>
<ns3:Endereco>RUA INGAZEIRO</ns3:Endereco>
<ns3:Numero>1878</ns3:Numero>
<ns3:Complemento>SALA 08</ns3:Complemento>
<ns3:Bairro>SETOR 01</ns3:Bairro>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:Uf>RO</ns3:Uf>
<ns3:CodigoPais>1058</ns3:CodigoPais>
<ns3:Cep>76870084</ns3:Cep>
</ns3:Endereco>
<ns3:Contato>
<ns3:Telefone/>
<ns3:Email>ATENDIMENTO@DUETI.COM.BR</ns3:Email>
</ns3:Contato>
</ns3:PrestadorServico>
<ns3:OrgaoGerador>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:Uf>RO</ns3:Uf>
</ns3:OrgaoGerador>
<ns3:DeclaracaoPrestacaoServico>
<ns3:InfDeclaracaoPrestacaoServico>
<ns3:Competencia>2025-08-30</ns3:Competencia>
<ns3:Servico>
<ns3:Valores>
<ns3:ValorServicos>225.00</ns3:ValorServicos>
<ns3:ValorDeducoes>0.00</ns3:ValorDeducoes>
<ns3:ValorPis>0.00</ns3:ValorPis>
<ns3:ValorCofins>0.00</ns3:ValorCofins>
<ns3:ValorInss>0.00</ns3:ValorInss>
<ns3:ValorIr>0.00</ns3:ValorIr>
<ns3:ValorCsll>0.00</ns3:ValorCsll>
<ns3:OutrasRetencoes>0.00</ns3:OutrasRetencoes>
<ns3:ValorIss>9.17</ns3:ValorIss>
<ns3:Aliquota>4.0751</ns3:Aliquota>
<ns3:DescontoIncondicionado>0.00</ns3:DescontoIncondicionado>
<ns3:DescontoCondicionado>0.00</ns3:DescontoCondicionado>
</ns3:Valores>
<ns3:IssRetido>2</ns3:IssRetido>
<ns3:ResponsavelRetencao>1</ns3:ResponsavelRetencao>
<ns3:ItemListaServico>04.02</ns3:ItemListaServico>
<ns3:CodigoCnae>8640207</ns3:CodigoCnae>
<ns3:CodigoTributacaoMunicipio>0000040000002</ns3:CodigoTributacaoMunicipio>
<ns3:Discriminacao>ULTRASSOM OBSTETRICA DO 2/3 TRI. - PEDIDO: 7184 PGT: CREDITO -225.0 </ns3:Discriminacao>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:ExigibilidadeISS>1</ns3:ExigibilidadeISS>
<ns3:MunicipioIncidencia>1100023</ns3:MunicipioIncidencia>
</ns3:Servico>
<ns3:Prestador>
<ns3:CpfCnpj>
<ns3:Cnpj>41283279000145</ns3:Cnpj>
</ns3:CpfCnpj>
<ns3:InscricaoMunicipal>000151625</ns3:InscricaoMunicipal>
</ns3:Prestador>
<ns3:Tomador>
<ns3:IdentificacaoTomador>
<ns3:CpfCnpj>
<ns3:Cpf>01600304206</ns3:Cpf>
</ns3:CpfCnpj>
</ns3:IdentificacaoTomador>
<ns3:RazaoSocial>JHENIFER RODRIGUES GOMES</ns3:RazaoSocial>
<ns3:Endereco>
<ns3:Endereco>Avenida MACHADINHO</ns3:Endereco>
<ns3:Numero>2106</ns3:Numero>
<ns3:Bairro>JARDIM AMERICA</ns3:Bairro>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:Uf>RO</ns3:Uf>
<ns3:CodigoPais>1058</ns3:CodigoPais>
<ns3:Cep>76870000</ns3:Cep>
</ns3:Endereco>
<ns3:Contato/>
</ns3:Tomador>
<ns3:RegimeEspecialTributacao>6</ns3:RegimeEspecialTributacao>
<ns3:OptanteSimplesNacional>1</ns3:OptanteSimplesNacional>
<ns3:IncentivoFiscal>2</ns3:IncentivoFiscal>
</ns3:InfDeclaracaoPrestacaoServico>
</ns3:DeclaracaoPrestacaoServico>
</ns3:InfNfse>
</ns3:Nfse>
</CompNfse>
<CompNfse>
<ns3:Nfse versao="2.01">
<ns3:InfNfse Id="47122425UPAC9BVHAL02BYANVJTBTYPN">
<ns3:Numero>53</ns3:Numero>
<ns3:CodigoVerificacao>SXFM5KRH1</ns3:CodigoVerificacao>
<ns3:DataEmissao>2025-08-30T12:00:27</ns3:DataEmissao>
<ns3:OutrasInformacoes>Val. Aprox. Tributos:</ns3:OutrasInformacoes>
<ns3:ValoresNfse>
<ns3:BaseCalculo>430.00</ns3:BaseCalculo>
<ns3:Aliquota>4.0751</ns3:Aliquota>
<ns3:ValorIss>17.52</ns3:ValorIss>
<ns3:ValorLiquidoNfse>430.00</ns3:ValorLiquidoNfse>
</ns3:ValoresNfse>
<ns3:PrestadorServico>
<ns3:IdentificacaoPrestador>
<ns3:CpfCnpj>
<ns3:Cnpj>41283279000145</ns3:Cnpj>
</ns3:CpfCnpj>
<ns3:InscricaoMunicipal>24943</ns3:InscricaoMunicipal>
</ns3:IdentificacaoPrestador>
<ns3:RazaoSocial>BW PRESTAÇÃO DE SERVIÇOS MÉDICOS LTDA</ns3:RazaoSocial>
<ns3:NomeFantasia>DIRON SERVICOS MEDICOS</ns3:NomeFantasia>
<ns3:Endereco>
<ns3:Endereco>RUA INGAZEIRO</ns3:Endereco>
<ns3:Numero>1878</ns3:Numero>
<ns3:Complemento>SALA 08</ns3:Complemento>
<ns3:Bairro>SETOR 01</ns3:Bairro>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:Uf>RO</ns3:Uf>
<ns3:CodigoPais>1058</ns3:CodigoPais>
<ns3:Cep>76870084</ns3:Cep>
</ns3:Endereco>
<ns3:Contato>
<ns3:Telefone/>
<ns3:Email>ATENDIMENTO@DUETI.COM.BR</ns3:Email>
</ns3:Contato>
</ns3:PrestadorServico>
<ns3:OrgaoGerador>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:Uf>RO</ns3:Uf>
</ns3:OrgaoGerador>
<ns3:DeclaracaoPrestacaoServico>
<ns3:InfDeclaracaoPrestacaoServico>
<ns3:Competencia>2025-08-30</ns3:Competencia>
<ns3:Servico>
<ns3:Valores>
<ns3:ValorServicos>430.00</ns3:ValorServicos>
<ns3:ValorDeducoes>0.00</ns3:ValorDeducoes>
<ns3:ValorPis>0.00</ns3:ValorPis>
<ns3:ValorCofins>0.00</ns3:ValorCofins>
<ns3:ValorInss>0.00</ns3:ValorInss>
<ns3:ValorIr>0.00</ns3:ValorIr>
<ns3:ValorCsll>0.00</ns3:ValorCsll>
<ns3:OutrasRetencoes>0.00</ns3:OutrasRetencoes>
<ns3:ValorIss>17.52</ns3:ValorIss>
<ns3:Aliquota>4.0751</ns3:Aliquota>
<ns3:DescontoIncondicionado>0.00</ns3:DescontoIncondicionado>
<ns3:DescontoCondicionado>0.00</ns3:DescontoCondicionado>
</ns3:Valores>
<ns3:IssRetido>2</ns3:IssRetido>
<ns3:ResponsavelRetencao>1</ns3:ResponsavelRetencao>
<ns3:ItemListaServico>04.02</ns3:ItemListaServico>
<ns3:CodigoCnae>8640207</ns3:CodigoCnae>
<ns3:CodigoTributacaoMunicipio>0000040000002</ns3:CodigoTributacaoMunicipio>
<ns3:Discriminacao>ULTRASSOM DE BOLSA ESCROTAL COM DOPPLER - PEDIDO: 7185 PGT: CREDITO-250.0 | ULTRASSOM DA REGIAO INGUINAL ESQUERDA - PEDIDO: 7186 PGT: CREDITO -180.0 </ns3:Discriminacao>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:ExigibilidadeISS>1</ns3:ExigibilidadeISS>
<ns3:MunicipioIncidencia>1100023</ns3:MunicipioIncidencia>
</ns3:Servico>
<ns3:Prestador>
<ns3:CpfCnpj>
<ns3:Cnpj>41283279000145</ns3:Cnpj>
</ns3:CpfCnpj>
<ns3:InscricaoMunicipal>000151625</ns3:InscricaoMunicipal>
</ns3:Prestador>
<ns3:Tomador>
<ns3:IdentificacaoTomador>
<ns3:CpfCnpj>
<ns3:Cpf>92820530249</ns3:Cpf>
</ns3:CpfCnpj>
</ns3:IdentificacaoTomador>
<ns3:RazaoSocial>ALBERTO PEREIRA DOS SANTOS </ns3:RazaoSocial>
<ns3:Endereco>
<ns3:Endereco>..</ns3:Endereco>
<ns3:Numero>..</ns3:Numero>
<ns3:Bairro>..</ns3:Bairro>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:Uf>RO</ns3:Uf>
<ns3:Cep>00000000</ns3:Cep>
</ns3:Endereco>
<ns3:Contato/>
</ns3:Tomador>
<ns3:RegimeEspecialTributacao>6</ns3:RegimeEspecialTributacao>
<ns3:OptanteSimplesNacional>1</ns3:OptanteSimplesNacional>
<ns3:IncentivoFiscal>2</ns3:IncentivoFiscal>
</ns3:InfDeclaracaoPrestacaoServico>
</ns3:DeclaracaoPrestacaoServico>
</ns3:InfNfse>
</ns3:Nfse>
</CompNfse>
<CompNfse>
<ns3:Nfse versao="2.01">
<ns3:InfNfse Id="4712231ZLND23UCRVAGD3658OAF8LPKK">
<ns3:Numero>52</ns3:Numero>
<ns3:CodigoVerificacao>KIX8Z8950</ns3:CodigoVerificacao>
<ns3:DataEmissao>2025-08-30T11:57:48</ns3:DataEmissao>
<ns3:OutrasInformacoes>Val. Aprox. Tributos:</ns3:OutrasInformacoes>
<ns3:ValoresNfse>
<ns3:BaseCalculo>225.00</ns3:BaseCalculo>
<ns3:Aliquota>4.0751</ns3:Aliquota>
<ns3:ValorIss>9.17</ns3:ValorIss>
<ns3:ValorLiquidoNfse>225.00</ns3:ValorLiquidoNfse>
</ns3:ValoresNfse>
<ns3:PrestadorServico>
<ns3:IdentificacaoPrestador>
<ns3:CpfCnpj>
<ns3:Cnpj>41283279000145</ns3:Cnpj>
</ns3:CpfCnpj>
<ns3:InscricaoMunicipal>24943</ns3:InscricaoMunicipal>
</ns3:IdentificacaoPrestador>
<ns3:RazaoSocial>BW PRESTAÇÃO DE SERVIÇOS MÉDICOS LTDA</ns3:RazaoSocial>
<ns3:NomeFantasia>DIRON SERVICOS MEDICOS</ns3:NomeFantasia>
<ns3:Endereco>
<ns3:Endereco>RUA INGAZEIRO</ns3:Endereco>
<ns3:Numero>1878</ns3:Numero>
<ns3:Complemento>SALA 08</ns3:Complemento>
<ns3:Bairro>SETOR 01</ns3:Bairro>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:Uf>RO</ns3:Uf>
<ns3:CodigoPais>1058</ns3:CodigoPais>
<ns3:Cep>76870084</ns3:Cep>
</ns3:Endereco>
<ns3:Contato>
<ns3:Telefone/>
<ns3:Email>ATENDIMENTO@DUETI.COM.BR</ns3:Email>
</ns3:Contato>
</ns3:PrestadorServico>
<ns3:OrgaoGerador>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:Uf>RO</ns3:Uf>
</ns3:OrgaoGerador>
<ns3:DeclaracaoPrestacaoServico>
<ns3:InfDeclaracaoPrestacaoServico>
<ns3:Competencia>2025-08-30</ns3:Competencia>
<ns3:Servico>
<ns3:Valores>
<ns3:ValorServicos>225.00</ns3:ValorServicos>
<ns3:ValorDeducoes>0.00</ns3:ValorDeducoes>
<ns3:ValorPis>0.00</ns3:ValorPis>
<ns3:ValorCofins>0.00</ns3:ValorCofins>
<ns3:ValorInss>0.00</ns3:ValorInss>
<ns3:ValorIr>0.00</ns3:ValorIr>
<ns3:ValorCsll>0.00</ns3:ValorCsll>
<ns3:OutrasRetencoes>0.00</ns3:OutrasRetencoes>
<ns3:ValorIss>9.17</ns3:ValorIss>
<ns3:Aliquota>4.0751</ns3:Aliquota>
<ns3:DescontoIncondicionado>0.00</ns3:DescontoIncondicionado>
<ns3:DescontoCondicionado>0.00</ns3:DescontoCondicionado>
</ns3:Valores>
<ns3:IssRetido>2</ns3:IssRetido>
<ns3:ResponsavelRetencao>1</ns3:ResponsavelRetencao>
<ns3:ItemListaServico>04.02</ns3:ItemListaServico>
<ns3:CodigoCnae>8640207</ns3:CodigoCnae>
<ns3:CodigoTributacaoMunicipio>0000040000002</ns3:CodigoTributacaoMunicipio>
<ns3:Discriminacao>ULTRASSOM OBSTETRICA DO 2/3 TRI - PEDIDO: 7193 PGT: DEBITO -225.0 </ns3:Discriminacao>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:ExigibilidadeISS>1</ns3:ExigibilidadeISS>
<ns3:MunicipioIncidencia>1100023</ns3:MunicipioIncidencia>
</ns3:Servico>
<ns3:Prestador>
<ns3:CpfCnpj>
<ns3:Cnpj>41283279000145</ns3:Cnpj>
</ns3:CpfCnpj>
<ns3:InscricaoMunicipal>000151625</ns3:InscricaoMunicipal>
</ns3:Prestador>
<ns3:Tomador>
<ns3:IdentificacaoTomador>
<ns3:CpfCnpj>
<ns3:Cpf>70569082250</ns3:Cpf>
</ns3:CpfCnpj>
</ns3:IdentificacaoTomador>
<ns3:RazaoSocial>LARISSA SILVA MONTREZOL</ns3:RazaoSocial>
<ns3:Endereco>
<ns3:Endereco>PEDRO NAVA </ns3:Endereco>
<ns3:Numero>4026</ns3:Numero>
<ns3:Bairro>SETOR 06</ns3:Bairro>
<ns3:CodigoMunicipio>1100023</ns3:CodigoMunicipio>
<ns3:Uf>RO</ns3:Uf>
<ns3:CodigoPais>1058</ns3:CodigoPais>
<ns3:Cep>76873638</ns3:Cep>
</ns3:Endereco>
<ns3:Contato/>
</ns3:Tomador>
<ns3:RegimeEspecialTributacao>6</ns3:RegimeEspecialTributacao>
<ns3:OptanteSimplesNacional>1</ns3:OptanteSimplesNacional>
<ns3:IncentivoFiscal>2</ns3:IncentivoFiscal>
</ns3:InfDeclaracaoPrestacaoServico>
</ns3:DeclaracaoPrestacaoServico>
</ns3:InfNfse>
</ns3:Nfse>
</CompNfse>
</LoteNotaFiscal>'''

    # Criar arquivo XML temporário
    with open('temp_lote.xml', 'w', encoding='utf-8') as f:
        f.write(xml_content)

    # Parse do XML
    tree = ET.parse('temp_lote.xml')
    root = tree.getroot()

    print(f"Root tag: {root.tag}")

    # Buscar empresa (usar a primeira disponível)
    try:
        empresa = Empresa.objects.first()
        if not empresa:
            print("ERRO: Nenhuma empresa encontrada no banco")
            return
        print(f"Empresa: {empresa.razao} (CNPJ: {empresa.cnpj})")
    except Exception as e:
        print(f"ERRO ao buscar empresa: {str(e)}")
        return

    # Criar usuário mock
    class MockUser:
        def __init__(self):
            self.username = 'test_user'

    user = MockUser()

    # Testar preview primeiro
    print("\n=== TESTANDO PREVIEW ===")
    try:
        preview_result = extract_lote_preview(root, empresa)
        print(f"Preview encontrou {len(preview_result)} notas:")
        for i, nota in enumerate(preview_result, 1):
            print(f"  {i}. Número: {nota.get('numero_nota')}, Cliente: {nota.get('cliente')}, Valor: {nota.get('valor_liquido')}")
    except Exception as e:
        print(f"ERRO no preview: {str(e)}")
        import traceback
        traceback.print_exc()

    # Testar importação
    print("\n=== TESTANDO IMPORTAÇÃO ===")
    try:
        resultado = import_lote_nfse(root, user, empresa)
        print("Resultado da importação:")
        print(f"  Total processadas: {resultado.get('total_processadas', 0)}")
        print(f"  Total importadas: {resultado.get('total_importadas', 0)}")
        print(f"  Total ignoradas: {resultado.get('total_ignoradas', 0)}")

        print("\nNotas importadas:")
        for nota in resultado.get('notas_importadas', []):
            print(f"  - {nota}")

        print("\nNotas ignoradas:")
        for nota in resultado.get('notas_ignoradas', []):
            print(f"  - {nota}")

    except Exception as e:
        print(f"ERRO na importação: {str(e)}")
        import traceback
        traceback.print_exc()

    # Limpar arquivo temporário
    if os.path.exists('temp_lote.xml'):
        os.remove('temp_lote.xml')

if __name__ == '__main__':
    test_import_lote()