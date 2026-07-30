"""Rotina diária de faturamento médico — Serviço de Anestesia (seg–sex)."""
from __future__ import annotations

from datetime import date, time, timedelta

from agendador_tarefas.seed_faturamento import empresa_por_nome_fantasia

NOME_FANTASIA = 'SECURITY HEALTH ANESTESIA'

ROTINA_FATURAMENTO_MEDICO = (
    {
        'titulo': 'Faturamento Médico PM',
        'descricao': 'Segunda a Sexta, 11:16 às 11:50.',
        'hora_inicio': time(11, 16),
        'hora_fim': time(11, 50),
    },
    {
        'titulo': 'Faturamento Médico Bombeiro',
        'descricao': 'Segunda a Sexta, 11:50 às 12:00.',
        'hora_inicio': time(11, 50),
        'hora_fim': time(12, 0),
    },
    {
        'titulo': 'Faturamento Médico Geap',
        'descricao': 'Segunda a Sexta, 14:16 às 16:30.',
        'hora_inicio': time(14, 16),
        'hora_fim': time(16, 30),
    },
    {
        'titulo': 'Faturamento Médico Bradesco',
        'descricao': 'Segunda a Sexta, 16:31 às 17:00.',
        'hora_inicio': time(16, 31),
        'hora_fim': time(17, 0),
    },
    {
        'titulo': 'Faturamento Médico Cassi',
        'descricao': 'Segunda a Sexta, 17:01 às 17:20.',
        'hora_inicio': time(17, 1),
        'hora_fim': time(17, 20),
    },
    {
        'titulo': 'Faturamento Médico Postal Saúde',
        'descricao': 'Segunda a Sexta, 17:21 às 17:45.',
        'hora_inicio': time(17, 21),
        'hora_fim': time(17, 45),
    },
)

TITULO_FECHAMENTO_REPASSE = 'Fechamento do Repasse'


def _add_meses(mes: int, ano: int, delta: int) -> tuple[int, int]:
    total = (ano * 12 + mes - 1) + delta
    return (total % 12) + 1, total // 12


def gerar_tarefas_faturamento_medico_anestesia(
    *,
    inicio: date,
    fim: date,
) -> list[dict]:
    itens: list[dict] = []
    dia = inicio
    while dia <= fim:
        if dia.weekday() < 5:
            for rotina in ROTINA_FATURAMENTO_MEDICO:
                itens.append({
                    'titulo': rotina['titulo'],
                    'descricao': rotina['descricao'],
                    'data': dia,
                    'previsao_conclusao': dia,
                    'competencia_mes': dia.month,
                    'competencia_ano': dia.year,
                    'hora_inicio': rotina['hora_inicio'],
                    'hora_fim': rotina['hora_fim'],
                })
        dia += timedelta(days=1)
    return itens


def gerar_tarefas_fechamento_repasse(
    *,
    inicio_mes: int,
    inicio_ano: int,
    qtd_meses: int = 12,
) -> list[dict]:
    """Fechamento do repasse: do dia 15 ao 20 de cada mês."""
    import calendar

    itens: list[dict] = []
    mes, ano = inicio_mes, inicio_ano
    for _ in range(qtd_meses):
        ultimo_dia = calendar.monthrange(ano, mes)[1]
        itens.append({
            'titulo': TITULO_FECHAMENTO_REPASSE,
            'descricao': (
                f'Fechamento do repasse — do dia 15 ao 20 de cada mês. '
                f'Competência {mes:02d}/{ano}.'
            ),
            'data': date(ano, mes, 15),
            'previsao_conclusao': date(ano, mes, min(20, ultimo_dia)),
            'competencia_mes': mes,
            'competencia_ano': ano,
            'hora_inicio': None,
            'hora_fim': None,
        })
        mes, ano = _add_meses(mes, ano, 1)
    return itens


def _criar_itens(TarefaAgendada, empresa, itens: list[dict]) -> int:
    criadas = 0
    for item in itens:
        defaults = {
            'previsao_conclusao': item['previsao_conclusao'],
            'competencia_mes': item['competencia_mes'],
            'competencia_ano': item['competencia_ano'],
            'descricao': item['descricao'],
            'hora_inicio': item.get('hora_inicio'),
            'hora_fim': item.get('hora_fim'),
            'status': 'pendente',
            'responsavel': '',
        }
        _, created = TarefaAgendada.objects.get_or_create(
            empresa=empresa,
            titulo=item['titulo'],
            data=item['data'],
            defaults=defaults,
        )
        if created:
            criadas += 1
    return criadas


def criar_rotina_anestesia(
    TarefaAgendada,
    Empresa,
    *,
    inicio: date,
    fim: date,
    repasse_meses: int = 12,
) -> int:
    empresa = empresa_por_nome_fantasia(Empresa, NOME_FANTASIA)
    if not empresa:
        return 0

    itens = gerar_tarefas_faturamento_medico_anestesia(inicio=inicio, fim=fim)
    itens.extend(gerar_tarefas_fechamento_repasse(
        inicio_mes=inicio.month,
        inicio_ano=inicio.year,
        qtd_meses=repasse_meses,
    ))
    return _criar_itens(TarefaAgendada, empresa, itens)
