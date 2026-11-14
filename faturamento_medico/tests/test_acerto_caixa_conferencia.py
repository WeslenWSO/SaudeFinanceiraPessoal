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
    aplicar_rotulo_solicitante_resumo_linhas,
    montar_detalhe_medico_solicitante_acerto,
    montar_detalhe_solicitante_acerto_por_nome,
    montar_resumo_solicitante_acerto,
    montar_resumo_viabilidade_matriz_mes,
    montar_resumo_viabilidade_por_mes_acerto,
    montar_contexto_matriz_anual_acerto,
    montar_contexto_matriz_mensal_por_dia,
    montar_graficos_resumo_acerto_caixa,
    periodo_eh_ano_inteiro,
    periodo_eh_mes_inteiro,
    pode_abrir_resumo_acerto_direto,
    filtrar_linhas_por_dias_resumo,
    parse_dias_resumo_request,
    recomputar_resumos_acerto_caixa_de_linhas,
    url_query_acerto_caixa,
)


class _FakeQueryDict:
    def __init__(self, data: dict):
        self._data = data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def getlist(self, key):
        val = self._data.get(key)
        if val is None:
            return []
        if isinstance(val, list):
            return val
        return [val]


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
        btn_2026 = next(b for b in ctx['regua_botoes_anos'] if b['ano'] == 2026)
        self.assertTrue(btn_2026['parcial'])
        ctx_ano = montar_regua_dias_acerto(
            filtros, date(2026, 1, 1), date(2026, 12, 31)
        )
        ativo_2026 = next(b for b in ctx_ano['regua_botoes_anos'] if b['ano'] == 2026)
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

    def test_resumo_dinheiro_usa_valor_nf_nao_rateia_valor_pago(self):
        """Soma manual por forma (ex.: Dinheiro) deve usar valores da NF, não % do valor pago."""
        linhas = [
            {
                'faturamento_id': 10,
                'aguardando_faturamento': False,
                'valor_pago': Decimal('80'),
                'pagamentos_acerto': [
                    {'rotulo': 'Dinheiro', 'valor': Decimal('100')},
                    {'rotulo': 'PIX', 'valor': Decimal('50')},
                ],
                'forma_pgto': 'Dinheiro + PIX',
                'caixa_acerto': '1',
                'caixa_exibicao': 'CAIXA TESTE',
            },
            {
                'faturamento_id': 10,
                'aguardando_faturamento': False,
                'valor_pago': Decimal('50'),
                'pagamentos_acerto': [
                    {'rotulo': 'Dinheiro', 'valor': Decimal('100')},
                    {'rotulo': 'PIX', 'valor': Decimal('50')},
                ],
                'forma_pgto': '-',
                'caixa_acerto': '1',
                'caixa_exibicao': 'CAIXA TESTE',
            },
        ]
        pag, ag, _cx = recomputar_resumos_acerto_caixa_de_linhas(linhas)
        self.assertEqual(pag.get('Dinheiro'), Decimal('100'))
        self.assertEqual(pag.get('PIX'), Decimal('50'))

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

    def test_viabilidade_matriz_meses_colunas(self):
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
        ctx = montar_resumo_viabilidade_matriz_mes(linhas, 2026)
        self.assertEqual(len(ctx['viabilidade_matriz_colunas']), 12)
        cassi = next(r for r in ctx['viabilidade_matriz_linhas'] if r['viabilidade'] == 'CASSI')
        self.assertEqual(cassi['meses'][0]['qt'], 1)
        self.assertEqual(cassi['meses'][1]['qt'], 0)
        geap = next(r for r in ctx['viabilidade_matriz_linhas'] if r['viabilidade'] == 'GEAP')
        self.assertEqual(geap['meses'][1]['qt'], 2)
        self.assertEqual(ctx['viabilidade_matriz_totais_mes'][0]['qt'], 1)
        self.assertEqual(ctx['viabilidade_matriz_totais_mes'][1]['qt'], 2)

    def test_matriz_mes_modalidade_e_viabilidade_por_dia(self):
        linhas = [
            {
                'data_iso': '2026-11-03',
                'faturamento_id': 1,
                'convenio': 'CASSI',
                'modalidade': 'US',
                'codigo_servico': 'US',
                'valor_pago': Decimal('100'),
                'aguardando_faturamento': False,
                'forma_pgto': 'PIX',
                'pagamentos_acerto': [{'rotulo': 'PIX', 'valor': Decimal('100')}],
            },
            {
                'data_iso': '2026-11-03',
                'faturamento_id': 2,
                'convenio': 'GEAP',
                'modalidade': 'MR',
                'codigo_servico': 'MR',
                'valor_pago': Decimal('200'),
                'aguardando_faturamento': False,
                'forma_pgto': 'PIX',
                'pagamentos_acerto': [{'rotulo': 'PIX', 'valor': Decimal('200')}],
            },
            {
                'data_iso': '2026-11-05',
                'faturamento_id': 3,
                'convenio': 'CASSI',
                'modalidade': 'US',
                'codigo_servico': 'US',
                'valor_pago': Decimal('50'),
                'aguardando_faturamento': False,
                'forma_pgto': 'DINHEIRO',
                'pagamentos_acerto': [],
            },
        ]
        ctx = montar_contexto_matriz_mensal_por_dia(
            linhas, date(2026, 11, 1), date(2026, 11, 30)
        )
        self.assertTrue(ctx['resumo_matriz_mes'])
        self.assertEqual(len(ctx['resumo_dias_colunas']), 30)
        self.assertEqual(ctx['resumo_dias_colunas'][2]['dia'], 3)
        us = next(
            r for r in ctx['modalidades_matriz_dia_linhas'] if r['codigo'] == 'US'
        )
        self.assertEqual(us['meses'][2]['qt'], 1)
        self.assertEqual(us['meses'][4]['qt'], 1)
        cassi = next(
            r for r in ctx['viabilidade_matriz_dia_linhas'] if r['viabilidade'] == 'CASSI'
        )
        self.assertEqual(cassi['meses'][2]['qt'], 1)
        self.assertEqual(cassi['meses'][4]['qt'], 1)
        self.assertEqual(ctx['modalidades_matriz_dia_totais'][2]['qt'], 2)
        self.assertEqual(ctx['modalidades_matriz_dia_totais'][4]['qt'], 1)
        pix = next(
            r for r in ctx['pagamento_matriz_dia_formas'] if r['rotulo'] == 'PIX'
        )
        self.assertEqual(pix['meses'][2]['qt'], 2)
        self.assertEqual(pix['meses'][4]['qt'], 0)

    def test_matriz_mes_por_dia_nao_aplica_fora_mes_inteiro(self):
        ctx = montar_contexto_matriz_mensal_por_dia(
            [], date(2026, 11, 1), date(2026, 11, 15)
        )
        self.assertFalse(ctx['resumo_matriz_mes'])

    def test_matriz_anual_modalidade_e_pagamento_por_mes(self):
        self.assertTrue(
            periodo_eh_ano_inteiro(date(2026, 1, 1), date(2026, 12, 31))
        )
        self.assertFalse(
            periodo_eh_ano_inteiro(date(2026, 11, 1), date(2026, 11, 30))
        )
        linhas = [
            {
                'data_iso': '2026-01-10',
                'faturamento_id': 1,
                'convenio': 'CASSI',
                'modalidade': 'US',
                'codigo_servico': 'US',
                'valor_pago': Decimal('100'),
                'aguardando_faturamento': False,
                'pagamentos_acerto': [{'rotulo': 'PIX', 'valor': Decimal('100')}],
                'forma_pgto': 'PIX',
                'caixa_acerto': '',
                'caixa_exibicao': 'Cx',
            },
            {
                'data_iso': '2026-02-10',
                'faturamento_id': 2,
                'convenio': 'GEAP',
                'modalidade': 'MR',
                'codigo_servico': 'MR',
                'valor_pago': Decimal('200'),
                'aguardando_faturamento': False,
                'pagamentos_acerto': [{'rotulo': 'PIX', 'valor': Decimal('200')}],
                'forma_pgto': 'PIX',
                'caixa_acerto': '',
                'caixa_exibicao': 'Cx',
            },
        ]
        ctx = montar_contexto_matriz_anual_acerto(
            linhas, date(2026, 1, 1), date(2026, 12, 31)
        )
        self.assertTrue(ctx['resumo_matriz_anual'])
        self.assertEqual(ctx['matriz_anual_colspan_secao'], 27)
        us = next(
            r for r in ctx['modalidades_matriz_linhas'] if r['codigo'] == 'US'
        )
        self.assertEqual(us['meses'][0]['qt'], 1)
        self.assertEqual(us['meses'][1]['qt'], 0)
        pix = next(r for r in ctx['pagamento_matriz_formas'] if r['rotulo'] == 'PIX')
        self.assertEqual(pix['meses'][0]['qt'], 1)
        self.assertEqual(pix['meses'][1]['qt'], 1)

    def test_matriz_anual_novembro_usa_pagamentos_acerto_nao_forma_vazia(self):
        """Coluna do mês deve seguir pagamentos_acerto (NF), não cair em Sem NF por forma '-'."""
        linhas = [
            {
                'data_iso': '2026-11-03',
                'faturamento_id': 10,
                'convenio': 'CASSI',
                'valor_pago': Decimal('100'),
                'aguardando_faturamento': False,
                'forma_pgto': '-',
                'pagamentos_acerto': [{'rotulo': 'PIX', 'valor': Decimal('100')}],
                'caixa_acerto': '',
                'caixa_exibicao': 'Cx',
            },
            {
                'data_iso': '2026-11-20',
                'faturamento_id': 11,
                'convenio': 'GEAP',
                'valor_pago': Decimal('200'),
                'aguardando_faturamento': False,
                'forma_pgto': '-',
                'pagamentos_acerto': [],
                'caixa_acerto': '',
                'caixa_exibicao': 'Cx',
            },
        ]
        ctx = montar_contexto_matriz_anual_acerto(
            linhas, date(2026, 1, 1), date(2026, 12, 31)
        )
        nov = 10
        pix = next(r for r in ctx['pagamento_matriz_formas'] if r['rotulo'] == 'PIX')
        self.assertEqual(pix['meses'][nov]['qt'], 1)
        sem_nf = next(
            r
            for r in ctx['pagamento_matriz_formas']
            if r['rotulo'] == 'Sem NF / forma não informada'
        )
        self.assertEqual(sem_nf['meses'][nov]['qt'], 1)

    def test_graficos_pagamento_inclui_aguardando(self):
        g = montar_graficos_resumo_acerto_caixa(
            [{'rotulo': 'PIX', 'total': Decimal('100')}],
            Decimal('50'),
            grafico_modalidade_labels=['US'],
            grafico_modalidade_valores=[100.0],
        )
        self.assertIn('PIX', g['grafico_pagamento_labels'])
        self.assertIn('Aguardando faturamento', g['grafico_pagamento_labels'])
        self.assertEqual(len(g['grafico_pagamento_valores']), 2)

    def test_resumo_solicitante_qt_valor(self):
        linhas = [
            {
                'medico_solicitante': 'Dr. Silva',
                'valor_pago': Decimal('100'),
                'aguardando_faturamento': False,
            },
            {
                'medico_solicitante': 'Dr. Silva',
                'valor_pago': Decimal('50'),
                'aguardando_faturamento': False,
            },
        ]
        rows = montar_resumo_solicitante_acerto(linhas)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['quantidade'], 2)
        self.assertEqual(rows[0]['valor'], Decimal('150'))

    def test_solicitante_agrupa_por_apelido(self):
        mapa = {
            'VINICIUS DE MACEDO MAGALHAES': 'VINICIUS MACEDO',
            'VINICIUS MACEDO MAGALHAES': 'VINICIUS MACEDO',
        }
        linhas = [
            {
                'medico_solicitante': 'VINICIUS DE MACEDO MAGALHAES',
                'valor_pago': Decimal('100'),
                'aguardando_faturamento': False,
            },
            {
                'medico_solicitante': 'VINICIUS MACEDO MAGALHAES',
                'valor_pago': Decimal('50'),
                'aguardando_faturamento': False,
            },
        ]
        aplicar_rotulo_solicitante_resumo_linhas(linhas, mapa)
        rows = montar_resumo_solicitante_acerto(linhas)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['solicitante'], 'VINICIUS MACEDO')
        self.assertEqual(rows[0]['quantidade'], 2)
        self.assertEqual(rows[0]['valor'], Decimal('150'))

    def test_solicitante_sem_apelido_usa_grafia(self):
        linhas = [
            {
                'medico_solicitante': 'DR. UNICO',
                'valor_pago': Decimal('10'),
                'aguardando_faturamento': False,
            },
        ]
        aplicar_rotulo_solicitante_resumo_linhas(linhas, {})
        rows = montar_resumo_solicitante_acerto(linhas)
        self.assertEqual(rows[0]['solicitante'], 'DR. UNICO')

    def test_detalhe_solicitante_viabilidade_e_pagamento(self):
        linhas = [
            {
                'faturamento_id': 1,
                'medico_solicitante': 'Dr. A',
                'convenio': 'FUSEX',
                'valor_pago': Decimal('100'),
                'aguardando_faturamento': False,
                'forma_pgto': 'PIX',
                'pagamentos_acerto': [],
            },
            {
                'faturamento_id': 2,
                'medico_solicitante': 'Dr. A',
                'convenio': 'PARTICULAR',
                'valor_pago': Decimal('40'),
                'aguardando_faturamento': False,
                'forma_pgto': 'DINHEIRO',
                'pagamentos_acerto': [],
            },
            {
                'faturamento_id': 3,
                'medico_solicitante': 'Dr. B',
                'convenio': 'GEAP',
                'valor_pago': Decimal('20'),
                'aguardando_faturamento': False,
                'forma_pgto': 'PIX',
                'pagamentos_acerto': [],
            },
        ]
        aplicar_rotulo_solicitante_resumo_linhas(linhas, {})
        det = montar_detalhe_medico_solicitante_acerto(linhas)
        self.assertIn('Dr. A', det)
        self.assertGreaterEqual(len(det['Dr. A']['modalidade']), 1)
        self.assertEqual(det['Dr. A']['total_viabilidade_qt'], 2)
        viabs = {v['viabilidade']: v['quantidade'] for v in det['Dr. A']['viabilidade']}
        self.assertEqual(viabs['FUSEX'], 1)
        self.assertEqual(viabs['PARTICULAR'], 1)
        rotulos = [p['rotulo'] for p in det['Dr. A']['pagamento']]
        self.assertIn('PIX', rotulos)
        self.assertIn('Dinheiro', rotulos)

    def test_detalhe_solicitante_por_nome(self):
        linhas = [
            {
                'faturamento_id': 1,
                'medico_solicitante': 'Dr. A',
                'convenio': 'FUSEX',
                'modalidade': 'US',
                'valor_pago': Decimal('100'),
                'aguardando_faturamento': False,
                'forma_pgto': 'PIX',
                'pagamentos_acerto': [],
            },
        ]
        aplicar_rotulo_solicitante_resumo_linhas(linhas, {})
        bloco = montar_detalhe_solicitante_acerto_por_nome(linhas, 'Dr. A')
        self.assertIsNotNone(bloco)
        self.assertGreaterEqual(len(bloco['modalidade']), 1)

    def test_grafico_convenio_torre(self):
        viab = [
            {'viabilidade': 'FUSEX', 'quantidade': 2, 'valor': Decimal('100')},
            {'viabilidade': 'PARTICULAR', 'quantidade': 1, 'valor': Decimal('50')},
        ]
        g = montar_graficos_resumo_acerto_caixa(
            [],
            Decimal('0'),
            grafico_modalidade_labels=[],
            grafico_modalidade_valores=[],
            resumo_viabilidade=viab,
        )
        self.assertEqual(g['grafico_convenio_labels'][0], 'FUSEX')
        self.assertEqual(g['grafico_convenio_valores'][0], 100.0)

    def test_pode_abrir_resumo_mes_ano_ou_dias(self):
        di_mes = date(2026, 11, 1)
        df_mes = date(2026, 11, 30)
        req_mes = MagicMock()
        req_mes.GET = _FakeQueryDict({'visao_resumo': 'mes'})
        self.assertTrue(
            periodo_eh_mes_inteiro(di_mes, df_mes)
            and pode_abrir_resumo_acerto_direto(req_mes, di_mes, df_mes)
        )
        req_sem = MagicMock()
        req_sem.GET = _FakeQueryDict({})
        self.assertFalse(pode_abrir_resumo_acerto_direto(req_sem, di_mes, df_mes))
        req_dia = MagicMock()
        req_dia.GET = _FakeQueryDict({})
        self.assertTrue(
            pode_abrir_resumo_acerto_direto(req_dia, date(2026, 11, 3), date(2026, 11, 3))
        )
        req_dias = MagicMock()
        req_dias.GET = _FakeQueryDict({'dias_resumo': ['2026-11-03', '2026-11-05']})
        self.assertTrue(pode_abrir_resumo_acerto_direto(req_dias, di_mes, df_mes))

    def test_filtrar_linhas_por_dias_resumo(self):
        linhas = [
            {'data_iso': '2026-11-03', 'valor_pago': Decimal('1')},
            {'data_iso': '2026-11-04', 'valor_pago': Decimal('2')},
            {'data_iso': '2026-11-05', 'valor_pago': Decimal('3')},
        ]
        out = filtrar_linhas_por_dias_resumo(linhas, ['2026-11-03', '2026-11-05'])
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]['data_iso'], '2026-11-03')

    def test_parse_dias_resumo_request(self):
        req = MagicMock()
        req.GET = _FakeQueryDict(
            {'dias_resumo': ['2026-11-03', '2026-11-05', 'invalido']}
        )
        self.assertEqual(parse_dias_resumo_request(req), ['2026-11-03', '2026-11-05'])
