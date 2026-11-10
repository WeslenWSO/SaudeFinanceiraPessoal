from decimal import Decimal
from datetime import date
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase
from openpyxl import load_workbook

from faturamento_medico.views import (
    _excel_texto_nf_sem_valor_linha,
    _montar_workbook_lancamentos_solicitante,
    _valor_celula_excel,
)


class ExcelTextoNfSemValorTests(SimpleTestCase):
    def test_uma_nota_sem_valor_monetario(self):
        linha = {
            'qtd_notas': 1,
            'notas_vinculadas': [
                {
                    'numero': '6043',
                    'valor_fmt': '440,00',
                    'forma_pagamento': 'PIX',
                    'forma_pagamento_exibicao': 'PIX R$ 440,00',
                },
            ],
        }
        texto = _excel_texto_nf_sem_valor_linha(linha)
        self.assertEqual(texto, 'NF 6043 - PIX')
        self.assertNotIn('440', texto)
        self.assertNotIn('R$', texto)

    def test_sem_nf(self):
        self.assertEqual(_excel_texto_nf_sem_valor_linha({'qtd_notas': 0}), 'Sem NF')


class ValorCelulaExcelTests(SimpleTestCase):
    def test_remove_caracteres_controle(self):
        texto = 'Paciente\x00com\x07controle'
        limpo = _valor_celula_excel(texto)
        self.assertNotIn('\x00', limpo)
        self.assertNotIn('\x07', limpo)
        self.assertEqual(limpo, 'Pacientecomcontrole')

    def test_workbook_salva_com_texto_sujo(self):
        empresa = MagicMock(razao='Clínica\x01 Teste', cnpj='00.000.000/0001-00')
        coleta = {
            'periodo_fmt': '01/01/2025 → 31/01/2025',
            'grid_linhas': [
                {
                    'data_fmt': '10/01/2025',
                    'paciente': 'João\x02 Silva',
                    'procedimento': 'RM',
                    'modalidade': 'MR',
                    'status_agendamento': 'Realizado',
                    'status': 'Conferido',
                    'valor': Decimal('100'),
                    'valor_desconto_efetivo': Decimal('0'),
                    'solicitante': 'Dr. A',
                    'medico': 'Dr. B',
                    'convenio': 'Particular',
                    'qtd_notas': 0,
                    'notas_vinculadas': [],
                },
            ],
            'valor_total': Decimal('100'),
        }
        wb = _montar_workbook_lancamentos_solicitante(empresa, coleta)
        buffer = BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        wb2 = load_workbook(buffer)
        self.assertEqual(wb2.active.title, 'Lancamentos')


class ExportarLancamentosExcelViewTests(SimpleTestCase):
    def test_retorna_403_sem_empresa_sessao(self):
        from faturamento_medico.views import exportar_lancamentos_solicitante_excel

        rf = RequestFactory()
        req = rf.get('/lancamentos/excel/')
        req.user = AnonymousUser()
        req.session = {}
        resp = exportar_lancamentos_solicitante_excel(req)
        self.assertIn(resp.status_code, (302, 403))

    @patch('faturamento_medico.views._coletar_grid_linhas_exames_solicitante')
    def test_fluxo_minimo_com_mock(self, mock_coleta):
        from faturamento_medico.views import exportar_lancamentos_solicitante_excel

        mock_coleta.return_value = {
            'empresa_id': 1,
            'di': date(2025, 1, 1),
            'df': date(2025, 1, 31),
            'periodo_fmt': '01/01/2025 → 31/01/2025',
            'grid_linhas': [],
            'valor_total': 0,
        }
        empresa = MagicMock(razao='Empresa', cnpj=None)

        rf = RequestFactory()
        req = rf.get('/lancamentos/excel/')
        user = MagicMock()
        user.is_authenticated = True
        req.user = user
        req.session = {'empresa_id': 1}

        with patch('faturamento_medico.views.Empresa.objects.get', return_value=empresa):
            resp = exportar_lancamentos_solicitante_excel(req)

        self.assertEqual(resp.status_code, 200)
        self.assertIn('spreadsheetml', resp['Content-Type'])
        load_workbook(BytesIO(resp.content))
