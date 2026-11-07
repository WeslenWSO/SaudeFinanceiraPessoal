from datetime import date
from decimal import Decimal

from django.test import TestCase

from contasareceber.models import ContaAReceber
from dashboard.services.montar_visao_geral import _sum_receitas_competencia
from empresa.models import Empresa
from notasfiscais.models import NotaFiscalServico


class ReceitasCompetenciaEmissaoTests(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(razao='Teste Ltda', cnpj='12345678000199')

    def test_prioriza_data_emissao_da_nf(self):
        nf = NotaFiscalServico.objects.create(
            empresa=self.empresa,
            numero_nota='100',
            data_emissao=date(2026, 10, 5),
            valor_bruto=Decimal('1000.00'),
            valor_liquido=Decimal('1000.00'),
        )
        ContaAReceber.objects.create(
            empresa=self.empresa,
            cliente='Cliente A',
            nota=nf,
            data_emissao=date(2026, 11, 1),
            data_vencimento=date(2026, 11, 15),
            valor_a_receber=Decimal('1000.00'),
            status='pago',
        )
        out = _sum_receitas_competencia(
            self.empresa, date(2026, 10, 1), date(2026, 10, 31)
        )
        self.assertEqual(out, Decimal('1000.00'))
        fora = _sum_receitas_competencia(
            self.empresa, date(2026, 11, 1), date(2026, 11, 30)
        )
        self.assertEqual(fora, Decimal('0'))

    def test_sem_nf_usa_emissao_do_titulo(self):
        ContaAReceber.objects.create(
            empresa=self.empresa,
            cliente='Cliente B',
            data_emissao=date(2026, 10, 20),
            data_vencimento=date(2026, 11, 10),
            valor_a_receber=Decimal('500.00'),
            status='pendente',
        )
        out = _sum_receitas_competencia(
            self.empresa, date(2026, 10, 1), date(2026, 10, 31)
        )
        self.assertEqual(out, Decimal('500.00'))
