"""Rotina diária de faturamento médico — Medicinarte (seg–sex)."""
from __future__ import annotations

from datetime import date, time, timedelta

from agendador_tarefas.seed_faturamento import empresa_por_nome_fantasia

NOME_FANTASIA = 'Medicinarte'

ROTINA_FATURAMENTO_MEDICO = (
    {
        'titulo': 'Iniciar o Faturamento médico',
        'descricao': 'Agendamento Medcloud. Segunda a Sexta, 11:01 às 11:15.',
        'hora_inicio': time(11, 1),
        'hora_fim': time(11, 15),
    },
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
        'titulo': 'Faturamento Médico Fusex',
        'descricao': 'Segunda a Sexta, 13:45 às 14:10.',
        'hora_inicio': time(13, 45),
        'hora_fim': time(14, 10),
    },
    {
        'titulo': 'Faturamento Médico Funcional',
        'descricao': 'Segunda a Sexta, 14:11 às 14:15.',
        'hora_inicio': time(14, 11),
        'hora_fim': time(14, 15),
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
    {
        'titulo': 'Faturamento Médico Sesi',
        'descricao': 'Segunda a Sexta, 17:46 às 17:55.',
        'hora_inicio': time(17, 46),
        'hora_fim': time(17, 55),
    },
)


def gerar_tarefas_faturamento_medico_medicinarte(
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


def criar_rotina_faturamento_medico_medicinarte(
    TarefaAgendada,
    Empresa,
    *,
    inicio: date,
    fim: date,
) -> int:
    empresa = empresa_por_nome_fantasia(Empresa, NOME_FANTASIA)
    if not empresa:
        return 0

    criadas = 0
    for item in gerar_tarefas_faturamento_medico_medicinarte(inicio=inicio, fim=fim):
        _, created = TarefaAgendada.objects.get_or_create(
            empresa=empresa,
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
