"""Exporta o resumo do acerto de caixa (mensal por dia / anual por mês) para Excel."""

from __future__ import annotations

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


_FILL_CAB = PatternFill('solid', fgColor='B8D4E8')
_FILL_ZEBRA_A = PatternFill('solid', fgColor='DBEAFE')
_FILL_ZEBRA_B = PatternFill('solid', fgColor='F8FAFC')
_FILL_TOTAL = PatternFill('solid', fgColor='EFF6FF')
_FILL_SECAO = PatternFill('solid', fgColor='F1F5F9')


def _celula(ws, row: int, col: int, valor, *, bold=False, fill=None, center=False):
    c = ws.cell(row=row, column=col, value=valor)
    if bold:
        c.font = Font(bold=True, size=9)
    if fill:
        c.fill = fill
    if center:
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    return c


def _largura_colunas_matriz(ws, n_colunas_dados: int):
    ws.column_dimensions['A'].width = 28
    for i in range(n_colunas_dados * 2 + 2):
        ws.column_dimensions[get_column_letter(2 + i)].width = 8 if i % 2 == 0 else 11


def _escrever_titulo_aba(ws, titulo: str, subtitulo: str = ''):
    _celula(ws, 1, 1, titulo, bold=True)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
    _celula(ws, 2, 1, subtitulo)
    if subtitulo:
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=6)
    return 4


def _cabecalho_matriz(ws, start_row: int, rotulo_col: str, colunas: list[dict]) -> int:
    c0 = 1
    _celula(ws, start_row, c0, rotulo_col, bold=True, fill=_FILL_CAB, center=True)
    ws.merge_cells(
        start_row=start_row, start_column=c0, end_row=start_row + 1, end_column=c0
    )
    c = 2
    for i, col in enumerate(colunas):
        label = col.get('label_curto') or col.get('label') or ''
        _celula(ws, start_row, c, label, bold=True, fill=_FILL_CAB, center=True)
        ws.merge_cells(start_row=start_row, start_column=c, end_row=start_row, end_column=c + 1)
        fill_sub = _FILL_ZEBRA_A if i % 2 == 0 else _FILL_ZEBRA_B
        _celula(ws, start_row + 1, c, 'Qt', bold=True, fill=fill_sub, center=True)
        _celula(ws, start_row + 1, c + 1, 'R$', bold=True, fill=fill_sub, center=True)
        c += 2
    _celula(ws, start_row, c, 'Total', bold=True, fill=_FILL_CAB, center=True)
    ws.merge_cells(start_row=start_row, start_column=c, end_row=start_row, end_column=c + 1)
    _celula(ws, start_row + 1, c, 'Qt', bold=True, fill=_FILL_TOTAL, center=True)
    _celula(ws, start_row + 1, c + 1, 'R$', bold=True, fill=_FILL_TOTAL, center=True)
    return start_row + 2


def _linha_matriz(
    ws,
    row: int,
    rotulo: str,
    celulas: list[dict],
    total_qt,
    total_valor,
) -> int:
    _celula(ws, row, 1, rotulo)
    c = 2
    for i, cel in enumerate(celulas):
        fill = _FILL_ZEBRA_A if i % 2 == 0 else _FILL_ZEBRA_B
        _celula(ws, row, c, cel.get('qt', ''), center=True, fill=fill)
        _celula(ws, row, c + 1, cel.get('valor_fmt', ''), center=True, fill=fill)
        c += 2
    _celula(ws, row, c, total_qt, center=True, fill=_FILL_TOTAL)
    _celula(ws, row, c + 1, total_valor, center=True, fill=_FILL_TOTAL)
    return row + 1


