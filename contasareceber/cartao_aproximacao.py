"""
Conciliação de títulos (contas a receber) com recebíveis da maquininha por data e valor aproximados.
"""
from __future__ import annotations

import unicodedata
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import transaction

from contasareceber.models import ContaAReceber
from relatoriorecebiveis.models import RelatorioRecebiveisMaquinaCartao

DAY_WINDOW = 2
# Diferença aceita em R$ ou 2% do maior valor (o que for maior)
TOLERANCE_MIN = Decimal('0.50')
TOLERANCE_PCT = Decimal('0.02')


def _ascii_fold_upper(s: str) -> str:
    t = unicodedata.normalize('NFKD', s or '')
    u = ''.join(c for c in t if not unicodedata.combining(c))
    return u.upper().replace(' ', '')


def tipo_cartao_conta(conta: ContaAReceber) -> str | None:
    """
    A partir da cobrança do título (ex.: CARTAO CREDITO / CARTAO DEBITO).
    Retorna 'credito', 'debito' ou None se não for cartão tipado assim.
    """
    desc = _ascii_fold_upper(
        conta.forma_pagamento.descricao if conta.forma_pagamento else ''
    )
    if 'DEBIT' in desc or 'DEBITO' in desc:
        return 'debito'
    if 'CREDIT' in desc or 'CREDITO' in desc:
        return 'credito'
    return None


def rel_forma_bate_tipo(forma_rel: str, tipo: str | None) -> bool:
    """tipo: 'credito' | 'debito' | None — None não filtra."""
    if tipo is None:
        return True
    fp = (forma_rel or '').strip()
    if not fp:
        return False
    r = _ascii_fold_upper(fp)
    if tipo == 'debito':
        return 'DEBIT' in r or 'DEBITO' in r
    if tipo == 'credito':
        return 'CREDIT' in r or 'CREDITO' in r
    return True


def _ref_date(conta: ContaAReceber):
    return conta.data_vencimento or conta.data_emissao


def _valor_compativel(valor_titulo: Decimal, valor_rel: Decimal) -> bool:
    if valor_titulo is None or valor_rel is None:
        return False
    a, b = Decimal(valor_titulo), Decimal(valor_rel)
    diff = abs(a - b)
    ref = max(abs(a), abs(b), Decimal('0.01'))
    lim = max(TOLERANCE_MIN, (ref * TOLERANCE_PCT).quantize(Decimal('0.01')))
    return diff <= lim


def _serialize_conta(c: ContaAReceber) -> dict[str, Any]:
    tc = tipo_cartao_conta(c)
    return {
        'id': c.id,
        'cliente': c.cliente,
        'doc': c.doc or '',
        'valor_a_receber': str(c.valor_a_receber),
        'data_vencimento': c.data_vencimento.isoformat() if c.data_vencimento else None,
        'data_emissao': c.data_emissao.isoformat() if c.data_emissao else None,
        'autorizacao': c.autorizacao or '',
        'forma_pagamento': c.forma_pagamento.descricao if c.forma_pagamento else '',
        'tipo_cartao': tc or '',
    }


def _serialize_rel(r: RelatorioRecebiveisMaquinaCartao) -> dict[str, Any]:
    maq = r.get_maquinha_display() if r.maquinha else (r.maquinha or '')
    return {
        'id': r.id,
        'data_pagamento': r.data_pagamento.isoformat() if r.data_pagamento else None,
        'forma_pagamento': (r.forma_pagamento or '').strip(),
        'valor_liquido': str(r.valor_liquido),
        'valor_bruto': str(r.valor_bruto),
        'taxa_maquinha': str(r.taxa_maquinha),
        'maquinha': maq,
        'numero_autorizacao': r.numero_autorizacao or '',
        'bandeira': r.bandeira or '',
    }


def _eligible_relatorios_qs(empresa_id: int, d_min, d_max):
    return (
        RelatorioRecebiveisMaquinaCartao.objects.filter(
            empresa_id=empresa_id,
            conciliado=False,
            conta_a_receber__isnull=True,
            data_pagamento__isnull=False,
            data_pagamento__gte=d_min,
            data_pagamento__lte=d_max,
        )
        .order_by('data_pagamento', 'id')
    )


