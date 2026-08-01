"""Visão Real × Plan do planejamento orçamentário (estrutura do fluxo de caixa + empréstimos)."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import Prefetch

from emprestimos.models import Emprestimo, ParcelaEmprestimo
from fluxo_de_caixa.services.montar_fluxo_mensal import (
    _celula_cmp,
    montar_dados_completos,
)


def _linha_tem_movimento(valores) -> bool:
    return any(
        (c.get('realizado') or 0) != 0 or (c.get('planejado') or 0) != 0
        for c in valores
    )


def _bloco_emprestimos(empresa, ano: int) -> tuple[list[dict], dict]:
    """
    Parcelas do contrato por mês (data_vencimento):
    - Plan. = valor_parcela do contrato
    - Real. = valor_pago (se houver), senão valor_parcela quando parcela paga/quitada
    """
    meses = list(range(1, 13))
    emprestimos = (
        Emprestimo.objects.filter(empresa=empresa)
        .select_related('banco')
        .prefetch_related(
            Prefetch(
                'parcelas',
                queryset=ParcelaEmprestimo.objects.filter(data_vencimento__year=ano).order_by('numero'),
            )
        )
        .order_by('banco__nome', 'numero_contrato')
    )

    # banco_nome -> [(rotulo_contrato, valores[12])]
    por_banco: dict[str, list] = defaultdict(list)
    total_mes_real = [Decimal('0')] * 12
    total_mes_plan = [Decimal('0')] * 12

    for emp in emprestimos:
        parcelas = list(emp.parcelas.all())
        if not parcelas:
            continue

        real_mes = [Decimal('0')] * 12
        plan_mes = [Decimal('0')] * 12
        for p in parcelas:
            if not p.data_vencimento or p.data_vencimento.year != ano:
                continue
            m = p.data_vencimento.month
            valor_plan = p.valor_parcela or Decimal('0')
            plan_mes[m - 1] += valor_plan
            if p.status in ('paga', 'quitada') or (p.valor_pago or 0) > 0:
                real_mes[m - 1] += (p.valor_pago if p.valor_pago is not None else valor_plan)
            # Parcela aberta no mês: só entra no Plan (já somado); Real fica 0 até pagar

        if not any(v != 0 for v in plan_mes) and not any(v != 0 for v in real_mes):
            continue

        banco_nome = ''
        if emp.banco_id:
            banco_nome = (emp.banco.nome or '').strip()
        if not banco_nome:
            banco_nome = (emp.cooperativa or '').strip() or 'Sem banco'

        rotulo = f'EMPRÉSTIMO CTR {emp.numero_contrato}'.strip()
        if emp.cliente and emp.cliente.strip() and emp.cliente.strip().upper() not in rotulo.upper():
            # Contratos de terceiros / identificação extra
            rotulo = f'{emp.cliente.strip()} — CTR {emp.numero_contrato}'

        valores = [_celula_cmp(real_mes[i], plan_mes[i]) for i in range(12)]
        por_banco[banco_nome].append({
            'categoria': {'nome': rotulo, 'tipo': 'emprestimo'},
            'valores': valores,
            'subtotal': False,
            'emprestimo': True,
        })
        for i in range(12):
            total_mes_real[i] += real_mes[i]
            total_mes_plan[i] += plan_mes[i]

    linhas: list[dict] = []
    if not por_banco:
        total = {
            'categoria': {'nome': 'EMPRÉSTIMOS (parcelas do contrato)', 'tipo': 'emprestimo'},
            'valores': [_celula_cmp(0, 0) for _ in meses],
            'subtotal': True,
            'emprestimo_bloco': True,
        }
        return [total], total

    linhas.append({
        'categoria': {
            'nome': 'EMPRÉSTIMOS — da empresa e pagamento da empresa',
            'tipo': 'emprestimo',
        },
        'valores': [_celula_cmp(total_mes_real[i], total_mes_plan[i]) for i in range(12)],
        'subtotal': True,
        'emprestimo_bloco': True,
    })

    for banco_nome in sorted(por_banco.keys(), key=lambda s: s.upper()):
        contratos = por_banco[banco_nome]
        banco_real = [Decimal('0')] * 12
        banco_plan = [Decimal('0')] * 12
        for c in contratos:
            for i, cel in enumerate(c['valores']):
                banco_real[i] += Decimal(str(cel.get('realizado') or 0))
                banco_plan[i] += Decimal(str(cel.get('planejado') or 0))

        linhas.append({
            'categoria': {'nome': banco_nome, 'tipo': 'grupo'},
            'valores': [_celula_cmp(banco_real[i], banco_plan[i]) for i in range(12)],
            'subtotal': False,
            'grupo': True,
            'emprestimo': True,
        })
        for c in contratos:
            if _linha_tem_movimento(c['valores']):
                linhas.append(c)

    total = {
        'categoria': {'nome': 'TOTAL EMPRÉSTIMOS (parcelas)', 'tipo': 'emprestimo'},
        'valores': [_celula_cmp(total_mes_real[i], total_mes_plan[i]) for i in range(12)],
        'subtotal': True,
        'emprestimo_bloco': True,
    }
    linhas.append(total)
    return linhas, total


def montar_visao_real_plan(empresa, ano: int) -> tuple[list[dict], dict]:
    """
    Mesma estrutura do Fluxo Real × Plan, e após o RESULTADO final
    inclui as parcelas de empréstimo do ano (valor da parcela por mês do contrato).
    """
    dados, grafico = montar_dados_completos(empresa, ano)

    # Última linha RESULTADO geral do fluxo
    resultado_final = None
    for linha in reversed(dados):
        if linha.get('subtotal') and (linha.get('categoria') or {}).get('tipo') in ('total', 'resultado'):
            if 'Distribuição' in (linha['categoria'].get('nome') or '') or linha['categoria'].get('tipo') == 'total':
                resultado_final = linha
                break
    if resultado_final is None:
        for linha in reversed(dados):
            if linha.get('subtotal'):
                resultado_final = linha
                break

    emp_linhas, emp_total = _bloco_emprestimos(empresa, ano)
    dados.extend(emp_linhas)

    if resultado_final is not None:
        geral = {
            'categoria': {
                'nome': 'RESULTADO GERAL (após empréstimos)',
                'tipo': 'total',
            },
            'valores': [],
            'subtotal': True,
            'resultado_geral': True,
        }
        for i in range(12):
            r = resultado_final['valores'][i]
            e = emp_total['valores'][i]
            geral['valores'].append(
                _celula_cmp(
                    Decimal(str(r.get('realizado') or 0)) - Decimal(str(e.get('realizado') or 0)),
                    Decimal(str(r.get('planejado') or 0)) - Decimal(str(e.get('planejado') or 0)),
                )
            )
        dados.append(geral)

    return dados, grafico