def _aba_matriz_modalidade(ws, ctx: dict, por_dia: bool):
    colunas = ctx['resumo_dias_colunas'] if por_dia else ctx['resumo_meses_colunas']
    linhas = (
        ctx.get('modalidades_matriz_dia_linhas')
        if por_dia
        else ctx.get('modalidades_matriz_linhas')
    ) or []
    totais = (
        ctx.get('modalidades_matriz_dia_totais')
        if por_dia
        else ctx.get('modalidades_matriz_totais_mes')
    ) or []
    subtitulo = (
        ctx.get('resumo_matriz_mes_titulo', '')
        if por_dia
        else f"Ano {ctx.get('resumo_matriz_ano', '')}"
    )
    row = _escrever_titulo_aba(
        ws,
        'Modalidade — por dia' if por_dia else 'Modalidade — por mês',
        f'{subtitulo} · qt · R$',
    )
    row = _cabecalho_matriz(ws, row, 'Modalidade', colunas)
    for item in linhas:
        row = _linha_matriz(
            ws,
            row,
            item.get('label', ''),
            item.get('meses') or [],
            item.get('total_qt', ''),
            item.get('total_valor_fmt', ''),
        )
    _celula(ws, row, 1, 'Total', bold=True, fill=_FILL_TOTAL)
    c = 2
    for i, tot in enumerate(totais):
        fill = _FILL_ZEBRA_A if i % 2 == 0 else _FILL_ZEBRA_B
        _celula(ws, row, c, tot.get('qt', ''), bold=True, center=True, fill=fill)
        _celula(ws, row, c + 1, tot.get('valor_fmt', ''), bold=True, center=True, fill=fill)
        c += 2
    _celula(ws, row, c, ctx.get('resumo_quantidade_total', ''), bold=True, center=True, fill=_FILL_TOTAL)
    _celula(ws, row, c + 1, ctx.get('resumo_valor_total_fmt', ''), bold=True, center=True, fill=_FILL_TOTAL)
    _largura_colunas_matriz(ws, len(colunas))
    ws.freeze_panes = 'B5' if row > 4 else 'B2'


def _aba_matriz_viabilidade(ws, ctx: dict, por_dia: bool):
    if por_dia:
        colunas = ctx['resumo_dias_colunas']
        linhas = ctx.get('viabilidade_matriz_dia_linhas') or []
        totais = ctx.get('viabilidade_matriz_dia_totais') or []
        titulo = 'Viabilidade — por dia'
        subtitulo = ctx.get('resumo_matriz_mes_titulo', '')
        total_qt = ctx.get('resumo_viabilidade_total_qt', '')
        total_val = ctx.get('resumo_viabilidade_total_valor_fmt', '')
    else:
        colunas = ctx.get('viabilidade_matriz_colunas') or ctx.get('resumo_meses_colunas') or []
        linhas = ctx.get('viabilidade_matriz_linhas') or []
        totais = ctx.get('viabilidade_matriz_totais_mes') or []
        titulo = 'Viabilidade — por mês'
        subtitulo = f"Ano {ctx.get('resumo_matriz_ano', '')}"
        total_qt = ctx.get('resumo_viabilidade_total_qt', '')
        total_val = ctx.get('resumo_viabilidade_total_valor_fmt', '')

    row = _escrever_titulo_aba(ws, titulo, f'{subtitulo} · qt · R$')
    row = _cabecalho_matriz(ws, row, 'Viabilidade', colunas)
    for item in linhas:
        row = _linha_matriz(
            ws,
            row,
            (item.get('viabilidade') or '')[:80],
            item.get('meses') or [],
            item.get('total_qt', ''),
            item.get('total_valor_fmt', ''),
        )
    _celula(ws, row, 1, 'Total', bold=True, fill=_FILL_TOTAL)
    c = 2
    for i, tot in enumerate(totais):
        fill = _FILL_ZEBRA_A if i % 2 == 0 else _FILL_ZEBRA_B
        _celula(ws, row, c, tot.get('qt', ''), bold=True, center=True, fill=fill)
        _celula(ws, row, c + 1, tot.get('valor_fmt', ''), bold=True, center=True, fill=fill)
        c += 2
    _celula(ws, row, c, total_qt, bold=True, center=True, fill=_FILL_TOTAL)
    _celula(ws, row, c + 1, total_val, bold=True, center=True, fill=_FILL_TOTAL)
    _largura_colunas_matriz(ws, len(colunas))
    ws.freeze_panes = 'B5'


