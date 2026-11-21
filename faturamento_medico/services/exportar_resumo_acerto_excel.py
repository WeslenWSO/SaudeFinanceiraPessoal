"""Exporta o resumo do acerto de caixa (mensal por dia / anual por mês) para Excel."""

from __future__ import annotations

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


_FILL_CAB = PatternFill('solid', fgColor='B8D4E8')
_FILL_BANNER = PatternFill('solid', fgColor='1F3864')
_FILL_ZEBRA_A = PatternFill('solid', fgColor='DBEAFE')
_FILL_ZEBRA_B = PatternFill('solid', fgColor='F8FAFC')
_FILL_TOTAL = PatternFill('solid', fgColor='EFF6FF')
_FILL_SECAO = PatternFill('solid', fgColor='F1F5F9')
_FILL_KPI = PatternFill('solid', fgColor='DBEAFE')
_FILL_MONEY = PatternFill('solid', fgColor='C6EFCE')
_FONT_BRANCO = Font(bold=True, size=11, color='FFFFFF')
_FONT_TITULO = Font(bold=True, size=13)
_THIN = Side(style='thin')
_BORDA = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_COL_DADOS_GRAFICO = 40


def _celula(ws, row: int, col: int, valor, *, bold=False, fill=None, center=False, border=False):
    c = ws.cell(row=row, column=col, value=valor)
    if bold:
        c.font = Font(bold=True, size=9)
    if fill:
        c.fill = fill
    if center:
        c.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    elif isinstance(valor, str) and len(str(valor)) > 20:
        c.alignment = Alignment(vertical='center', wrap_text=True)
    if border:
        c.border = _BORDA
    return c


def _filtrar_serie_grafico(labels: list, valores: list) -> tuple[list, list]:
    out_l: list = []
    out_v: list = []
    for lb, v in zip(labels or [], valores or []):
        try:
            vf = float(v or 0)
        except (TypeError, ValueError):
            vf = 0.0
        if vf > 0:
            out_l.append(str(lb or '—'))
            out_v.append(vf)
    return out_l, out_v


def _escrever_serie_grafico(ws, col_ini: int, start_row: int, labels: list, valores: list) -> tuple[int, int]:
    """Grava rótulo + valor em colunas auxiliares; retorna primeira/última linha de dados."""
    r = start_row
    for lb, val in zip(labels, valores):
        _celula(ws, r, col_ini, lb, border=True)
        c = _celula(ws, r, col_ini + 1, val, border=True, center=True)
        c.number_format = '#,##0.00'
        r += 1
    if r <= start_row:
        _celula(ws, start_row, col_ini, '—', border=True)
        _celula(ws, start_row, col_ini + 1, 0, border=True)
        return start_row, start_row
    return start_row, r - 1


def _adicionar_grafico_coluna(
    ws,
    anchor: str,
    titulo: str,
    col_cat: int,
    col_val: int,
    row_ini: int,
    row_fim: int,
    *,
    cor: str = '2563EB',
    largura: float = 16,
    altura: float = 9,
):
    if row_fim < row_ini:
        return
    chart = BarChart()
    chart.type = 'col'
    chart.grouping = 'clustered'
    chart.title = titulo
    chart.style = 10
    chart.height = altura
    chart.width = largura
    chart.legend = None
    data = Reference(ws, min_col=col_val, min_row=row_ini, max_row=row_fim)
    cats = Reference(ws, min_col=col_cat, min_row=row_ini, max_row=row_fim)
    chart.add_data(data, titles_from_data=False)
    chart.set_categories(cats)
    try:
        chart.series[0].graphicalProperties.solidFill = cor
    except Exception:
        pass
    chart.y_axis.majorGridlines = None
    ws.add_chart(chart, anchor)


