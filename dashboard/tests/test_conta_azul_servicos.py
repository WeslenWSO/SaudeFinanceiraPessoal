from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from dashboard.conta_azul.servicos import (
    aplicar_item_api_ao_servico,
    extrair_fiscal_de_resposta,
    importar_servicos,
    montar_payload_fiscal,
    replicar_fiscal_servicos,
)
from dashboard.conta_azul.client import ContaAzulAPIError
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

    def test_replicar_fiscal_copia_campos_e_marca_pendente(self):
        empresa = Empresa.objects.create(razao='Repl', cnpj='12345678000197')
        origem = ServicoContaAzul.objects.create(
            empresa=empresa,
            conta_azul_id='orig-1',
            codigo='M1',
            c_class_trib='000001',
            codigo_nbs='1.2301.22.00',
            indicador_operacao='030101',
            natureza_operacao='Tributação normal',
        )
        dest1 = ServicoContaAzul.objects.create(
            empresa=empresa,
            conta_azul_id='dest-1',
            codigo='D1',
        )
        dest2 = ServicoContaAzul.objects.create(
            empresa=empresa,
            conta_azul_id='dest-2',
            codigo='D2',
        )
        stats = replicar_fiscal_servicos(empresa, origem, [dest1.pk, dest2.pk, origem.pk])
        self.assertEqual(stats['replicados'], 2)
        dest1.refresh_from_db()
        dest2.refresh_from_db()
        self.assertEqual(dest1.c_class_trib, '000001')
        self.assertEqual(dest1.codigo_nbs, '1.2301.22.00')
        self.assertTrue(dest1.fiscal_pendente_envio)
        self.assertEqual(dest2.indicador_operacao, '030101')

    def test_import_nao_apaga_fiscal_quando_api_retorna_vazio(self):
        empresa = Empresa.objects.create(razao='Keep', cnpj='12345678000195')
        servico = ServicoContaAzul.objects.create(
            empresa=empresa,
            conta_azul_id='uuid-2',
            c_class_trib='000001',
            codigo_nbs='1.2301.22.00',
            fiscal_pendente_envio=False,
        )
        item = {'codigo': 'S2', 'descricao': 'Atualizado', 'dados_fiscais': {}}
        aplicar_item_api_ao_servico(servico, item, preservar_fiscal_pendente=False)
        self.assertEqual(servico.c_class_trib, '000001')
        self.assertEqual(servico.codigo_nbs, '1.2301.22.00')

    def test_import_atualiza_cadastro_sem_apagar_fiscal(self):
        empresa = Empresa.objects.create(razao='Keep3', cnpj='12345678000194')
        servico = ServicoContaAzul.objects.create(
            empresa=empresa,
            conta_azul_id='uuid-3',
            c_class_trib='000001',
            indicador_operacao='030101',
            fiscal_pendente_envio=False,
        )
        item = {
            'descricao': 'Exame RM',
            'codigo_cnae': '8630503',
            'lei_116': '04.02',
            'codigo_municipio_servico': '1148541402',
        }
        aplicar_item_api_ao_servico(servico, item)
        self.assertEqual(servico.lei_116, '04.02')
        self.assertEqual(servico.codigo_cnae, '8630503')
        self.assertEqual(servico.codigo_servico_municipal, '1148541402')
        self.assertEqual(servico.c_class_trib, '000001')
        self.assertEqual(servico.indicador_operacao, '030101')

    def test_replicar_fiscal_exige_origem_com_dados(self):
        empresa = Empresa.objects.create(razao='Repl2', cnpj='12345678000196')
        origem = ServicoContaAzul.objects.create(empresa=empresa, conta_azul_id='vazio')
        with self.assertRaises(ContaAzulAPIError):
            replicar_fiscal_servicos(empresa, origem, [])

    def test_importar_nao_busca_detalhe_por_id(self):
        empresa = Empresa.objects.create(razao='Imp', cnpj='12345678000193')
        client = MagicMock()
        client.buscar_servicos.return_value = [
            {
                'id': 'uuid-import-1',
                'codigo': 'S1',
                'descricao': 'Serviço teste',
                'codigo_cnae': '8630503',
                'lei_116': '04.02',
                'codigo_municipio_servico': '040205',
            }
        ]
        stats = importar_servicos(empresa, client)
        self.assertEqual(stats['criados'], 1)
        client.buscar_servico_por_id.assert_not_called()
        obj = ServicoContaAzul.objects.get(empresa=empresa, conta_azul_id='uuid-import-1')
        self.assertEqual(obj.lei_116, '04.02')
        self.assertEqual(obj.codigo_servico_municipal, '040205')
