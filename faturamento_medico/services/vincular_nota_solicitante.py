"""Vincula exames do solicitante a NFSe (NotaFiscalServico) por nome do paciente."""

from __future__ import annotations

import json
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


def _valor_fmt_nota(nota: NotaFiscalServico) -> str:
    valor = nota.valor_liquido if nota.valor_liquido is not None else nota.valor_bruto
    if valor is None:
        return '-'
    return f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def serializar_nota_linha(nota: NotaFiscalServico, manual: bool = False) -> dict:
    forma = _forma_pagamento_nota(nota)
    numero = (nota.numero_nota or '').strip() or f'#{nota.pk}'
    return {
        'pk': nota.pk,
        'numero': numero,
        'url': reverse('notasfiscais:detail', args=[nota.pk]),
        'forma_pagamento': forma or '-',
        'cliente': (nota.cliente or '').strip() or '-',
        'valor_fmt': _valor_fmt_nota(nota),
        'data_emissao_fmt': nota.data_emissao.strftime('%d/%m/%Y') if nota.data_emissao else '-',
        'manual': manual,
    }


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
    matches.sort(key=lambda n: (abs((n.data_emissao - data_exame).days), n.numero_nota or ''))
    return matches


def buscar_nota_manual_salva(
    empresa_id: int | None,
    numero_nota: str | None,
) -> NotaFiscalServico | None:
    """Recupera NFSe previamente vinculada pelo número salvo no faturamento."""
    numero = (numero_nota or '').strip()
    if not numero or not empresa_id:
        return None
    return (
        NotaFiscalServico.objects.filter(
            empresa_id=empresa_id,
            numero_nota=numero,
            data_cancelamento__isnull=True,
        )
        .select_related('forma_pagamento')
        .first()
    )


def resolver_notas_linha(
    notas_por_data: dict[date, list[NotaFiscalServico]],
    empresa_id: int | None,
    nome_paciente: str,
    data_exame: date | None,
    numero_nota_salvo: str | None = None,
) -> list[dict]:
    """Busca automática + fallback do vínculo manual salvo no faturamento."""
    notas = buscar_notas_paciente(notas_por_data, nome_paciente, data_exame)
    if notas:
        return [serializar_nota_linha(n, manual=False) for n in notas]
    nota_manual = buscar_nota_manual_salva(empresa_id, numero_nota_salvo)
    if nota_manual:
        return [serializar_nota_linha(nota_manual, manual=True)]
    return []


def _score_nota_vinculo(
    nota: NotaFiscalServico,
    nome_paciente: str,
    termo: str,
) -> float:
    """Pontua candidata: termo de busca (cliente/discriminação/NF) ou nome do paciente."""
    termo = (termo or '').strip()
    numero = (nota.numero_nota or '').strip()
    cliente = (nota.cliente or '').strip()
    discriminacao = (nota.discriminacao or '').strip()

    if termo:
        termo_upper = termo.upper()
        if termo in numero:
            return 1.0
        if termo_upper in cliente.upper():
            return 0.95
        if termo_upper in discriminacao.upper():
            return 0.92
        sim_cliente = _similaridade(termo, cliente)
        if sim_cliente >= 0.75:
            return max(0.85, sim_cliente)
        sim_disc = _similaridade(termo, discriminacao)
        if sim_disc >= 0.75:
            return max(0.85, sim_disc)
        return 0.0

    if nome_paciente and nome_paciente != '-':
        sim_cliente = _similaridade(nome_paciente, cliente)
        if sim_cliente >= SIMILARIDADE_MIN_PACIENTE:
            return sim_cliente
        sim_disc = _similaridade(nome_paciente, discriminacao)
        if sim_disc >= SIMILARIDADE_MIN_PACIENTE:
            return sim_disc
    return 0.0


def buscar_notas_para_vinculo(
    empresa_id: int | None,
    nome_paciente: str,
    data_exame: date | None,
    termo: str = '',
    limite: int = 20,
) -> list[dict]:
    """Lista NFSe candidatas à vinculação manual (busca por nome, discriminação ou número)."""
    if not empresa_id:
        return []
    from django.db.models import Q

    qs = NotaFiscalServico.objects.filter(
        empresa_id=empresa_id,
        data_cancelamento__isnull=True,
    ).select_related('forma_pagamento')
    if data_exame:
        qs = qs.filter(
            data_emissao__gte=data_exame,
            data_emissao__lte=data_exame + timedelta(days=JANELA_DIAS_APOS_EXAME),
        )
    termo = (termo or '').strip()
    if termo:
        qs = qs.filter(
            Q(numero_nota__icontains=termo)
            | Q(cliente__icontains=termo)
            | Q(discriminacao__icontains=termo)
        )
    candidatas: list[tuple[float, NotaFiscalServico]] = []
    limite_scan = 500 if not termo else max(limite * 5, 100)
    for nota in qs.order_by('-data_emissao')[:limite_scan]:
        score = _score_nota_vinculo(nota, nome_paciente, termo)
        if score > 0:
            candidatas.append((score, nota))
    candidatas.sort(key=lambda x: (-x[0], -(x[1].data_emissao.toordinal() if x[1].data_emissao else 0)))
    return [serializar_nota_linha(n, manual=False) for _, n in candidatas[:limite]]


def notas_linha_para_json(notas: list[dict]) -> str:
    return json.dumps(notas, ensure_ascii=False)