def build_suggestions(empresa_id: int, conta_ids: list[int]) -> dict[str, Any]:
    contas = list(
        ContaAReceber.objects.filter(
            id__in=conta_ids,
            empresa_id=empresa_id,
            status='pendente',
        ).select_related('forma_pagamento')
    )

    if not contas:
        return {
            'sugestoes': [],
            'titulos_sem_sugestao': [],
            'recebiveis_sem_sugestao': [],
            'pool_recebiveis': [],
            'erro': 'Nenhuma conta pendente encontrada para os IDs informados.',
        }

    ref_dates = []
    for c in contas:
        rd = _ref_date(c)
        if rd:
            ref_dates.append(rd)

    if not ref_dates:
        return {
            'sugestoes': [],
            'titulos_sem_sugestao': [_serialize_conta(c) for c in contas],
            'recebiveis_sem_sugestao': [],
            'pool_recebiveis': [],
            'erro': None,
        }

    d_min = min(ref_dates) - timedelta(days=DAY_WINDOW)
    d_max = max(ref_dates) + timedelta(days=DAY_WINDOW)
    rels = list(_eligible_relatorios_qs(empresa_id, d_min, d_max)[:800])

    used_rel: set[int] = set()
    sugestoes: list[dict[str, Any]] = []
    titulos_sem: list[dict[str, Any]] = []

    for conta in sorted(contas, key=lambda x: x.id):
        ref = _ref_date(conta)
        if not ref:
            titulos_sem.append(_serialize_conta(conta))
            continue

        j0, j1 = ref - timedelta(days=DAY_WINDOW), ref + timedelta(days=DAY_WINDOW)
        candidates: list[tuple[float, RelatorioRecebiveisMaquinaCartao]] = []
        vt = Decimal(conta.valor_a_receber or 0)

        tipo_titulo = tipo_cartao_conta(conta)

        for r in rels:
            if r.id in used_rel:
                continue
            if r.data_pagamento is None or not (j0 <= r.data_pagamento <= j1):
                continue
            if not rel_forma_bate_tipo(r.forma_pagamento, tipo_titulo):
                continue
            ok_liq = _valor_compativel(vt, r.valor_liquido)
            ok_bruto = _valor_compativel(vt, r.valor_bruto)
            if not ok_liq and not ok_bruto:
                continue
            days_diff = abs((r.data_pagamento - ref).days)
            vdiff = min(
                abs(vt - Decimal(r.valor_liquido or 0)),
                abs(vt - Decimal(r.valor_bruto or 0)),
            )
            score = float(vdiff) + 0.15 * days_diff
            candidates.append((score, r))

        if not candidates:
            titulos_sem.append(_serialize_conta(conta))
            continue

        candidates.sort(key=lambda x: x[0])
        best = candidates[0][1]
        used_rel.add(best.id)
        sugestoes.append(
            {
                'conta_id': conta.id,
                'relatorio_id': best.id,
                'conta': _serialize_conta(conta),
                'recebivel': _serialize_rel(best),
                'score': round(candidates[0][0], 4),
            }
        )

    receb_sem = [_serialize_rel(r) for r in rels if r.id not in used_rel]
    pool = [_serialize_rel(r) for r in rels]

    return {
        'sugestoes': sugestoes,
        'titulos_sem_sugestao': titulos_sem,
        'recebiveis_sem_sugestao': receb_sem,
        'pool_recebiveis': pool,
        'janela_dias': DAY_WINDOW,
        'erro': None,
    }


def _vincular_relatorio_na_conta(
    conta: ContaAReceber,
    relatorio: RelatorioRecebiveisMaquinaCartao,
) -> None:
    """Associa o lançamento do recebível ao título (sem alterar totais da conta ainda)."""
    doc = (conta.doc or '')[:50] if conta.doc else ''
    razao = (conta.cliente or '')[:200] if conta.cliente else ''
    relatorio.nota_fiscal = doc
    relatorio.razao = razao
    relatorio.conta_a_receber = conta
    relatorio.conciliado = False
    relatorio.save(
        update_fields=[
            'nota_fiscal',
            'razao',
            'conta_a_receber',
            'conciliado',
        ]
    )


def _autorizacao_de_recebiveis_para_conta(
    relatorios: list[RelatorioRecebiveisMaquinaCartao],
    max_len: int = 100,
) -> str | None:
    """
    Monta texto para ContaAReceber.autorizacao a partir dos recebíveis vinculados.
    Vários números distintos são unidos por vírgula; respeita max_len do modelo.
    """
    parts: list[str] = []
    for r in relatorios:
        a = (r.numero_autorizacao or '').strip()
        if a and a not in parts:
            parts.append(a)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0][:max_len]
    joined = ', '.join(parts)
    if len(joined) <= max_len:
        return joined
    return parts[0][:max_len]


