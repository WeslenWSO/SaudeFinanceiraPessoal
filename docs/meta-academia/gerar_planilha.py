"""Gera planilha Excel com cronograma e orçamento — Meta Academia (Blue 7K)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUTPUT = Path(__file__).resolve().parent / 'Meta_Academia_Cronograma_Orcamento.xlsx'

TAXA_HORA = 120
HORAS_DIA = 6

HEADER_FILL = PatternFill(start_color='BDD7EE', end_color='BDD7EE', fill_type='solid')
MARCO_FILL = PatternFill(start_color='FFF2CC', end_color='FFF2CC', fill_type='solid')
TOTAL_FILL = PatternFill(start_color='E2EFDA', end_color='E2EFDA', fill_type='solid')
SUBTOTAL_FILL = PatternFill(start_color='F2F2F2', end_color='F2F2F2', fill_type='solid')
THIN = Side(style='thin', color='8EAADB')
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

CRONOGRAMA = [
    (0, 'Menu Meta Academia', 2, 1, '2026-09-01', '2026-09-01', ''),
    (0, 'Seeds premiação Atendente', 3, 1, '2026-09-01', '2026-09-01', ''),
    (0, 'Doc fluxo mensal', 2, 1, '2026-09-01', '2026-09-02', ''),
    (0, 'Teste + deploy', 2, 1, '2026-09-02', '2026-09-02', ''),
    (1, 'Migration PeriodoAcademia', 3, 2, '2026-09-02', '2026-09-03', ''),
    (1, 'Migration ItemPeriodoAcademia', 3, 2, '2026-09-03', '2026-09-03', ''),
    (1, 'Serviço afericao.py', 12, 6, '2026-09-03', '2026-09-04', ''),
    (1, 'Mapeamento fórmulas', 8, 5, '2026-09-04', '2026-09-05', ''),
    (1, 'calculos.py', 6, 3, '2026-09-05', '2026-09-05', ''),
    (1, 'Views recalcular/fechar', 8, 4, '2026-09-05', '2026-09-06', ''),
    (1, 'Template dashboard', 12, 6, '2026-09-06', '2026-09-07', ''),
    (1, 'Bonificação atendente', 4, 2, '2026-09-07', '2026-09-07', ''),
    (1, 'Testes + deploy', 2, 2, '2026-09-08', '2026-09-08', 'MVP'),
    (2, 'RegistroCancelamento', 10, 6, '2026-09-09', '2026-09-10', ''),
    (2, 'LRD diária', 18, 11, '2026-09-10', '2026-09-12', ''),
    (2, 'AuditoriaSOP', 14, 8, '2026-09-12', '2026-09-15', ''),
    (2, 'RegistroReclamacao', 10, 6, '2026-09-15', '2026-09-16', ''),
    (2, 'Painel KPIs', 22, 13, '2026-09-16', '2026-09-19', ''),
    (2, 'Relatório retenção', 10, 6, '2026-09-19', '2026-09-22', ''),
    (2, 'Aferição inadimplentes', 8, 5, '2026-09-22', '2026-09-23', ''),
    (2, 'Testes + deploy', 8, 5, '2026-09-23', '2026-09-26', 'Recepção'),
    (3, 'Régua 90d padrinho', 24, 14, '2026-09-26', '2026-10-01', ''),
    (3, 'Retenção D90', 16, 10, '2026-10-01', '2026-10-03', ''),
    (3, 'Avaliações', 12, 7, '2026-10-03', '2026-10-06', ''),
    (3, 'Ocupação aulas', 10, 6, '2026-10-06', '2026-10-07', ''),
    (3, 'Comissão vendas', 16, 10, '2026-10-07', '2026-10-10', ''),
    (3, 'KPIs fechamento', 8, 5, '2026-10-10', '2026-10-13', ''),
    (3, 'Testes + deploy', 4, 3, '2026-10-13', '2026-10-24', 'Padrinho'),
    (4, 'PDF extrato', 12, 7, '2026-10-24', '2026-10-28', ''),
    (4, 'Multi-unidade', 20, 11, '2026-10-28', '2026-11-03', ''),
    (4, 'Certificação', 24, 14, '2026-11-03', '2026-11-10', ''),
    (4, 'NPS estruturado', 8, 5, '2026-11-10', '2026-11-12', ''),
    (4, 'Stub CRM/check-in', 16, 8, '2026-11-12', '2026-11-21', 'Completo'),
]

FASES_ORCAMENTO = [
    ('0', 'Menu + seeds + doc', 9, 4, 1.8),
    ('1', 'Aferição + fechamento mensal', 58, 32, 14.6),
    ('1b', 'Metas em lote (opcional)', 8, 4, 0),
    ('2', 'LRD, SOPs, painel gerencial', 100, 60, 25.6),
    ('3', 'Padrinho, vendas, coord. técnica', 90, 55, 22.5),
    ('4', 'PDF, multi-unidade, certificação', 80, 45, 18.4),
]

CENARIOS = [
    ('MVP (Fases 0+1)', 36, 4320.0, 16.4, 330.0, 99.0, 429.0, 4749.0, date(2026, 9, 8)),
    ('Até recepção (Fases 0+1+2)', 96, 11520.0, 40.9, 825.0, 247.5, 1072.5, 12592.5, date(2026, 9, 26)),
    ('Projeto completo (Fases 0–4)', 200, 24000.0, 81.8, 1650.0, 495.0, 2145.0, 26145.0, date(2026, 11, 21)),
]

MARCOS = [
    ('08/09/2026', 'MVP Fase 0+1', 36, 'Cadastro meta mensal + aferição automática + fechamento'),
    ('26/09/2026', 'Fase 2 — Recepção', 96, 'LRD, SOPs, painel KPIs, reunião retenção'),
    ('24/10/2026', 'Fase 3 — Padrinho', 151, 'Padrinho, vendas, coordenação técnica'),
    ('21/11/2026', 'Fase 4 — Completo', 200, 'PDF, multi-unidade, certificação'),
]

FASE_NOMES = {
    0: 'Fase 0 — Organização',
    1: 'Fase 1 — Aferição mensal',
    2: 'Fase 2 — Operação recepção',
    3: 'Fase 3 — Padrinho + vendas',
    4: 'Fase 4 — Escala e integrações',
}


def _fmt_data(iso: str) -> str:
    y, m, d = iso.split('-')
    return f'{d}/{m}/{y}'


def _estilo_cabecalho(ws, row, titulos):
    for col, titulo in enumerate(titulos, start=1):
        cell = ws.cell(row=row, column=col, value=titulo)
        cell.font = Font(bold=True)
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell.border = BORDER


def _larguras(ws, larguras: dict):
    for col, width in larguras.items():
        ws.column_dimensions[col].width = width


def _cabecalho_projeto(ws, titulo_aba: str):
    ws['A1'] = 'Meta Academia — Projeto Blue 7K'
    ws['A1'].font = Font(bold=True, size=14)
    ws['A2'] = 'Cliente: Bluefit Maceió | Sistema: Saúde Financeira Pessoal (Django)'
    ws['A3'] = f'Aba: {titulo_aba} | Início: 01/09/2026 | Ritmo: {HORAS_DIA} h/dia | Taxa: R$ {TAXA_HORA}/h'
    ws['A4'] = 'Desenvolvimento com IA (Cursor) — horas e prazos reduzidos ~40%'
    return 6


def criar_aba_cronograma(wb: Workbook):
    ws = wb.active
    ws.title = 'Cronograma'
    row = _cabecalho_projeto(ws, 'Cronograma')

    titulos = [
        'Fase', 'Tarefa', 'Horas sem IA', 'Horas com IA', 'Dias úteis (IA)',
        'Início', 'Fim (IA)', 'Marco',
    ]
    _estilo_cabecalho(ws, row, titulos)
    row += 1
    inicio_dados = row

    fase_atual = None
    subtotal_sem = subtotal_com = 0
    total_sem = total_com = 0

    for fase, tarefa, h_sem, h_com, ini, fim, marco in CRONOGRAMA:
        if fase_atual is not None and fase != fase_atual:
            ws.cell(row=row, column=1, value=f'Subtotal Fase {fase_atual}').font = Font(bold=True)
            ws.cell(row=row, column=3, value=subtotal_sem).font = Font(bold=True)
            ws.cell(row=row, column=4, value=subtotal_com).font = Font(bold=True)
            ws.cell(row=row, column=5, value=round(subtotal_com / HORAS_DIA, 1)).font = Font(bold=True)
            for col in range(1, len(titulos) + 1):
                ws.cell(row=row, column=col).fill = SUBTOTAL_FILL
                ws.cell(row=row, column=col).border = BORDER
            row += 1
            subtotal_sem = subtotal_com = 0

        fase_atual = fase
        subtotal_sem += h_sem
        subtotal_com += h_com
        total_sem += h_sem
        total_com += h_com

        valores = [
            fase, tarefa, h_sem, h_com, round(h_com / HORAS_DIA, 1),
            _fmt_data(ini), _fmt_data(fim), marco,
        ]
        fill = MARCO_FILL if marco else None
        for col, val in enumerate(valores, start=1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = BORDER
            if col in (3, 4, 5):
                cell.alignment = Alignment(horizontal='center')
            if fill:
                cell.fill = fill
                cell.font = Font(bold=True)
        row += 1

    if fase_atual is not None:
        ws.cell(row=row, column=1, value=f'Subtotal Fase {fase_atual}').font = Font(bold=True)
        ws.cell(row=row, column=3, value=subtotal_sem).font = Font(bold=True)
        ws.cell(row=row, column=4, value=subtotal_com).font = Font(bold=True)
        ws.cell(row=row, column=5, value=round(subtotal_com / HORAS_DIA, 1)).font = Font(bold=True)
        for col in range(1, len(titulos) + 1):
            ws.cell(row=row, column=col).fill = SUBTOTAL_FILL
            ws.cell(row=row, column=col).border = BORDER
        row += 1

    ws.cell(row=row, column=1, value='TOTAL GERAL').font = Font(bold=True, size=11)
    ws.cell(row=row, column=3, value=total_sem).font = Font(bold=True)
    ws.cell(row=row, column=4, value=total_com).font = Font(bold=True)
    ws.cell(row=row, column=5, value=round(total_com / HORAS_DIA, 1)).font = Font(bold=True)
    for col in range(1, len(titulos) + 1):
        ws.cell(row=row, column=col).fill = TOTAL_FILL
        ws.cell(row=row, column=col).border = BORDER

    ws.auto_filter.ref = f'A{inicio_dados - 1}:{get_column_letter(len(titulos))}{row}'
    ws.freeze_panes = f'A{inicio_dados}'
    _larguras(ws, {'A': 6, 'B': 38, 'C': 14, 'D': 14, 'E': 14, 'F': 12, 'G': 12, 'H': 14})


def criar_aba_orcamento(wb: Workbook):
    ws = wb.create_sheet('Orçamento')
    row = _cabecalho_projeto(ws, 'Orçamento')

    ws.cell(row=row, column=1, value='CENÁRIOS CONSOLIDADOS').font = Font(bold=True, size=12)
    row += 1

    titulos_cenario = [
        'Escopo', 'Horas (IA)', 'Mão de obra (R$)', 'Tokens (M)', 'Tokens base (R$)',
        'Cursor +30% (R$)', 'Custo IA total (R$)', 'Total projeto (R$)', 'Com buffer 10%',
        'Data entrega',
    ]
    _estilo_cabecalho(ws, row, titulos_cenario)
    row += 1

    for escopo, horas, mao, tok_m, tok_base, cursor30, ia_total, total, data_ent in CENARIOS:
        buffer = round(total * 1.10, 2)
        valores = [
            escopo, horas, mao, tok_m, tok_base, cursor30, ia_total, total, buffer,
            data_ent.strftime('%d/%m/%Y'),
        ]
        for col, val in enumerate(valores, start=1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = BORDER
            if col >= 3:
                cell.number_format = '#,##0.00'
                cell.alignment = Alignment(horizontal='right')
        row += 1

    row += 2
    ws.cell(row=row, column=1, value='DETALHAMENTO POR FASE').font = Font(bold=True, size=12)
    row += 1

    titulos_fase = [
        'Fase', 'Escopo', 'Horas sem IA', 'Horas com IA', 'Dias (IA)',
        'Mão de obra (R$)', 'Tokens est. (M)', 'Custo IA (R$)', 'Subtotal (R$)',
    ]
    _estilo_cabecalho(ws, row, titulos_fase)
    row += 1

    for fase, escopo, h_sem, h_com, tok_m in FASES_ORCAMENTO:
        mao = h_com * TAXA_HORA
        tok_base = tok_m * 3.67 / 1000 * 5.5
        ia = tok_base * 1.30
        subtotal = mao + ia
        valores = [
            fase, escopo, h_sem, h_com, round(h_com / HORAS_DIA, 1),
            mao, round(tok_m, 1), round(ia, 2), round(subtotal, 2),
        ]
        for col, val in enumerate(valores, start=1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = BORDER
            if col >= 3:
                cell.alignment = Alignment(horizontal='center' if col <= 5 else 'right')
            if col >= 6:
                cell.number_format = '#,##0.00'
        row += 1

    row += 2
    ws.cell(row=row, column=1, value='PREMISSAS').font = Font(bold=True, size=11)
    row += 1
    premissas = [
        f'Taxa de desenvolvimento: R$ {TAXA_HORA}/hora',
        'Custo IA: ~409k tokens/h com Cursor; US$ 3,67/1M tokens; câmbio R$ 5,50',
        'Reserva Cursor AI: +30% sobre custo de tokens',
        'Buffer recomendado: +10% sobre total (imprevistos)',
        'Fase 1b (metas em lote) é opcional — não incluída nos cenários MVP/recepção/completo',
        'Validade da proposta: 30 dias a partir da emissão',
    ]
    for texto in premissas:
        ws.cell(row=row, column=1, value=texto)
        row += 1

    row += 1
    ws.cell(row=row, column=1, value='MARCOS DE PAGAMENTO SUGERIDOS').font = Font(bold=True, size=11)
    row += 1
    pagamentos = [
        ('30%', 'Assinatura / kick-off', 'Início do projeto'),
        ('30%', 'Entrega MVP (08/09/2026)', 'Fases 0+1 em produção'),
        ('25%', 'Entrega recepção (26/09/2026)', 'Fase 2 — LRD, SOPs, painel'),
        ('15%', 'Entrega final (21/11/2026)', 'Fases 3+4 — projeto completo'),
    ]
    _estilo_cabecalho(ws, row, ['%', 'Marco', 'Descrição'])
    row += 1
    for pct, marco, desc in pagamentos:
        for col, val in enumerate((pct, marco, desc), start=1):
            ws.cell(row=row, column=col, value=val).border = BORDER
        row += 1

    _larguras(ws, {
        'A': 28, 'B': 22, 'C': 16, 'D': 14, 'E': 16, 'F': 16, 'G': 16, 'H': 18, 'I': 16, 'J': 14,
    })


def criar_aba_marcos(wb: Workbook):
    ws = wb.create_sheet('Marcos')
    row = _cabecalho_projeto(ws, 'Marcos de entrega')

    titulos = ['Data alvo', 'Marco', 'Horas acum.', 'O que a operação ganha', 'Critério de pronto']
    _estilo_cabecalho(ws, row, titulos)
    row += 1

    criterios = {
        'MVP Fase 0+1': 'Fechar mês calcula Conversão/Vendas/Churn; extrato premiação',
        'Fase 2 — Recepção': 'KPIs gerente visíveis; LRD registrável; cancelamentos categorizados',
        'Fase 3 — Padrinho': '% régua e retenção D90 no painel',
        'Fase 4 — Completo': 'PDF extrato; multi-unidade; certificação por setor',
    }

    for data_alvo, marco, horas, ganho in MARCOS:
        valores = [data_alvo, marco, horas, ganho, criterios.get(marco, '')]
        for col, val in enumerate(valores, start=1):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = BORDER
            if col == 3:
                cell.alignment = Alignment(horizontal='center')
        row += 1

    row += 2
    ws.cell(row=row, column=1, value='CRONOGRAMA POR FASE (visão resumida)').font = Font(bold=True, size=11)
    row += 1
    _estilo_cabecalho(ws, row, ['Fase', 'Nome', 'Horas (IA)', 'Período estimado'])
    row += 1
    periodos = {
        0: '01–02 set/2026',
        1: '02–08 set/2026',
        2: '09–26 set/2026',
        3: '26 set – 24 out/2026',
        4: '24 out – 21 nov/2026',
    }
    for fase_num in range(5):
        h_com = sum(r[3] for r in CRONOGRAMA if r[0] == fase_num)
        for col, val in enumerate(
            (fase_num, FASE_NOMES[fase_num], h_com, periodos[fase_num]), start=1
        ):
            cell = ws.cell(row=row, column=col, value=val)
            cell.border = BORDER
        row += 1

    _larguras(ws, {'A': 14, 'B': 28, 'C': 14, 'D': 52, 'E': 48})


def gerar_planilha(caminho: Path | None = None) -> Path:
    caminho = caminho or OUTPUT
    wb = Workbook()
    criar_aba_cronograma(wb)
    criar_aba_orcamento(wb)
    criar_aba_marcos(wb)
    wb.save(caminho)
    return caminho


if __name__ == '__main__':
    out = gerar_planilha()
    print(f'Planilha gerada: {out}')
