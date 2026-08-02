"""Visão anual do planejamento orçamentário (planejado + empréstimos) com período flexível."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Prefetch, Q, Sum

from categoria.models import Categoria
from contasapagar.models import ContasaPagar
from contasareceber.models import ContaAReceber
from emprestimos.models import Emprestimo, ParcelaEmprestimo
from fluxo_de_caixa.services.montar_fluxo_mensal import (
    MESES_CURTO,
    MESES_NOME,
    _celula_cmp,
    _ordenar_grupos,
    _titulo_grupo,
)
from notasfiscais.models import NotaFiscalServico
from planejamento_orcamentario.models import LancamentoOrcamento

MODOS_PERIODO = ('ano', 'mes', 'periodo')


def _ym(ano: int, mes: int) -> int:
    return ano * 12 + mes


def gerar_colunas(
    modo: str,
    *,
    ano: int | None = None,
    mes: int | None = None,
    ano_ini: int | None = None,
    mes_ini: int | None = None,
    ano_fim: int | None = None,
    mes_fim: int | None = None,
) -> list[tuple[int, int]]:
    """Lista ordenada de (ano, mês) para as colunas da tabela."""
    modo = (modo or 'ano').strip().lower()
    if modo == 'mes':
        a = int(ano or date.today().year)
        m = int(mes or date.today().month)
        m = max(1, min(12, m))
        return [(a, m)]

    if modo == 'periodo':
        ai = int(ano_ini or ano or date.today().year)
        mi = max(1, min(12, int(mes_ini or 1)))
        af = int(ano_fim or ai)
        mf = max(1, min(12, int(mes_fim or 12)))
        if _ym(af, mf) < _ym(ai, mi):
            ai, mi, af, mf = af, mf, ai, mi
        cols: list[tuple[int, int]] = []
        y, m = ai, mi
        while _ym(y, m) <= _ym(af, mf) and len(cols) < 36:
            cols.append((y, m))
            m += 1
            if m > 12:
                m = 1
                y += 1
        return cols or [(ai, mi)]

    a = int(ano or date.today().year)
    return [(a, m) for m in range(1, 13)]


def rotulos_colunas(colunas: list[tuple[int, int]]) -> list[dict]:
    return [
        {
            'ano': a,
            'mes': m,
            'nome': MESES_NOME[m - 1],
            'curto': MESES_CURTO[m - 1],
            'rotulo': f'{MESES_NOME[m - 1][:3]}/{a}',
            'rotulo_completo': f'{MESES_NOME[m - 1]}/{a}',
        }
        for a, m in colunas
    ]


def _limites(colunas: list[tuple[int, int]]) -> tuple[date, date]:
    a0, m0 = colunas[0]
    a1, m1 = colunas[-1]
    # último dia aproximado (28 cobre filtro por mês; usamos range de mês)
    from calendar import monthrange
    return date(a0, m0, 1), date(a1, m1, monthrange(a1, m1)[1])


def _idx(colunas: list[tuple[int, int]]) -> dict[tuple[int, int], int]:
    return {ym: i for i, ym in enumerate(colunas)}


def _zeros(n: int) -> list[Decimal]:
    return [Decimal('0')] * n


def _mapa_plan(empresa, colunas: list[tuple[int, int]]) -> dict[tuple[int, int, int], Decimal]:
    ini, fim = _limites(colunas)
    mapa: dict[tuple[int, int, int], Decimal] = defaultdict(lambda: Decimal('0'))
    qs = (
        LancamentoOrcamento.objects.filter(
            empresa=empresa,
            item__ativo=True,
            item__categoria_id__isnull=False,
            data_lancamento__gte=ini,
            data_lancamento__lte=fim,
        )
        .values('item__categoria_id', 'data_lancamento__year', 'data_lancamento__month')
        .annotate(total=Sum('valor'))
    )
    for row in qs:
        key = (row['item__categoria_id'], row['data_lancamento__year'], row['data_lancamento__month'])
        if key[1:] in _idx(colunas):
            mapa[key] += row['total'] or Decimal('0')
    return mapa


def _mapa_receitas(empresa, colunas: list[tuple[int, int]]) -> dict[tuple[int, int, int], Decimal]:
    ini, fim = _limites(colunas)
    mapa: dict[tuple[int, int, int], Decimal] = defaultdict(lambda: Decimal('0'))
    base = ContaAReceber.objects.filter(
        empresa=empresa,
        conta_azul_parcela_id__gt='',
        categoria_id__isnull=False,
    )
    for row in base.filter(
        status='pago',
        data_recebimento__gte=ini,
        data_recebimento__lte=fim,
    ).values('categoria_id', 'data_recebimento__year', 'data_recebimento__month').annotate(
        total=Sum('valor_recebido'),
    ):
        mapa[(row['categoria_id'], row['data_recebimento__year'], row['data_recebimento__month'])] += (
            row['total'] or Decimal('0')
        )
    for row in base.exclude(status='pago').filter(
        data_vencimento__gte=ini,
        data_vencimento__lte=fim,
    ).values('categoria_id', 'data_vencimento__year', 'data_vencimento__month').annotate(
        total=Sum('valor_a_receber'),
    ):
        mapa[(row['categoria_id'], row['data_vencimento__year'], row['data_vencimento__month'])] += (
            row['total'] or Decimal('0')
        )
    return mapa


def _mapa_despesas(empresa, colunas: list[tuple[int, int]], tipo: str) -> dict[tuple[int, int, int], Decimal]:
    ini, fim = _limites(colunas)
    mapa: dict[tuple[int, int, int], Decimal] = defaultdict(lambda: Decimal('0'))
    base = ContasaPagar.objects.filter(
        empresa=empresa,
        conta_azul_parcela_id__gt='',
        categoria__tipo=tipo,
    )
    for row in base.filter(
        dtPag__gte=ini,
        dtPag__lte=fim,
        valorPago__gt=0,
    ).values('categoria_id', 'dtPag__year', 'dtPag__month').annotate(total=Sum('valorPago')):
        mapa[(row['categoria_id'], row['dtPag__year'], row['dtPag__month'])] += row['total'] or Decimal('0')

    for row in base.filter(
        dtvenc__gte=ini,
        dtvenc__lte=fim,
    ).filter(Q(valorPago__isnull=True) | Q(valorPago=0)).values(
        'categoria_id', 'dtvenc__year', 'dtvenc__month',
    ).annotate(total=Sum('valorDoc')):
        mapa[(row['categoria_id'], row['dtvenc__year'], row['dtvenc__month'])] += row['total'] or Decimal('0')
    return mapa


def _serie_mapa(mapa, cat_id: int, colunas: list[tuple[int, int]]) -> list[Decimal]:
    return [mapa.get((cat_id, a, m), Decimal('0')) for a, m in colunas]


def _linha_tem_movimento(valores) -> bool:
    return any(
        (c.get('realizado') or 0) != 0 or (c.get('planejado') or 0) != 0
        for c in valores
    )


def _bloco_emprestimos(empresa, colunas: list[tuple[int, int]]) -> tuple[list[dict], dict]:
    """
    Parcelas do contrato por mês (data_vencimento):
    - Plan. = valor_parcela do contrato
    - Real. = valor_pago (se houver), senão valor_parcela quando parcela paga/quitada
    """
    n = len(colunas)
    idx = _idx(colunas)
    ini, fim = _limites(colunas)
    emprestimos = (
        Emprestimo.objects.filter(empresa=empresa)
        .select_related('banco')
        .prefetch_related(
            Prefetch(
                'parcelas',
                queryset=ParcelaEmprestimo.objects.filter(
                    data_vencimento__gte=ini,
                    data_vencimento__lte=fim,
                ).order_by('numero'),
            )
        )
        .order_by('banco__nome', 'numero_contrato')
    )

    por_banco: dict[str, list] = defaultdict(list)
    total_mes_real = _zeros(n)
    total_mes_plan = _zeros(n)

    for emp in emprestimos:
        parcelas = list(emp.parcelas.all())
        if not parcelas:
            continue

        real_mes = _zeros(n)
        plan_mes = _zeros(n)
        for p in parcelas:
            if not p.data_vencimento:
                continue
            pos = idx.get((p.data_vencimento.year, p.data_vencimento.month))
            if pos is None:
                continue
            valor_plan = p.valor_parcela or Decimal('0')
            plan_mes[pos] += valor_plan
            if p.status in ('paga', 'quitada') or (p.valor_pago or 0) > 0:
                real_mes[pos] += (p.valor_pago if p.valor_pago is not None else valor_plan)

        if not any(v != 0 for v in plan_mes) and not any(v != 0 for v in real_mes):
            continue

        banco_nome = ''
        if emp.banco_id:
            banco_nome = (emp.banco.nome or '').strip()
        if not banco_nome:
            banco_nome = (emp.cooperativa or '').strip() or 'Sem banco'

        rotulo = f'EMPRÉSTIMO CTR {emp.numero_contrato}'.strip()
        if emp.cliente and emp.cliente.strip() and emp.cliente.strip().upper() not in rotulo.upper():
            rotulo = f'{emp.cliente.strip()} — CTR {emp.numero_contrato}'

        valores = [_celula_cmp(real_mes[i], plan_mes[i]) for i in range(n)]
        por_banco[banco_nome].append({
            'categoria': {'nome': rotulo, 'tipo': 'emprestimo'},
            'valores': valores,
            'subtotal': False,
            'emprestimo': True,
        })
        for i in range(n):
            total_mes_real[i] += real_mes[i]
            total_mes_plan[i] += plan_mes[i]

    linhas: list[dict] = []
    if not por_banco:
        total = {
            'categoria': {'nome': 'EMPRÉSTIMOS (parcelas do contrato)', 'tipo': 'emprestimo'},
            'valores': [_celula_cmp(0, 0) for _ in range(n)],
            'subtotal': True,
            'emprestimo_bloco': True,
        }
        return [total], total

    linhas.append({
        'categoria': {
            'nome': 'EMPRÉSTIMOS — da empresa e pagamento da empresa',
            'tipo': 'emprestimo',
        },
        'valores': [_celula_cmp(total_mes_real[i], total_mes_plan[i]) for i in range(n)],
        'subtotal': True,
        'emprestimo_bloco': True,
    })

    for banco_nome in sorted(por_banco.keys(), key=lambda s: s.upper()):
        contratos = por_banco[banco_nome]
        banco_real = _zeros(n)
        banco_plan = _zeros(n)
        for c in contratos:
            for i, cel in enumerate(c['valores']):
                banco_real[i] += Decimal(str(cel.get('realizado') or 0))
                banco_plan[i] += Decimal(str(cel.get('planejado') or 0))

        linhas.append({
            'categoria': {'nome': banco_nome, 'tipo': 'grupo'},
            'valores': [_celula_cmp(banco_real[i], banco_plan[i]) for i in range(n)],
            'subtotal': False,
            'grupo': True,
            'emprestimo': True,
        })
        for c in contratos:
            if _linha_tem_movimento(c['valores']):
                linhas.append(c)

    total = {
        'categoria': {'nome': 'TOTAL EMPRÉSTIMOS (parcelas)', 'tipo': 'emprestimo'},
        'valores': [_celula_cmp(total_mes_real[i], total_mes_plan[i]) for i in range(n)],
        'subtotal': True,
        'emprestimo_bloco': True,
    }
    linhas.append(total)
    return linhas, total


def montar_visao_real_plan(empresa, colunas: list[tuple[int, int]]) -> tuple[list[dict], dict]:
    """
    Estrutura do fluxo + parcelas de empréstimo no período.
    `colunas` = lista de (ano, mês), ex.: ano cheio, um mês, ou 08/2026–07/2027.
    """
    import json

    if not colunas:
        colunas = gerar_colunas('ano', ano=date.today().year)

    n = len(colunas)
    categorias = list(Categoria.objects.filter(empresa=empresa))
    rec_cats = [c for c in categorias if c.tipo == 'R']
    desp_cats = [c for c in categorias if c.tipo == 'D']
    inv_cats = [c for c in categorias if c.tipo == 'I']
    lucro_cats = [c for c in categorias if c.tipo == 'L']

    mapa_rec = _mapa_receitas(empresa, colunas)
    mapa_desp = _mapa_despesas(empresa, colunas, 'D')
    mapa_inv = _mapa_despesas(empresa, colunas, 'I')
    mapa_lucro = _mapa_despesas(empresa, colunas, 'L')
    mapa_plan = _mapa_plan(empresa, colunas)

    dados: list[dict] = []

    def _plan_cat(cat_id: int, a: int, m: int) -> Decimal:
        return mapa_plan.get((cat_id, a, m), Decimal('0'))

    def _add_bloco_tipo(tipo_label, tipo_cod, mapa, cats):
        total = {
            'categoria': {'nome': tipo_label, 'tipo': tipo_cod},
            'valores': [],
            'subtotal': True,
        }
        for a, m in colunas:
            real = sum(mapa.get((c.id, a, m), Decimal('0')) for c in cats)
            plan = sum(_plan_cat(c.id, a, m) for c in cats)
            total['valores'].append(_celula_cmp(real, plan))
        if _linha_tem_movimento(total['valores']) or tipo_label in (
            'DESPESAS', 'INVESTIMENTO', 'DISTRIBUIÇÃO DE LUCRO',
        ):
            dados.append(total)

        for _idx_g, (nome_grupo, cats_grupo) in enumerate(_ordenar_grupos(cats), 1):
            cats_analiticas = [
                c for c in sorted(cats_grupo, key=lambda c: (c.classificacao, c.nome))
                if c.sintetico != 'S'
            ]
            vals_grupo_real = _zeros(n)
            linhas_cat = []
            for cat in cats_analiticas:
                linha = {
                    'categoria': {
                        'id': cat.id,
                        'nome': f'{cat.classificacao} {cat.nome}'.strip(),
                        'tipo': tipo_cod,
                    },
                    'valores': [],
                }
                for i, (a, m) in enumerate(colunas):
                    real = mapa.get((cat.id, a, m), Decimal('0'))
                    plan = _plan_cat(cat.id, a, m)
                    linha['valores'].append(_celula_cmp(real, plan))
                    vals_grupo_real[i] += real
                if _linha_tem_movimento(linha['valores']):
                    linhas_cat.append(linha)

            if not linhas_cat:
                continue

            vals_grupo_cel = []
            for i, (a, m) in enumerate(colunas):
                plan_g = sum(_plan_cat(c.id, a, m) for c in cats_analiticas)
                vals_grupo_cel.append(_celula_cmp(vals_grupo_real[i], plan_g))

            dados.append({
                'categoria': {'nome': _titulo_grupo(nome_grupo), 'tipo': 'grupo'},
                'valores': vals_grupo_cel,
                'subtotal': False,
                'grupo': True,
            })
            dados.extend(linhas_cat)

        return total

    # Faturamento
    for nome, campo in (('FATURAMENTO BRUTO', 'valor_bruto'), ('FATURAMENTO LÍQUIDO', 'valor_liquido')):
        linha = {'categoria': {'nome': nome, 'tipo': 'faturamento'}, 'valores': [], 'subtotal': True}
        for a, m in colunas:
            val = NotaFiscalServico.objects.filter(
                empresa=empresa, data_emissao__year=a, data_emissao__month=m,
            ).aggregate(t=Sum(campo))['t'] or 0
            linha['valores'].append(_celula_cmp(val, 0, comparar=False))
        if _linha_tem_movimento(linha['valores']):
            dados.append(linha)

    receita_total = _add_bloco_tipo('RECEITA', 'receita', mapa_rec, rec_cats)
    despesa_total = _add_bloco_tipo('DESPESAS', 'despesa', mapa_desp, desp_cats)

    rd_linha = {
        'categoria': {'nome': 'RESULTADO (Receita − Despesas)', 'tipo': 'resultado'},
        'valores': [],
        'subtotal': True,
    }
    for i in range(n):
        r = receita_total['valores'][i]
        d = despesa_total['valores'][i]
        rd_linha['valores'].append(
            _celula_cmp(r['realizado'] - d['realizado'], r['planejado'] - d['planejado'])
        )
    dados.append(rd_linha)

    investimento_total = _add_bloco_tipo('INVESTIMENTO', 'investimento', mapa_inv, inv_cats)

    ri_linha = {
        'categoria': {'nome': 'RESULTADO (Receita − Despesas − Investimento)', 'tipo': 'resultado'},
        'valores': [],
        'subtotal': True,
    }
    for i in range(n):
        rd = rd_linha['valores'][i]
        inv = investimento_total['valores'][i]
        ri_linha['valores'].append(
            _celula_cmp(rd['realizado'] - inv['realizado'], rd['planejado'] - inv['planejado'])
        )
    dados.append(ri_linha)

    dl_total = _add_bloco_tipo('DISTRIBUIÇÃO DE LUCRO', 'lucro', mapa_lucro, lucro_cats)

    total_geral = {
        'categoria': {
            'nome': 'RESULTADO (Receita − Despesas − Investimento − Distribuição de Lucro)',
            'tipo': 'total',
        },
        'valores': [],
        'subtotal': True,
    }
    for i in range(n):
        ri = ri_linha['valores'][i]
        dl = dl_total['valores'][i]
        total_geral['valores'].append(
            _celula_cmp(ri['realizado'] - dl['realizado'], ri['planejado'] - dl['planejado'])
        )
    dados.append(total_geral)

    emp_linhas, emp_total = _bloco_emprestimos(empresa, colunas)
    dados.extend(emp_linhas)

    geral = {
        'categoria': {'nome': 'RESULTADO GERAL (após empréstimos)', 'tipo': 'total'},
        'valores': [],
        'subtotal': True,
        'resultado_geral': True,
    }
    for i in range(n):
        r = total_geral['valores'][i]
        e = emp_total['valores'][i]
        geral['valores'].append(
            _celula_cmp(
                Decimal(str(r.get('realizado') or 0)) - Decimal(str(e.get('realizado') or 0)),
                Decimal(str(r.get('planejado') or 0)) - Decimal(str(e.get('planejado') or 0)),
            )
        )
    dados.append(geral)

    labels = [f'{MESES_CURTO[m - 1]}/{a}' for a, m in colunas]

    def _serie(linha, chave):
        return [float(cel.get(chave) or 0) for cel in linha['valores']]

    res_rd = _serie(rd_linha, 'planejado')
    res_final = _serie(total_geral, 'planejado')
    res_geral = _serie(geral, 'planejado')

    grafico_torre = {
        'labels_json': json.dumps(labels, ensure_ascii=False),
        'receitas_plan_json': json.dumps(_serie(receita_total, 'planejado')),
        'despesas_plan_json': json.dumps(_serie(despesa_total, 'planejado')),
        'resultado_rd_json': json.dumps(res_rd),
        'resultado_final_json': json.dumps(res_final),
        'resultado_geral_json': json.dumps(res_geral),
        # legado (compat)
        'resultado_plan_json': json.dumps(res_final),
        'tem_dados': any(
            v != 0
            for serie in (
                _serie(receita_total, 'planejado'),
                _serie(despesa_total, 'planejado'),
                res_rd,
                res_final,
                res_geral,
                _serie(emp_total, 'planejado'),
            )
            for v in serie
        ),
    }

    return dados, grafico_torre