def _aba_matriz_pagamento(ws, ctx: dict, por_dia: bool):
    if por_dia:
        colunas = ctx['resumo_dias_colunas']
        formas = ctx.get('pagamento_matriz_dia_formas') or []
        aguardando = ctx.get('pagamento_matriz_dia_aguardando') or []
        totais = ctx.get('pagamento_matriz_dia_totais') or []
        titulo = 'Formas de pagamento — por dia'
        subtitulo = ctx.get('resumo_matriz_mes_titulo', '')
    else:
        colunas = ctx['resumo_meses_colunas']
        formas = ctx.get('pagamento_matriz_formas') or []
        aguardando = ctx.get('pagamento_matriz_aguardando') or []
        totais = ctx.get('pagamento_matriz_totais_mes') or []
        titulo = 'Formas de pagamento — por mês'
        subtitulo = f"Ano {ctx.get('resumo_matriz_ano', '')}"

    row = _escrever_titulo_aba(ws, titulo, f'{subtitulo} · qt · R$')
    row = _cabecalho_matriz(ws, row, 'Forma / convênio', colunas)
    for item in formas:
        row = _linha_matriz(
            ws,
            row,
            item.get('rotulo', ''),
            item.get('meses') or [],
            item.get('total_qt', ''),
            item.get('total_valor_fmt', ''),
        )
    if aguardando:
        ncol = len(colunas) * 2 + 3
        _celula(ws, row, 1, 'Aguardando faturamento', bold=True, fill=_FILL_SECAO)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncol)
        row += 1
        for item in aguardando:
            row = _linha_matriz(
                ws,
                row,
                '  ' + (item.get('rotulo') or ''),
                item.get('meses') or [],
                item.get('total_qt', ''),
                item.get('total_valor_fmt', ''),
            )
    _celula(ws, row, 1, 'Total geral', bold=True, fill=_FILL_TOTAL)
    c = 2
    for i, tot in enumerate(totais):
        fill = _FILL_ZEBRA_A if i % 2 == 0 else _FILL_ZEBRA_B
        qt = '—' if por_dia else tot.get('qt', '—')
        val = tot.get('valor_fmt', '')
        _celula(ws, row, c, qt, bold=True, center=True, fill=fill)
        _celula(ws, row, c + 1, val, bold=True, center=True, fill=fill)
        c += 2
    _celula(ws, row, c, '—', bold=True, center=True, fill=_FILL_TOTAL)
    _celula(ws, row, c + 1, ctx.get('total_resumo_geral_fmt', ''), bold=True, center=True, fill=_FILL_TOTAL)
    _largura_colunas_matriz(ws, len(colunas))
    ws.freeze_panes = 'B5'


def _aba_resumo_capa(wb: Workbook, ctx: dict):
    ws = wb.active
    ws.title = 'Resumo'
    _celula(ws, 1, 1, 'Resumo — Acerto de Caixa', bold=True)
    _celula(ws, 2, 1, f"Período: {ctx.get('periodo_fmt', '')}")
    _celula(ws, 3, 1, ctx.get('filtros_resumo', ''))
    _celula(ws, 4, 1, f"Linhas no filtro: {ctx.get('quantidade_linhas', 0)}")
    row = 6
    _celula(ws, row, 1, 'Formas de pagamento', bold=True)
    row += 1
    for r in ctx.get('resumo_pagamento') or []:
        _celula(ws, row, 1, r.get('rotulo', ''))
        _celula(ws, row, 2, f"R$ {r.get('total_fmt', '')}")
        row += 1
    if ctx.get('resumo_aguardando_faturamento'):
        _celula(ws, row, 1, 'Aguardando faturamento', bold=True)
        _celula(ws, row, 2, f"R$ {ctx.get('total_aguardando_faturamento_fmt', '')}")
        row += 1
        for r in ctx['resumo_aguardando_faturamento']:
            _celula(ws, row, 1, f"  {r.get('convenio', '')}")
            _celula(ws, row, 2, f"R$ {r.get('total_fmt', '')}")
            row += 1
    row += 1
    _celula(ws, row, 1, 'Total geral', bold=True)
    _celula(ws, row, 2, f"R$ {ctx.get('total_resumo_geral_fmt', '')}")
    row += 1
    _celula(ws, row, 1, 'Valor pago (grade)', bold=True)
    _celula(ws, row, 2, f"R$ {ctx.get('total_valor_pago_grade_fmt', '')}")
    ws.column_dimensions['A'].width = 42
    ws.column_dimensions['B'].width = 16


