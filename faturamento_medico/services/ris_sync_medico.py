"""Sincroniza médico/solicitante de grupos RIS com faturamentos já existentes."""

from __future__ import annotations

from faturamento_medico.models import FaturamentoMedico

CAMPOS_RIS_SYNC = (
    'medico',
    'medico_solicitante',
    'status_agendamento',
    'convenio',
    'tecnico',
    'horario',
    'horario_inicio',
    'horario_fim',
    'local',
)


def _normalizar_servico(texto: str) -> str:
    return (texto or '').strip().lower()


def _score_match_faturamento(faturamento: FaturamentoMedico, dados: dict) -> int:
    servicos_ris = {_normalizar_servico(s['descricao']) for s in dados.get('servicos') or []}
    if not servicos_ris:
        return 0
    servicos_db = {
        _normalizar_servico(it.servico)
        for it in faturamento.itens_servico.all()
    }
    return len(servicos_ris & servicos_db)


def buscar_faturamento_ris_existente(empresa_id: int, dados: dict) -> FaturamentoMedico | None:
    """Localiza faturamento existente pelo paciente/data e overlap de procedimentos."""
    qs = FaturamentoMedico.objects.filter(
        empresa_id=empresa_id,
        nome__iexact=dados['nome'],
        data=dados['data'],
    )
    cpf = (dados.get('cpf') or '').strip()
    if cpf:
        qs = qs.filter(cpf=cpf)

    candidatos = list(qs.prefetch_related('itens_servico'))
    if not candidatos:
        return None

    melhor = max(candidatos, key=lambda fat: _score_match_faturamento(fat, dados))
    if _score_match_faturamento(melhor, dados) > 0:
        return melhor

    if len(candidatos) == 1:
        return candidatos[0]
    return None


def sincronizar_faturamento_ris(faturamento: FaturamentoMedico, dados: dict) -> list[str]:
    """Atualiza campos do faturamento a partir do grupo RIS. Retorna campos alterados."""
    alterados: list[str] = []
    for campo in CAMPOS_RIS_SYNC:
        novo = dados.get(campo)
        if campo == 'convenio' and not novo:
            novo = 'Particular'
        if not novo:
            continue
        atual = getattr(faturamento, campo, None)
        atual_str = (atual or '').strip() if isinstance(atual, str) else atual
        novo_str = (novo or '').strip() if isinstance(novo, str) else novo
        if atual_str != novo_str:
            setattr(faturamento, campo, novo)
            alterados.append(campo)
    if alterados:
        faturamento.save(update_fields=alterados + ['data_atualizacao'])
    return alterados
