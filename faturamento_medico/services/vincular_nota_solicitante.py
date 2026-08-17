"""Vincula exames do solicitante a NFSe por nome do paciente e janela de datas."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.urls import reverse

from faturamento_medico.services.atualizar_faturamento_convenio import _similaridade
from notasfiscais.models import NotaFiscalServico

JANELA_DIAS_APOS_EXAME = 15
SIMILARIDADE_MIN_PACIENTE = 0.82


def _forma_pagamento_nota(nota: NotaFiscalServico) -> str:
    if nota.forma_pagamento_id and nota.forma_pagamento:
        return (nota.forma_pagamento.descricao or '').strip()
    return (nota.extract_payment_method_from_description() or '').strip()


def carregar_notas_por_data(
    empresa_id: int | None,
    data_inicio: date,
    data_fim: date,
    janela_dias: int = JANELA_DIAS_APOS_EXAME,
) -> dict[date, list[NotaFiscalServico]]:
    """Carrega NFSe indexadas por data_emissao (período + janela após o fim)."""
    qs = NotaFiscalServico.objects.filter(
        data_emissao__gte=data_inicio,
        data_emissao__lte=data_fim + timedelta(days=janela_dias),
        data_cancelamento__isnull=True,
    ).select_related('forma_pagamento')
    if empresa_id:
        qs = qs.filter(empresa_id=empresa_id)
    por_data: dict[date, list[NotaFiscalServico]] = defaultdict(list)
    for nota in qs:
        if nota.data_emissao:
            por_data[nota.data_emissao].append(nota)
    return por_data


def buscar_notas_paciente(
    notas_por_data: dict[date, list[NotaFiscalServico]],
    nome_paciente: str,
    data_exame: date | None,
    janela_dias: int = JANELA_DIAS_APOS_EXAME,
) -> list[NotaFiscalServico]:
    """NFSe cujo tomador coincide com o paciente entre o exame e +janela_dias."""
    if not data_exame or not (nome_paciente or '').strip() or nome_paciente == '-':
        return []
    matches: list[NotaFiscalServico] = []
    for offset in range(janela_dias + 1):
        dia = data_exame + timedelta(days=offset)
        for nota in notas_por_data.get(dia, []):
            if _similaridade(nome_paciente, nota.cliente or '') >= SIMILARIDADE_MIN_PACIENTE:
                matches.append(nota)
    matches.sort(key=lambda n: (n.data_emissao, n.numero_nota or ''))
    return matches


def serializar_nota_linha(nota: NotaFiscalServico) -> dict:
    forma = _forma_pagamento_nota(nota)
    numero = (nota.numero_nota or '').strip() or f'#{nota.pk}'
    return {
        'pk': nota.pk,
        'numero': numero,
        'url': reverse('notasfiscais:detail', args=[nota.pk]),
        'forma_pagamento': forma or '-',
        'data_emissao_fmt': nota.data_emissao.strftime('%d/%m/%Y') if nota.data_emissao else '-',
    }