def _largura_colunas_matriz(ws, n_colunas_dados: int):
    ws.column_dimensions['A'].width = 28
    for i in range(n_colunas_dados * 2 + 2):
        ws.column_dimensions[get_column_letter(2 + i)].width = 8 if i % 2 == 0 else 11
    ws.column_dimensions[get_column_letter(2 + n_colunas_dados * 2 + 2)].width = 12


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
        _celula(ws, start_row, c, label, bold=True, fill=_FILL_CAB, center=True, border=True)
        ws.merge_cells(start_row=start_row, start_column=c, end_row=start_row, end_column=c + 1)
        fill_sub = _FILL_ZEBRA_A if i % 2 == 0 else _FILL_ZEBRA_B
        _celula(ws, start_row + 1, c, 'Qt', bold=True, fill=fill_sub, center=True, border=True)
        _celula(ws, start_row + 1, c + 1, 'R$', bold=True, fill=fill_sub, center=True, border=True)
        c += 2
    _celula(ws, start_row, c, 'Total', bold=True, fill=_FILL_CAB, center=True)
    ws.merge_cells(start_row=start_row, start_column=c, end_row=start_row, end_column=c + 1)
    _celula(ws, start_row + 1, c, 'Qt', bold=True, fill=_FILL_TOTAL, center=True, border=True)
    _celula(ws, start_row + 1, c + 1, 'R$', bold=True, fill=_FILL_TOTAL, center=True, border=True)
    c_media = c + 2
    _celula(
        ws,
        start_row,
        c_media,
        'Média\nTotal/Qt',
        bold=True,
        fill=_FILL_CAB,
        center=True,
        border=True,
    )
    ws.merge_cells(
        start_row=start_row,
        start_column=c_media,
        end_row=start_row + 1,
        end_column=c_media,
    )
    return start_row + 2


def _linha_matriz(
    ws,
    row: int,
    rotulo: str,
    celulas: list[dict],
    total_qt,
    total_valor,
    media_valor_qt_fmt: str = '',
) -> int:
    _celula(ws, row, 1, rotulo, border=True)
    c = 2
    for i, cel in enumerate(celulas):
        fill = _FILL_ZEBRA_A if i % 2 == 0 else _FILL_ZEBRA_B
        _celula(ws, row, c, cel.get('qt', ''), center=True, fill=fill, border=True)
        _celula(ws, row, c + 1, cel.get('valor_fmt', ''), center=True, fill=fill, border=True)
        c += 2
    _celula(ws, row, c, total_qt, center=True, fill=_FILL_TOTAL, border=True)
    _celula(ws, row, c + 1, total_valor, center=True, fill=_FILL_TOTAL, border=True)
    _celula(
        ws,
        row,
        c + 2,
        media_valor_qt_fmt,
        center=True,
        fill=_FILL_TOTAL,
        border=True,
    )
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
            item.get('media_valor_qt_fmt', ''),
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
    _celula(
        ws,
        row,
        c + 2,
        ctx.get('resumo_media_valor_qt_fmt', ''),
        bold=True,
        center=True,
        fill=_FILL_TOTAL,
        border=True,
    )
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
            item.get('media_valor_qt_fmt', ''),
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
    _celula(
        ws,
        row,
        c + 2,
        ctx.get('resumo_viabilidade_media_valor_qt_fmt', ''),
        bold=True,
        center=True,
        fill=_FILL_TOTAL,
        border=True,
    )
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
            item.get('media_valor_qt_fmt', ''),
        )
    if aguardando:
        ncol = len(colunas) * 2 + 4
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
                item.get('media_valor_qt_fmt', ''),
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
    _celula(
        ws,
        row,
        c + 2,
        ctx.get('resumo_geral_media_valor_qt_fmt', ''),
        bold=True,
        center=True,
        fill=_FILL_TOTAL,
        border=True,
    )
    _largura_colunas_matriz(ws, len(colunas))
    ws.freeze_panes = 'B5'


