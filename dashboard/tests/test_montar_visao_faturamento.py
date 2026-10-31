from decimal import Decimal

from django.test import SimpleTestCase

from dashboard.montar_visao_faturamento import _linhas_de_agregacao


class MontarVisaoFaturamentoTest(SimpleTestCase):
    def test_linhas_de_agregacao_percentual(self):
        rows = [{'valor': Decimal('700'), 'quantidade': 7}]
        linhas = _linhas_de_agregacao(
            rows,
            rotulo_fn=lambda r: 'PIX',
            total_valor=Decimal('1000'),
        )
        self.assertEqual(linhas[0]['rotulo'], 'PIX')
        self.assertEqual(linhas[0]['percentual_fmt'], '70,00%')
