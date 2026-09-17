from decimal import Decimal

from django.test import TestCase

from dashboard.conta_azul.servicos import (
    aplicar_item_api_ao_servico,
    extrair_fiscal_de_resposta,
    montar_payload_fiscal,
)
from dashboard.models import ServicoContaAzul
from empresa.models import Empresa


class ExtrairFiscalServicoTest(TestCase):
    def test_extrai_campos_aninhados_e_aliquotas(self):
        item = {
            'codigo': 'S1',
            'descricao': 'Exame imagem',
            'codigo_cnae': '8630503',
            'lei_116': '04.02',
            'codigo_servico_municipal': '040205',
            'dados_fiscais': {
                'codigo_nbs': '1.2301.22.00',
                'codigo_indicador_operacao': '030101',
                'codigo_classificacao_tributaria': '000001',
                'aliquota_cbs': 0.9,
                'aliquota_ibs_estadual': 0.1,
                'aliquota_ibs_municipal': 0,
            },
        }
        fiscal = extrair_fiscal_de_resposta(item)
        self.assertEqual(fiscal['codigo_nbs'], '1.2301.22.00')
        self.assertEqual(fiscal['indicador_operacao'], '030101')
        self.assertEqual(fiscal['c_class_trib'], '000001')
        self.assertEqual(fiscal['aliquota_cbs'], Decimal('0.9'))
        self.assertEqual(fiscal['aliquota_ibs'], Decimal('0.1'))
        self.assertEqual(fiscal['aliquota_ibs_municipal'], Decimal('0'))

    def test_montar_payload_nao_inclui_aliquotas(self):
        empresa = Empresa.objects.create(razao='Teste', cnpj='12345678000199')
        servico = ServicoContaAzul(
            empresa=empresa,
            c_class_trib='000001',
            codigo_nbs='1.2301.22.00',
            indicador_operacao='030101',
            aliquota_cbs=Decimal('0.9'),
            aliquota_ibs=Decimal('0.1'),
        )
        payload = montar_payload_fiscal(servico)
        self.assertEqual(payload['codigo_classificacao_tributaria'], '000001')
        self.assertEqual(payload['codigo_nbs'], '1.2301.22.00')
        self.assertEqual(payload['codigo_indicador_operacao'], '030101')
        self.assertNotIn('aliquota_cbs', payload)
        self.assertNotIn('aliquota_ibs', payload)
        self.assertNotIn('aliquota_ibs_estadual', payload)

    def test_import_preserva_fiscal_pendente(self):
        empresa = Empresa.objects.create(razao='Teste2', cnpj='12345678000198')
        servico = ServicoContaAzul.objects.create(
            empresa=empresa,
            conta_azul_id='uuid-1',
            codigo='S1',
            c_class_trib='999999',
            fiscal_pendente_envio=True,
        )
        item = {
            'codigo': 'S1',
            'descricao': 'Novo nome',
            'dados_fiscais': {'codigo_classificacao_tributaria': '000001'},
        }
        aplicar_item_api_ao_servico(servico, item, preservar_fiscal_pendente=True)
        self.assertEqual(servico.c_class_trib, '999999')
        self.assertEqual(servico.descricao, 'Novo nome')
