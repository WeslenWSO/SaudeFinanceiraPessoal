"""Dados iniciais de faturamento por convênio."""
from __future__ import annotations

from datetime import date


def quinto_dia_util(ano: int, mes: int) -> date:
    """Retorna o 5º dia útil do mês (seg–sex)."""
    count = 0
    d = date(ano, mes, 1)
    while True:
        if d.weekday() < 5:
            count += 1
            if count == 5:
                return d
        d = date.fromordinal(d.toordinal() + 1)


def _add_meses(mes: int, ano: int, delta: int) -> tuple[int, int]:
    total = (ano * 12 + mes - 1) + delta
    return (total % 12) + 1, total // 12


CONVENIOS_MEDICINARTE = (
    'Postal Saúde',
    'Bombeiro',
    'Polícia Militar',
    'Fusex',
    'Profarma',
    'PPSaude',
    'Bradesco',
    'Geap',
    'Cassi',
)

CONVENIOS_ANESTESIA = (
    'Geap',
    'Bradesco',
    'Postal Saúde',
    'PM',
    'Bombeiro',
    'Life',
)

# (nome fantasia da empresa, convênios)
AGENDAS_POR_EMPRESA: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('Medicinarte', CONVENIOS_MEDICINARTE),
    ('SECURITY HEALTH ANESTESIA', CONVENIOS_ANESTESIA),
)

# Retrocompatível com migrations antigas
CONVENIOS_FATURAMENTO = CONVENIOS_MEDICINARTE
NOME_FANTASIA_AGENDA_FATURAMENTO = 'Medicinarte'


def empresa_por_nome_fantasia(Empresa, nome_fantasia: str):
    return Empresa.objects.filter(nome_fantasia__iexact=nome_fantasia).first()


def empresa_agenda_faturamento(Empresa):
    """Empresa Medicinarte (retrocompatível)."""
    return empresa_por_nome_fantasia(Empresa, NOME_FANTASIA_AGENDA_FATURAMENTO)


def todos_titulos_faturamento() -> frozenset[str]:
    titulos: set[str] = set()
    for _, convenios in AGENDAS_POR_EMPRESA:
        titulos.update(convenios)
    titulos.update(('Polícia Militar', 'Verificar glosa'))
    return frozenset(titulos)


def queryset_tarefas_seed_agenda(TarefaAgendada):
    """Tarefas geradas automaticamente pelo seed de faturamento/glosa."""
    from django.db.models import Q

    return TarefaAgendada.objects.filter(
        Q(titulo__in=todos_titulos_faturamento())
        | Q(titulo__endswith='— Recurso de Glosa')
    )


def _regra_convenio(
    titulo: str,
    prefixo: str,
    inicio_ano: int,
    inicio_mes: int,
    quinto: date,
    data_inicio: date,
) -> tuple[str, date]:
    if titulo == 'Postal Saúde':
        return f'{prefixo} Quinto dia útil.', quinto
    if titulo == 'Bombeiro':
        return f'{prefixo} Até dia 15 sempre com Nota Fiscal.', date(inicio_ano, inicio_mes, 15)
    if titulo in ('PM', 'Polícia Militar'):
        return f'{prefixo} Até dia 10 — 07h às 13hrs.', date(inicio_ano, inicio_mes, 10)
    if titulo == 'Fusex':
        return f'{prefixo} Quinto dia útil — 07h às 13hrs.', quinto
    if titulo == 'Profarma':
        return f'{prefixo} Início do mês nota disponível.', data_inicio
    if titulo == 'PPSaude':
        return f'{prefixo} Quinto dia útil.', quinto
    if titulo == 'Bradesco':
        return f'{prefixo} Até dia 15.', date(inicio_ano, inicio_mes, 15)
    if titulo == 'Geap':
        return f'{prefixo} Quinto dia útil.', quinto
    if titulo == 'Cassi':
        return f'{prefixo} Até dia 20.', date(inicio_ano, inicio_mes, 20)
    if titulo == 'Life':
        return f'{prefixo} Quinto dia útil.', quinto
    return f'{prefixo} Consultar prazo no convênio.', quinto


def tarefa_recurso_glosa_convenio(
    convenio: str,
    *,
    competencia_mes: int,
    competencia_ano: int,
    execucao_mes: int,
    execucao_ano: int,
) -> dict:
    """Recurso de glosa por convênio: prazo 01–10; follow-up do lote após 7 dias."""
    return {
        'titulo': f'{convenio} — Recurso de Glosa',
        'descricao': (
            f'Competência {competencia_mes:02d}/{competencia_ano}. '
            'Prazo recurso de glosa: do dia 01 ao 10 de cada mês. '
            'Enviar lote. Após 7 dias, solicitar por e-mail a situação do lote.'
        ),
        'data': date(execucao_ano, execucao_mes, 1),
        'previsao_conclusao': date(execucao_ano, execucao_mes, 10),
        'competencia_mes': competencia_mes,
        'competencia_ano': competencia_ano,
    }