def _aba_resumo_capa(wb: Workbook, ctx: dict):
    ws = wb.active
    ws.title = 'Resumo'
    ws.merge_cells('A1:D1')
    tit = _celula(ws, 1, 1, 'Resumo — Acerto de Caixa', bold=True, fill=_FILL_BANNER)
    tit.font = _FONT_BRANCO
    tit.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[1].height = 28

    sub = (
        f"{ctx.get('periodo_fmt', '')} · {ctx.get('filtros_resumo', '')} · "
        f"{ctx.get('quantidade_linhas', 0)} linha(s)"
    )
    ws.merge_cells('A2:D2')
    s2 = _celula(ws, 2, 1, sub, fill=_FILL_SECAO, border=True)
    s2.alignment = Alignment(wrap_text=True, vertical='center')
    ws.row_dimensions[2].height = 22

    row = 4
    _celula(ws, row, 1, 'Formas de pagamento', bold=True, fill=_FILL_CAB, border=True)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=2)
    row += 1
    for i, r in enumerate(ctx.get('resumo_pagamento') or []):
        fill = _FILL_ZEBRA_A if i % 2 == 0 else _FILL_ZEBRA_B
        _celula(ws, row, 1, r.get('rotulo', ''), fill=fill, border=True)
        v = _celula(ws, row, 2, f"R$ {r.get('total_fmt', '')}", fill=fill, border=True, center=True)
        v.alignment = Alignment(horizontal='right', vertical='center')
        row += 1
    if ctx.get('resumo_aguardando_faturamento'):
        _celula(ws, row, 1, 'Aguardando faturamento', bold=True, fill=_FILL_SECAO, border=True)
        t_ag = _celula(
            ws,
            row,
            2,
            f"R$ {ctx.get('total_aguardando_faturamento_fmt', '')}",
            bold=True,
            fill=_FILL_SECAO,
            border=True,
            center=True,
        )
        t_ag.alignment = Alignment(horizontal='right')
        row += 1
        for i, r in enumerate(ctx['resumo_aguardando_faturamento']):
            fill = _FILL_ZEBRA_B if i % 2 == 0 else _FILL_ZEBRA_A
            _celula(ws, row, 1, f"  {r.get('convenio', '')}", fill=fill, border=True)
            va = _celula(ws, row, 2, f"R$ {r.get('total_fmt', '')}", fill=fill, border=True, center=True)
            va.alignment = Alignment(horizontal='right')
            row += 1

    row += 1
    _celula(ws, row, 1, 'Total geral', bold=True, fill=_FILL_KPI, border=True)
    tg = _celula(
        ws,
        row,
        2,
        f"R$ {ctx.get('total_resumo_geral_fmt', '')}",
        bold=True,
        fill=_FILL_MONEY,
        border=True,
        center=True,
    )
    tg.alignment = Alignment(horizontal='right')
    row += 1
    _celula(ws, row, 1, 'Valor pago (grade)', bold=True, fill=_FILL_KPI, border=True)
    vp = _celula(
        ws,
        row,
        2,
        f"R$ {ctx.get('total_valor_pago_grade_fmt', '')}",
        bold=True,
        fill=_FILL_MONEY,
        border=True,
        center=True,
    )
    vp.alignment = Alignment(horizontal='right')

    ws.column_dimensions['A'].width = 38
    ws.column_dimensions['B'].width = 18
    for col_idx in range(_COL_DADOS_GRAFICO, _COL_DADOS_GRAFICO + 8):
        ws.column_dimensions[get_column_letter(col_idx)].hidden = True

    usar_meses = bool(ctx.get('grafico_torre_usar_meses'))
    col = _COL_DADOS_GRAFICO
    row_g = 4
    if usar_meses:
        lbs, vals = _filtrar_serie_grafico(
            ctx.get('grafico_torre_meses_labels') or [],
            ctx.get('grafico_torre_meses_modalidade_valores') or [],
        )
        ini, fim = _escrever_serie_grafico(ws, col, row_g, lbs, vals)
        _adicionar_grafico_coluna(
            ws, 'E4', 'Total por mês (grade)', col, col + 1, ini, fim, cor='2563EB'
        )
        lbs2, vals2 = _filtrar_serie_grafico(
            ctx.get('grafico_torre_meses_labels') or [],
            ctx.get('grafico_torre_meses_pagamento_valores') or [],
        )
        ini2, fim2 = _escrever_serie_grafico(ws, col + 3, row_g, lbs2, vals2)
        _adicionar_grafico_coluna(
            ws,
            'N4',
            'Total por mês (pagamento)',
            col + 3,
            col + 4,
            ini2,
            fim2,
            cor='0D9488',
        )
    else:
        conv_l, conv_v = _filtrar_serie_grafico(
            ctx.get('grafico_convenio_labels') or [],
            ctx.get('grafico_convenio_valores') or [],
        )
        ini, fim = _escrever_serie_grafico(ws, col, row_g, conv_l, conv_v)
        _adicionar_grafico_coluna(
            ws, 'E4', 'Convênio (torre)', col, col + 1, ini, fim, cor='0D9488', largura=14
        )

        mod_l, mod_v = _filtrar_serie_grafico(
            ctx.get('grafico_torre_modalidade_labels') or [],
            ctx.get('grafico_torre_modalidade_valores') or [],
        )
        ini2, fim2 = _escrever_serie_grafico(ws, col + 3, row_g, mod_l, mod_v)
        _adicionar_grafico_coluna(
            ws, 'M4', 'Modalidade (torre)', col + 3, col + 4, ini2, fim2, cor='2563EB', largura=14
        )

        pag_l, pag_v = _filtrar_serie_grafico(
            ctx.get('grafico_pagamento_labels') or [],
            ctx.get('grafico_pagamento_valores') or [],
        )
        ini3, fim3 = _escrever_serie_grafico(ws, col + 6, row_g, pag_l, pag_v)
        _adicionar_grafico_coluna(
            ws,
            'U4',
            'Forma de pagamento',
            col + 6,
            col + 7,
            ini3,
            fim3,
            cor='7C3AED',
            largura=14,
        )

    ws.print_area = 'A1:Y35'
    ws.sheet_view.showGridLines = False


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