def _atualizar_conta_totais_cartao(
    conta: ContaAReceber,
    relatorios: list[RelatorioRecebiveisMaquinaCartao],
) -> None:
    """
    Não altera valor_a_receber (valor de face do título).
    valor_recebido = soma dos líquidos da maquininha; tarifas = soma das taxas.
    Com vários recebíveis (parcelas), soma todos os vinculados.
    Status permanece «cartão» até o extrato bancário conciliar com os recebíveis.
    """
    # Preferir todos já vinculados à conta (+ os informados), sem duplicar
    by_id = {r.pk: r for r in RelatorioRecebiveisMaquinaCartao.objects.filter(conta_a_receber=conta)}
    for r in relatorios:
        by_id[r.pk] = r
    todos = list(by_id.values())
    if not todos:
        todos = list(relatorios)

    total_liq = sum(Decimal(r.valor_liquido or 0) for r in todos)
    total_taxa = sum(abs(Decimal(r.taxa_maquinha or 0)) for r in todos)
    datas = [r.data_pagamento for r in todos if r.data_pagamento]
    data_rec = max(datas) if datas else None
    conta.valor_recebido = total_liq
    conta.tarifas = total_taxa
    conta.data_recebimento = data_rec
    # Vinculação maquininha → cartão; «pago» só na conciliação extrato × recebível
    conta.status = 'cartao'
    update_fields: list[str] = [
        'valor_recebido',
        'tarifas',
        'status',
        'data_recebimento',
        'data_atualizacao',
    ]
    atual_auth = (conta.autorizacao or '').strip()
    if not atual_auth:
        nova = _autorizacao_de_recebiveis_para_conta(todos)
        if nova:
            conta.autorizacao = nova
            update_fields.append('autorizacao')
    conta.save(update_fields=update_fields)


def vincular_conta_a_recebivel(conta: ContaAReceber, relatorio: RelatorioRecebiveisMaquinaCartao) -> None:
    """Compatível com fluxo de um único recebível (soma = um lançamento)."""
    _vincular_relatorio_na_conta(conta, relatorio)
    _atualizar_conta_totais_cartao(conta, [relatorio])


def aplicar_grupos(empresa_id: int, grupos: list[dict[str, Any]]) -> tuple[int, list[str]]:
    """
    grupos: [{'conta_id': int, 'relatorio_ids': [int, ...]}, ...]
    Vários recebíveis por título (ex.: parcelas). Grava valor_recebido (soma dos líquidos) e tarifas;
    valor_a_receber do título não é alterado.
    Retorna (quantidade de recebíveis vinculados, erros).
    """
    erros: list[str] = []
    aplicados = 0
    rels_usados: set[int] = set()

    for g in grupos:
        try:
            cid = int(g['conta_id'])
            rids = [int(x) for x in (g.get('relatorio_ids') or [])]
        except (KeyError, TypeError, ValueError):
            erros.append('Grupo inválido ignorado.')
            continue

        if not rids:
            continue

        if len(rids) != len(set(rids)):
            erros.append(f'Título {cid}: lista de recebíveis com ID repetido.')
            continue

        conflict = [rid for rid in rids if rid in rels_usados]
        if conflict:
            erros.append(
                f'Recebível(is) {conflict} já usado(s) em outro título nesta confirmação.'
            )
            continue

        with transaction.atomic():
            try:
                conta = ContaAReceber.objects.select_for_update().get(
                    id=cid,
                    empresa_id=empresa_id,
                    status__in=['pendente', 'cartao'],
                )
            except ContaAReceber.DoesNotExist:
                erros.append(f'Título {cid} não está pendente/cartão ou não existe.')
                continue

            rel_list: list[RelatorioRecebiveisMaquinaCartao] = []
            grupo_ok = True
            for rid in rids:
                try:
                    rel = RelatorioRecebiveisMaquinaCartao.objects.select_for_update().get(
                        id=rid, empresa_id=empresa_id
                    )
                except RelatorioRecebiveisMaquinaCartao.DoesNotExist:
                    erros.append(f'Recebível {rid} não encontrado.')
                    grupo_ok = False
                    break
                if rel.conciliado or rel.conta_a_receber_id:
                    erros.append(
                        f'Recebível {rid} já vinculado ou conciliado; grupo do título {cid} não aplicado.'
                    )
                    grupo_ok = False
                    break
                rel_list.append(rel)

            if not grupo_ok or not rel_list:
                continue

            tipo_t = tipo_cartao_conta(conta)
            if tipo_t == 'debito' and len(rel_list) > 1:
                erros.append(
                    f'Título {cid}: cobrança débito aceita apenas um lançamento de recebível por título.'
                )
                continue
            forma_ok = True
            for rel in rel_list:
                if not rel_forma_bate_tipo(rel.forma_pagamento, tipo_t):
                    erros.append(
                        f'Recebível {rel.id}: forma de pagamento não combina com a cobrança do título {cid}.'
                    )
                    forma_ok = False
                    break
            if not forma_ok:
                continue

            for rel in rel_list:
                _vincular_relatorio_na_conta(conta, rel)
            _atualizar_conta_totais_cartao(conta, rel_list)

            for rid in rids:
                rels_usados.add(rid)
            aplicados += len(rel_list)

    return aplicados, erros