def tarefas_recurso_glosa_mensal(
    *,
    execucao_mes: int,
    execucao_ano: int,
    qtd_meses: int = 12,
    convenios: tuple[str, ...] = CONVENIOS_MEDICINARTE,
) -> list[dict]:
    """Uma tarefa de glosa por convênio, a cada mês (competência = mês anterior)."""
    itens: list[dict] = []
    mes, ano = execucao_mes, execucao_ano
    for _ in range(qtd_meses):
        comp_mes, comp_ano = _add_meses(mes, ano, -1)
        for convenio in convenios:
            itens.append(tarefa_recurso_glosa_convenio(
                convenio,
                competencia_mes=comp_mes,
                competencia_ano=comp_ano,
                execucao_mes=mes,
                execucao_ano=ano,
            ))
        mes, ano = _add_meses(mes, ano, 1)
    return itens


def tarefa_verificar_glosa(
    *,
    competencia_mes: int,
    competencia_ano: int,
    execucao_mes: int,
    execucao_ano: int,
) -> dict:
    """Verificação de glosa: sempre do dia 01 ao 10 do mês de execução."""
    return {
        'titulo': 'Verificar glosa',
        'descricao': (
            f'Competência {competencia_mes:02d}/{competencia_ano}. '
            'Período de verificação de glosa: do dia 01 ao dia 10 de cada mês.'
        ),
        'data': date(execucao_ano, execucao_mes, 1),
        'previsao_conclusao': date(execucao_ano, execucao_mes, 10),
        'competencia_mes': competencia_mes,
        'competencia_ano': competencia_ano,
    }


def tarefas_verificar_glosa_mensal(
    *,
    execucao_mes: int,
    execucao_ano: int,
    qtd_meses: int = 12,
) -> list[dict]:
    """
    Gera tarefas mensais de glosa.
    Execução no mês M (dias 01–10); competência = mês anterior (faturamento).
    """
    itens: list[dict] = []
    mes, ano = execucao_mes, execucao_ano
    for _ in range(qtd_meses):
        comp_mes, comp_ano = _add_meses(mes, ano, -1)
        itens.append(tarefa_verificar_glosa(
            competencia_mes=comp_mes,
            competencia_ano=comp_ano,
            execucao_mes=mes,
            execucao_ano=ano,
        ))
        mes, ano = _add_meses(mes, ano, 1)
    return itens


def tarefas_faturamento_competencia(
    *,
    competencia_mes: int = 7,
    competencia_ano: int = 2026,
    inicio_mes: int = 8,
    inicio_ano: int = 2026,
    convenios: tuple[str, ...] = CONVENIOS_MEDICINARTE,
) -> list[dict]:
    """
    Competência MM/AAAA — tarefas iniciando em 01 do mês de execução.
    Convênio no título; regra de prazo na descrição + recurso de glosa.
    """
    data_inicio = date(inicio_ano, inicio_mes, 1)
    quinto = quinto_dia_util(inicio_ano, inicio_mes)
    prefixo = f'Faturamento competência {competencia_mes:02d}/{competencia_ano}.'

    itens: list[dict] = []
    for titulo in convenios:
        descricao, previsao = _regra_convenio(
            titulo, prefixo, inicio_ano, inicio_mes, quinto, data_inicio,
        )
        itens.append({
            'titulo': titulo,
            'descricao': descricao,
            'previsao_conclusao': previsao,
        })

    for titulo in convenios:
        glosa = tarefa_recurso_glosa_convenio(
            titulo,
            competencia_mes=competencia_mes,
            competencia_ano=competencia_ano,
            execucao_mes=inicio_mes,
            execucao_ano=inicio_ano,
        )
        itens.append({
            'titulo': glosa['titulo'],
            'descricao': glosa['descricao'],
            'previsao_conclusao': glosa['previsao_conclusao'],
            'data': glosa['data'],
        })
    return itens


def criar_tarefas_empresa(
    TarefaAgendada,
    empresa,
    *,
    convenios: tuple[str, ...],
    competencia_mes: int = 7,
    competencia_ano: int = 2026,
    inicio_mes: int = 8,
    inicio_ano: int = 2026,
    glosa_meses: int = 12,
) -> None:
    """Cria faturamento da competência + glosa mensal para uma empresa."""
    data_inicio = date(inicio_ano, inicio_mes, 1)

    for item in tarefas_faturamento_competencia(
        competencia_mes=competencia_mes,
        competencia_ano=competencia_ano,
        inicio_mes=inicio_mes,
        inicio_ano=inicio_ano,
        convenios=convenios,
    ):
        TarefaAgendada.objects.get_or_create(
            empresa=empresa,
            competencia_mes=competencia_mes,
            competencia_ano=competencia_ano,
            titulo=item['titulo'],
            defaults={
                'data': item.get('data', data_inicio),
                'previsao_conclusao': item['previsao_conclusao'],
                'descricao': item['descricao'],
                'status': 'pendente',
                'responsavel': '',
            },
        )

    for item in tarefas_recurso_glosa_mensal(
        execucao_mes=inicio_mes,
        execucao_ano=inicio_ano,
        qtd_meses=glosa_meses,
        convenios=convenios,
    ):
        TarefaAgendada.objects.get_or_create(
            empresa=empresa,
            competencia_mes=item['competencia_mes'],
            competencia_ano=item['competencia_ano'],
            titulo=item['titulo'],
            defaults={
                'data': item['data'],
                'previsao_conclusao': item['previsao_conclusao'],
                'descricao': item['descricao'],
                'status': 'pendente',
                'responsavel': '',
            },
        )