def _aba_solicitante(wb: Workbook, ctx: dict):
    ws = wb.create_sheet('Solicitante')
    row = _escrever_titulo_aba(ws, 'Médico solicitante — qt · valor pago', ctx.get('periodo_fmt', ''))
    _celula(ws, row, 1, 'Solicitante', bold=True, fill=_FILL_CAB)
    _celula(ws, row, 2, 'Qt', bold=True, fill=_FILL_CAB, center=True)
    _celula(ws, row, 3, 'Valor', bold=True, fill=_FILL_CAB, center=True)
    row += 1
    for r in ctx.get('resumo_solicitante') or []:
        _celula(ws, row, 1, r.get('solicitante', ''))
        _celula(ws, row, 2, r.get('quantidade', ''), center=True)
        _celula(ws, row, 3, f"R$ {r.get('valor_fmt', '')}", center=True)
        row += 1
    _celula(ws, row, 1, 'Total', bold=True, fill=_FILL_TOTAL)
    _celula(ws, row, 2, ctx.get('resumo_solicitante_total_qt', ''), bold=True, center=True, fill=_FILL_TOTAL)
    _celula(ws, row, 3, f"R$ {ctx.get('resumo_solicitante_total_valor_fmt', '')}", bold=True, center=True, fill=_FILL_TOTAL)
    ws.column_dimensions['A'].width = 48
    ws.column_dimensions['B'].width = 8
    ws.column_dimensions['C'].width = 14


def montar_workbook_resumo_acerto(ctx: dict, *, visao: str = 'mes') -> Workbook:
    from faturamento_medico.services.acerto_caixa import montar_resumo_viabilidade_matriz_mes

    wb = Workbook()
    _aba_resumo_capa(wb, ctx)

    visao = (visao or 'mes').strip().lower()
    por_dia = visao != 'ano' and bool(ctx.get('resumo_matriz_mes'))
    anual = visao == 'ano' and bool(ctx.get('resumo_matriz_anual'))

    if por_dia:
        ws_mod = wb.create_sheet('Modalidade')
        _aba_matriz_modalidade(ws_mod, ctx, True)
        ws_viab = wb.create_sheet('Viabilidade')
        _aba_matriz_viabilidade(ws_viab, ctx, True)
        ws_pag = wb.create_sheet('Pagamento')
        _aba_matriz_pagamento(ws_pag, ctx, True)
    elif anual:
        ano = ctx.get('resumo_matriz_ano')
        if ano and not ctx.get('viabilidade_matriz_linhas'):
            linhas = ctx.get('linhas') or []
            ctx.update(montar_resumo_viabilidade_matriz_mes(linhas, int(ano)))
        ws_mod = wb.create_sheet('Modalidade')
        _aba_matriz_modalidade(ws_mod, ctx, False)
        ws_viab = wb.create_sheet('Viabilidade')
        _aba_matriz_viabilidade(ws_viab, ctx, False)
        ws_pag = wb.create_sheet('Pagamento')
        _aba_matriz_pagamento(ws_pag, ctx, False)
    else:
        ws = wb.create_sheet('Modalidade (resumo)')
        row = 4
        _celula(ws, row, 1, 'Modalidade', bold=True, fill=_FILL_CAB)
        _celula(ws, row, 2, 'Qt', bold=True, fill=_FILL_CAB, center=True)
        _celula(ws, row, 3, 'Valor', bold=True, fill=_FILL_CAB, center=True)
        row += 1
        for item in ctx.get('resumo_modalidades') or []:
            _celula(ws, row, 1, item.get('label', ''))
            _celula(ws, row, 2, item.get('quantidade', ''), center=True)
            _celula(ws, row, 3, f"R$ {item.get('valor_fmt', '')}", center=True)
            row += 1
        ws_v = wb.create_sheet('Viabilidade (resumo)')
        _celula(ws_v, 4, 1, 'Viabilidade', bold=True, fill=_FILL_CAB)
        _celula(ws_v, 4, 2, 'Qt', bold=True, fill=_FILL_CAB, center=True)
        _celula(ws_v, 4, 3, 'Valor', bold=True, fill=_FILL_CAB, center=True)
        row = 5
        for r in ctx.get('resumo_viabilidade') or []:
            _celula(ws_v, row, 1, r.get('viabilidade', ''))
            _celula(ws_v, row, 2, r.get('quantidade', ''), center=True)
            _celula(ws_v, row, 3, f"R$ {r.get('valor_fmt', '')}", center=True)
            row += 1

    _aba_solicitante(wb, ctx)
    return wb