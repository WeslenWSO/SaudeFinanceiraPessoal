from unittest.mock import MagicMock

from django.test import SimpleTestCase

from decimal import Decimal

from faturamento_medico.services.acerto_caixa import (
    _eh_aguardando_faturamento,
    _item_conferencia_pendente,
    montar_resumo_modalidades_acerto,
)


class AcertoCaixaConferenciaHelpersTests(SimpleTestCase):
    def test_aguardando_faturamento_agendamento(self):
        self.assertTrue(_eh_aguardando_faturamento('Aguardando faturamento'))
        self.assertTrue(_eh_aguardando_faturamento('Aguardando o faturamento'))
        self.assertFalse(_eh_aguardando_faturamento('Concluído'))
        self.assertFalse(_eh_aguardando_faturamento('Confirmado'))

    def test_item_pendente_vs_conferido(self):
        pendente = MagicMock(
            status_conferencia='PENDENTE',
            conferido=False,
        )
        conferido = MagicMock(
            status_conferencia='CONFERIDO',
            conferido=True,
        )
        falta_guia = MagicMock(
            status_conferencia='FALTA DE GUIA',
            conferido=False,
        )
        self.assertTrue(_item_conferencia_pendente(pendente))
        self.assertFalse(_item_conferencia_pendente(conferido))
        self.assertFalse(_item_conferencia_pendente(falta_guia))

    def test_resumo_modalidade_inclui_outros_e_grafico_valor_bate_total(self):
        linhas = [
            {'modalidade': 'US', 'total_item': Decimal('999'), 'valor_pago': Decimal('100')},
            {'modalidade': 'RM', 'total_item': Decimal('999'), 'valor_pago': Decimal('50')},
            {
                'modalidade': 'DX',
                'total_item': Decimal('9999'),
                'valor_pago': Decimal('2000'),
                'procedimento': 'Densitometria',
            },
        ]
        ctx = montar_resumo_modalidades_acerto(linhas)
        self.assertEqual(ctx['resumo_quantidade_total'], 3)
        self.assertEqual(ctx['resumo_outros_quantidade'], 1)
        self.assertEqual(len(ctx['modalidades_fora_resumo']), 1)
        self.assertEqual(ctx['modalidades_fora_resumo'][0]['codigo'], 'DX')
        us = next(m for m in ctx['resumo_modalidades'] if m['codigo'] == 'US')
        mr = next(m for m in ctx['resumo_modalidades'] if m['codigo'] == 'MR')
        self.assertEqual(mr['quantidade'], 1)
        self.assertEqual(us['quantidade'], 1)
        self.assertAlmostEqual(sum(ctx['grafico_modalidade_valores']), 2150.0)
