from unittest.mock import MagicMock

from django.test import SimpleTestCase

from decimal import Decimal

from faturamento_medico.services.acerto_caixa import (
    _eh_aguardando_faturamento,
    _item_conferencia_pendente,
    filtrar_linhas_acerto_caixa,
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

    def test_filtrar_linhas_respeita_somente_marcados(self):
        linhas = [
            {
                'caixa_acerto': '',
                'marcado_acerto_caixa': True,
                'valor_pago': Decimal('10'),
                'checkin_por': 'A',
                'status_agendamento': 'Concluído',
                'horario_inicio': '10:00',
            },
            {
                'caixa_acerto': '',
                'marcado_acerto_caixa': False,
                'valor_pago': Decimal('99'),
                'checkin_por': 'A',
                'status_agendamento': 'Concluído',
                'horario_inicio': '10:00',
            },
        ]
        out = filtrar_linhas_acerto_caixa(
            linhas,
            empresa_id=1,
            filtros={'somente_marcados': True},
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['valor_pago'], Decimal('10'))

    def test_filtrar_linhas_paciente_e_convenio(self):
        linhas = [
            {
                'paciente': 'Maria Silva',
                'convenio': 'GEAP',
                'caixa_acerto': '',
                'checkin_por': 'A',
                'status_agendamento': 'Concluído',
                'horario_inicio': '10:00',
            },
            {
                'paciente': 'João Souza',
                'convenio': 'Bradesco',
                'caixa_acerto': '',
                'checkin_por': 'A',
                'status_agendamento': 'Concluído',
                'horario_inicio': '10:00',
            },
        ]
        out = filtrar_linhas_acerto_caixa(
            linhas,
            empresa_id=1,
            filtros={'paciente': 'maria', 'convenio': ['GEAP']},
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['paciente'], 'Maria Silva')
