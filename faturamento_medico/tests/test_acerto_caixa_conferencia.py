from unittest.mock import MagicMock

from django.test import SimpleTestCase

from decimal import Decimal

from datetime import date

from faturamento_medico.services.acerto_caixa import (
    _eh_aguardando_faturamento,
    _item_conferencia_pendente,
    filtrar_linhas_acerto_caixa,
    montar_regua_dias_acerto,
    montar_resumo_modalidades_acerto,
    montar_resumo_viabilidade_acerto,
    montar_resumo_viabilidade_por_mes_acerto,
    recomputar_resumos_acerto_caixa_de_linhas,
    url_query_acerto_caixa,
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

    def test_regua_dias_mes_e_urls(self):
        filtros = {'caixa': ['1'], 'somente_marcados': True}
        ctx = montar_regua_dias_acerto(filtros, date(2026, 11, 1), date(2026, 11, 30))
        self.assertEqual(len(ctx['regua_dias']), 30)
        self.assertIn('Novembro', ctx['regua_titulo'])
        dia15 = next(d for d in ctx['regua_dias'] if d['numero'] == 15)
        self.assertTrue(dia15['no_intervalo'])
        qs = url_query_acerto_caixa(filtros, date(2026, 11, 15), date(2026, 11, 15))
        self.assertIn('data_inicio=2026-11-15', qs)
        self.assertIn('caixa=1', qs)
        self.assertEqual(len(ctx['regua_botoes_meses']), 12)
        nov = ctx['regua_botoes_meses'][10]
        self.assertTrue(nov['ativo'])
        self.assertIn('data_inicio=2026-11-01', nov['url_query'])
        self.assertIn('data_fim=2026-11-30', nov['url_query'])
        self.assertEqual(len(ctx['regua_botoes_anos']), 9)
        ativo_2026 = next(b for b in ctx['regua_botoes_anos'] if b['ano'] == 2026)
        self.assertTrue(ativo_2026['ativo'])

    def test_resumo_bate_soma_valor_pago_linhas(self):
        linhas = [
            {
                'faturamento_id': 1,
                'aguardando_faturamento': False,
                'valor_pago': Decimal('180'),
                'pagamentos_acerto': [{'rotulo': 'PIX', 'valor': Decimal('360')}],
                'forma_pgto': 'PIX R$ 360,00',
                'caixa_acerto': '',
                'caixa_exibicao': 'Cx',
            },
            {
                'faturamento_id': 1,
                'aguardando_faturamento': False,
                'valor_pago': Decimal('180'),
                'pagamentos_acerto': [{'rotulo': 'PIX', 'valor': Decimal('360')}],
                'forma_pgto': '-',
                'caixa_acerto': '',
                'caixa_exibicao': 'Cx',
            },
        ]
        pag, ag, _cx = recomputar_resumos_acerto_caixa_de_linhas(linhas)
        self.assertEqual(pag.get('PIX'), Decimal('360'))
        self.assertEqual(sum(pag.values()) + sum(ag.values()), Decimal('360'))

    def test_resumo_viabilidade_qt_valor(self):
        linhas = [
            {'convenio': 'CASSI', 'valor_pago': Decimal('100'), 'aguardando_faturamento': False},
            {'convenio': 'CASSI', 'valor_pago': Decimal('50'), 'aguardando_faturamento': False},
            {'convenio': 'GEAP', 'valor_pago': Decimal('80'), 'aguardando_faturamento': True, 'total_item': Decimal('80')},
        ]
        rows = montar_resumo_viabilidade_acerto(linhas)
        self.assertEqual(len(rows), 2)
        cassi = next(r for r in rows if r['viabilidade'] == 'CASSI')
        self.assertEqual(cassi['quantidade'], 2)
        self.assertEqual(cassi['valor'], Decimal('150'))

    def test_viabilidade_por_mes_janeiro_dezembro(self):
        linhas = [
            {
                'data_iso': '2026-01-15',
                'convenio': 'CASSI',
                'valor_pago': Decimal('100'),
                'aguardando_faturamento': False,
            },
            {
                'data_iso': '2026-02-10',
                'convenio': 'GEAP',
                'valor_pago': Decimal('50'),
                'aguardando_faturamento': False,
            },
            {
                'data_iso': '2026-02-20',
                'convenio': 'GEAP',
                'valor_pago': Decimal('30'),
                'aguardando_faturamento': False,
            },
        ]
        blocos = montar_resumo_viabilidade_por_mes_acerto(linhas, 2026)
        self.assertEqual(len(blocos), 12)
        self.assertEqual(blocos[0]['label'], 'Janeiro')
        self.assertTrue(blocos[0]['tem_dados'])
        self.assertEqual(blocos[0]['total_qt'], 1)
        self.assertEqual(blocos[1]['total_qt'], 2)
        self.assertFalse(blocos[2]['tem_dados'])
        self.assertEqual(blocos[11]['label'], 'Dezembro')