def aplicar_pares(empresa_id: int, pares: list[dict[str, Any]]) -> tuple[int, list[str]]:
    """
    pares: [{'conta_id': int, 'relatorio_id': int}, ...]
    Agrupa por conta e delega a aplicar_grupos.
    """
    from collections import defaultdict

    by_conta: defaultdict[int, list[int]] = defaultdict(list)
    for par in pares:
        try:
            by_conta[int(par['conta_id'])].append(int(par['relatorio_id']))
        except (KeyError, TypeError, ValueError):
            continue
    grupos = [{'conta_id': k, 'relatorio_ids': v} for k, v in by_conta.items()]
    return aplicar_grupos(empresa_id, grupos)


def _somente_digitos(valor: str | None) -> str:
    return ''.join(c for c in str(valor or '') if c.isdigit())


def autorizacoes_equivalentes(auth_a: str | None, auth_b: str | None, maquinha: str | None = None) -> bool:
    """
    Compara autorizações.
    - Sempre: igualdade exata (após trim) ou mesmos dígitos.
    - STONE: também compara os últimos 4 ou 5 dígitos de ambos
      (conta costuma ter 5–6 dígitos; recebível Stone ID pode ser longo).
    """
    a_raw = (auth_a or '').strip()
    b_raw = (auth_b or '').strip()
    if not a_raw or not b_raw:
        return False
    if a_raw == b_raw:
        return True

    a = _somente_digitos(a_raw)
    b = _somente_digitos(b_raw)
    if not a or not b:
        return False
    if a == b:
        return True

    if (maquinha or '').strip().upper() != 'STONE':
        return False

    for n in (5, 4):
        if len(a) >= n and len(b) >= n and a[-n:] == b[-n:]:
            return True

    # Autorização curta (típica na NFSe) no final do STONE ID longo
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if 4 <= len(shorter) <= 6 and longer.endswith(shorter):
        return True
    return False


def buscar_relatorios_por_autorizacao(
    empresa_id: int,
    autorizacao: str | None,
    *,
    conciliado: bool | None = False,
):
    """
    Localiza recebíveis pela autorização da conta.
    Inclui match Stone pelos últimos 4/5 dígitos.
    """
    auth = (autorizacao or '').strip()
    if not auth:
        return RelatorioRecebiveisMaquinaCartao.objects.none()

    qs = RelatorioRecebiveisMaquinaCartao.objects.filter(empresa_id=empresa_id)
    if conciliado is not None:
        qs = qs.filter(conciliado=conciliado)

    # Match exato primeiro
    exatos = list(qs.filter(numero_autorizacao=auth))
    if exatos:
        return RelatorioRecebiveisMaquinaCartao.objects.filter(pk__in=[r.pk for r in exatos])

    auth_digits = _somente_digitos(auth)
    if not auth_digits:
        return RelatorioRecebiveisMaquinaCartao.objects.none()

    from django.db.models import Q

    q_sufixo = Q()
    for n in (5, 4):
        if len(auth_digits) >= n:
            q_sufixo |= Q(numero_autorizacao__endswith=auth_digits[-n:])
    if 4 <= len(auth_digits) <= 6:
        q_sufixo |= Q(numero_autorizacao__endswith=auth_digits)

    if not q_sufixo:
        return RelatorioRecebiveisMaquinaCartao.objects.none()

    candidatos = qs.filter(maquinha='STONE').filter(q_sufixo)
    ids = [
        r.pk for r in candidatos
        if autorizacoes_equivalentes(auth, r.numero_autorizacao, 'STONE')
    ]
    if not ids:
        return RelatorioRecebiveisMaquinaCartao.objects.none()
    return RelatorioRecebiveisMaquinaCartao.objects.filter(pk__in=ids)
