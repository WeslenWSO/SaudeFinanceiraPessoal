"""Regras de status de agendamento (RIS/MedCloud) para relatórios da aba Análises."""
from __future__ import annotations

ROTULO_PENDENCIA_PACS = 'Pendência confirmação PACS'
STATUS_AGENDAMENTO_CONFIRMADO_RIS = 'Confirmado'


def _norm(status: str | None) -> str:
    return (status or '').strip()


def _norm_lower(status: str | None) -> str:
    return (
        _norm(status)
        .lower()
        .replace('ê', 'e')
        .replace('é', 'e')
        .replace('ã', 'a')
        .replace('ç', 'c')
    )


def eh_aguardando_faturamento_agendamento(status: str | None) -> bool:
    s = _norm_lower(status)
    return 'aguard' in s and 'fatur' in s


def eh_concluido_agendamento(status: str | None) -> bool:
    s = _norm_lower(status)
    return 'conclu' in s


def eh_confirmado_pendencia_pacs(status: str | None) -> bool:
    """Confirmado no RIS — exige confirmação no PACS (não entra no faturamento)."""
    s = _norm_lower(status)
    if not s.startswith('confirmado'):
        return False
    return 'conclu' not in s


def agendamento_conta_faturamento_analises(faturamento) -> bool:
    st = _norm(getattr(faturamento, 'status_agendamento', None))
    return eh_aguardando_faturamento_agendamento(st) or eh_concluido_agendamento(st)


# Alias usado em ranking e convênio
agendamento_conta_faturamento_convenio = agendamento_conta_faturamento_analises


def contar_dias_trabalhados_analise_agendamento(qs) -> int:
    dias: set = set()
    for fat in qs.prefetch_related('itens_servico'):
        if not agendamento_conta_faturamento_analises(fat):
            continue
        if fat.data:
            dias.add(fat.data)
    return len(dias)


def kwargs_ranking_faturamento_analises(empresa_id: int) -> dict:
    """Filtro padrão das abas Análises (exceto validação — só na tela Conferência)."""
    del empresa_id  # reservado para extensões futuras
    return {
        'somente_status_analise': False,
        'somente_agendamento_faturamento_convenio': True,
    }


LEGENDA_FILTRO_ANALISES = (
    'Faturamento: status de agendamento (RIS) — Aguardando faturamento e Concluído. '
    'Confirmado: pendência PACS (tela Conferência).'
)


def agendamento_pendencia_pacs_convenio(faturamento) -> bool:
    return eh_confirmado_pendencia_pacs(getattr(faturamento, 'status_agendamento', None))


def rotulo_exibicao_agendamento_dashboard(status: str | None) -> str:
    st = _norm(status) or 'Não informado'
    if eh_confirmado_pendencia_pacs(st):
        return ROTULO_PENDENCIA_PACS
    return st


def css_badge_agendamento(status: str | None) -> str:
    st = _norm(status)
    if eh_confirmado_pendencia_pacs(st):
        return 'info'
    if eh_concluido_agendamento(st):
        return 'success'
    if eh_aguardando_faturamento_agendamento(st):
        return 'warning'
    sl = _norm_lower(st)
    if 'cancel' in sl or 'desist' in sl or 'delet' in sl:
        return 'danger'
    if 'andamento' in sl or 'pend' in sl:
        return 'secondary'
    return 'secondary'


def status_agendamento_para_filtro_listagem(status_exibicao: str, status_original: str | None) -> str:
    """Valor do GET status_agendamento na listagem RIS."""
    if (status_exibicao or '').strip() == ROTULO_PENDENCIA_PACS:
        return STATUS_AGENDAMENTO_CONFIRMADO_RIS
    return _norm(status_original) or _norm(status_exibicao)
