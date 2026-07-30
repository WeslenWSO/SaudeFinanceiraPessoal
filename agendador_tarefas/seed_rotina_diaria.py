"""Rotina diária geral (sem empresa) — segunda a sexta."""
from __future__ import annotations

from datetime import date, time, timedelta


ROTINAS_DIARIAS = (
    {
        'titulo': 'Olhar emails',
        'descricao': 'Segunda a Sexta, 07:30 às 07:45.',
        'hora_inicio': time(7, 30),
        'hora_fim': time(7, 45),
    },
    {
        'titulo': 'Baixar Extrato',
        'descricao': 'Segunda a Sexta, 07:46 às 09:00.',
        'hora_inicio': time(7, 46),
        'hora_fim': time(9, 0),
        'descricao_por_weekday': {
            0: (
                'Segunda a Sexta, 07:46 às 09:00. '
                'Observação (segunda): puxar somente da data de sexta.'
            ),
            1: (
                'Segunda a Sexta, 07:46 às 09:00. '
                'Observação (terça): puxar extrato de sábado a segunda.'
            ),
        },
    },
    {
        'titulo': 'Importar Extratos',
        'descricao': 'Segunda a Sexta, 08:45 às 09:00.',
        'hora_inicio': time(8, 45),
        'hora_fim': time(9, 0),
    },
    {
        'titulo': 'Conciliação',
        'descricao': 'Segunda a Sexta, 09:01 às 11:00.',
        'hora_inicio': time(9, 1),
        'hora_fim': time(11, 0),
    },
)


def _descricao_rotina(rotina: dict, dia: date) -> str:
    extras = rotina.get('descricao_por_weekday') or {}
    return extras.get(dia.weekday(), rotina['descricao'])


def gerar_tarefas_rotina_diaria(
    *,
    inicio: date,
    fim: date,
) -> list[dict]:
    """Gera tarefas de seg–sex entre inicio e fim (exceto domingo; sábado incluído se cair no intervalo)."""
    itens: list[dict] = []
    dia = inicio
    while dia <= fim:
        if dia.weekday() < 5:  # seg–sex
            for rotina in ROTINAS_DIARIAS:
                itens.append({
                    'titulo': rotina['titulo'],
                    'descricao': _descricao_rotina(rotina, dia),
                    'data': dia,
                    'previsao_conclusao': dia,
                    'competencia_mes': dia.month,
                    'competencia_ano': dia.year,
                    'hora_inicio': rotina['hora_inicio'],
                    'hora_fim': rotina['hora_fim'],
                })
        dia += timedelta(days=1)
    return itens


def criar_rotina_diaria_geral(TarefaAgendada, *, inicio: date, fim: date) -> int:
    criadas = 0
    for item in gerar_tarefas_rotina_diaria(inicio=inicio, fim=fim):
        _, created = TarefaAgendada.objects.get_or_create(
            empresa=None,
            titulo=item['titulo'],
            data=item['data'],
            defaults={
                'previsao_conclusao': item['previsao_conclusao'],
                'competencia_mes': item['competencia_mes'],
                'competencia_ano': item['competencia_ano'],
                'descricao': item['descricao'],
                'hora_inicio': item['hora_inicio'],
                'hora_fim': item['hora_fim'],
                'status': 'pendente',
                'responsavel': '',
            },
        )
        if created:
            criadas += 1
    return criadas
