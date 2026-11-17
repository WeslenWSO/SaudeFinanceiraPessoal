from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from contasapagar.services.relatorio_despesas_recorrentes import (
    PagamentoLinha,
    agrupar_despesas_recorrentes,
)


class RelatorioDespesasRecorrentesTest(SimpleTestCase):
    def test_agrupa_mesma_descricao_e_dia(self):
        pagamentos = [
            PagamentoLinha('ALUGUEL', 'Aluguel', 5, Decimal('1500'), date(2026, 8, 5), 1),
            PagamentoLinha('ALUGUEL', 'Aluguel', 5, Decimal('1500'), date(2026, 9, 5), 2),
            PagamentoLinha('ALUGUEL', 'Aluguel', 5, Decimal('1500'), date(2026, 10, 5), 3),
            PagamentoLinha('ENERGIA', 'Energia', 12, Decimal('300'), date(2026, 9, 12), 4),
        ]
        grupos = agrupar_despesas_recorrentes(pagamentos)
        self.assertEqual(len(grupos), 1)
        g = grupos[0]
        self.assertEqual(g.descricao, 'Aluguel')
        self.assertEqual(g.dia, 5)
        self.assertEqual(g.quantidade, 3)

    def test_ignora_pagamento_unico(self):
        pagamentos = [
            PagamentoLinha('UNICA', 'Unica', 1, Decimal('99'), date(2026, 11, 1), 1),
        ]
        self.assertEqual(agrupar_despesas_recorrentes(pagamentos), [])
