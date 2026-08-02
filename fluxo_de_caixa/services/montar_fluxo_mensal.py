"""Montagem do fluxo de caixa mensal estilo planilha (GRUPO × CATEGORIA × meses)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.db.models import Prefetch, Q, Sum

from categoria.models import Categoria
from contasapagar.models import ContasaPagar
from contasareceber.models import ContaAReceber
from emprestimos.models import Emprestimo, ParcelaEmprestimo
from notasfiscais.models import NotaFiscalServico
from planejamento_orcamentario.models import LancamentoOrcamento

MESES_NOME = (
    'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
    'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
)
MESES_CURTO = ('Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez')

FLAG_PCT_LIMITE = Decimal('10')


def _cap_empresa_q(empresa):
    return Q(empresa=empresa) | Q(empresa__isnull=True, fornecedor__empresa=empresa)


def _zeros(n: int) -> list[Decimal]:
    return [Decimal('0')] * n


def _somar_listas(*listas: list[Decimal]) -> list[Decimal]:
    if not listas:
        return []
    n = len(listas[0])
    total = _zeros(n)
    for lst in listas:
        for i, v in enumerate(lst):
            total[i] += v
    return total


def _tem_movimento(valores: list[Decimal]) -> bool:
    return any(v != 0 for v in valores)


def _celula_cmp(realizado, planejado, comparar=True):
    r = Decimal(str(realizado or 0))
    p = Decimal(str(planejado or 0))
    pct = None
    flag = False
    flag_tipo = ''
    if comparar:
        if p != 0:
            pct = ((r - p) / p * Decimal('100')).quantize(Decimal('0.01'))
            if abs(pct) >= FLAG_PCT_LIMITE:
                flag = True
                flag_tipo = 'acima' if pct > 0 else 'abaixo'
            else:
                flag_tipo = 'ok'
        elif r != 0:
            flag = True
            flag_tipo = 'sem_previsto'
    return {
        'realizado': r,
        'planejado': p,
        'pct': pct,
        'tem_pct': pct is not None,
        'flag': flag,
        'flag_tipo': flag_tipo,
    }


def _mapa_planejado_por_categoria(empresa, ano) -> dict[int, list[Decimal]]:
    mapa: dict[int, list[Decimal]] = {}
    qs = (
        LancamentoOrcamento.objects.filter(
            empresa=empresa,
            item__ativo=True,
            item__categoria_id__isnull=False,
            data_lancamento__year=ano,
        )
        .values('item__categoria_id', 'data_lancamento__month')
        .annotate(total=Sum('valor'))
    )
    for row in qs:
        cid = row['item__categoria_id']
        mes = row['data_lancamento__month']
        if cid not in mapa:
            mapa[cid] = _zeros(12)
        mapa[cid][mes - 1] += row['total'] or Decimal('0')
    return mapa


def _mapa_receitas_por_categoria_mes(empresa, ano) -> dict[tuple[int, int], Decimal]:
    """Receitas importadas do Conta Azul (conta_azul_parcela_id)."""
    mapa: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal('0'))
    base = ContaAReceber.objects.filter(
        empresa=empresa,
        conta_azul_parcela_id__gt='',
        categoria_id__isnull=False,
    )
    for row in base.filter(
        status='pago',
        data_recebimento__year=ano,
    ).values('categoria_id', 'data_recebimento__month').annotate(
        total=Sum('valor_recebido'),
    ):
        mapa[(row['categoria_id'], row['data_recebimento__month'])] += row['total'] or Decimal('0')

    for row in base.exclude(status='pago').filter(
        data_vencimento__year=ano,
    ).values('categoria_id', 'data_vencimento__month').annotate(
        total=Sum('valor_a_receber'),
    ):
        mapa[(row['categoria_id'], row['data_vencimento__month'])] += row['total'] or Decimal('0')
    return mapa


def _mapa_despesas_por_categoria_mes(empresa, ano, tipo: str) -> dict[tuple[int, int], Decimal]:
    """Despesas / investimento / DL importados do Conta Azul."""
    mapa: dict[tuple[int, int], Decimal] = defaultdict(lambda: Decimal('0'))
    base = ContasaPagar.objects.filter(
        empresa=empresa,
        conta_azul_parcela_id__gt='',
        categoria__tipo=tipo,
    )
    for row in base.filter(
        dtPag__year=ano,
        valorPago__gt=0,
    ).values('categoria_id', 'dtPag__month').annotate(total=Sum('valorPago')):
        mapa[(row['categoria_id'], row['dtPag__month'])] += row['total'] or Decimal('0')

    for row in base.filter(
        dtvenc__year=ano,
    ).filter(Q(valorPago__isnull=True) | Q(valorPago=0)).values(
        'categoria_id', 'dtvenc__month',
    ).annotate(total=Sum('valorDoc')):
        mapa[(row['categoria_id'], row['dtvenc__month'])] += row['total'] or Decimal('0')
    return mapa


def _serie_categoria(mapa: dict, cat_id: int, meses: range) -> list[Decimal]:
    return [mapa.get((cat_id, m), Decimal('0')) for m in meses]


def _serie_tipo(mapa: dict, categorias: list[Categoria], meses: range) -> list[Decimal]:
    por_mes = _zeros(len(list(meses)))
    for cat in categorias:
        for i, mes in enumerate(meses):
            por_mes[i] += mapa.get((cat.id, mes), Decimal('0'))
    return por_mes


def _plan_cat(mapa_plan: dict, cat_id: int, mes: int) -> Decimal:
    serie = mapa_plan.get(cat_id)
    if not serie:
        return Decimal('0')
    return serie[mes - 1]


def _plan_soma(mapa_plan, categorias, mes: int) -> Decimal:
    return sum(_plan_cat(mapa_plan, c.id, mes) for c in categorias)


def _ordenar_grupos(categorias: list[Categoria]) -> list[tuple[str, list[Categoria]]]:
    buckets: dict[str, list[Categoria]] = defaultdict(list)
    for cat in categorias:
        buckets[cat.grupo or 'Outros'].append(cat)
    return sorted(
        buckets.items(),
        key=lambda item: (
            min(c.classificacao or 'z' for c in item[1]),
            item[0].lower(),
        ),
    )


def _titulo_grupo(nome: str) -> str:
    nome = (nome or 'Outros').strip()
    if nome and nome[0].isdigit() and '.' in nome[:4]:
        return nome.upper()
    return nome.upper()


def _linha_planilha(
    *,
    grupo: str = '',
    categoria: str,
    valores: list[Decimal],
    nivel: str,
    indent: int = 0,
    categoria_id: int | None = None,
    bloco: str = 'receita',
) -> dict:
    negativo = bloco in ('despesa', 'investimento', 'lucro')
    return {
        'grupo': grupo,
        'categoria': categoria,
        'valores': valores,
        'nivel': nivel,
        'indent': indent,
        'categoria_id': categoria_id,
        'bloco': bloco,
        'negativo': negativo,
    }


def _bloco_categorias_planilha(
    categorias: list[Categoria],
    mapa: dict,
    meses: range,
    *,
    secao: str = '',
    bloco: str = 'receita',
) -> list[dict]:
    linhas: list[dict] = []
    for _idx, (nome_grupo, cats) in enumerate(_ordenar_grupos(categorias), 1):
        cats_ord = sorted(cats, key=lambda c: (c.classificacao or '', c.nome))
        itens: list[dict] = []
        vals_grupo = _zeros(len(list(meses)))
        for cat in cats_ord:
            if cat.sintetico == 'S':
                continue
            vals = _serie_categoria(mapa, cat.id, meses)
            if not _tem_movimento(vals):
                continue
            itens.append(
                _linha_planilha(
                    categoria=cat.nome,
                    valores=vals,
                    nivel='item',
                    indent=1,
                    categoria_id=cat.id,
                    bloco=bloco,
                )
            )
            vals_grupo = _somar_listas(vals_grupo, vals)
        if not itens and not _tem_movimento(vals_grupo):
            continue
        linhas.append(
            _linha_planilha(
                grupo=secao,
                categoria=_titulo_grupo(nome_grupo),
                valores=vals_grupo,
                nivel='grupo',
                bloco=bloco,
            )
        )
        linhas.extend(itens)
    return linhas


def _linha_resultado(
    total_rec: list[Decimal],
    total_desp: list[Decimal],
    *,
    total_inv: list[Decimal] | None = None,
    total_dl: list[Decimal] | None = None,
    categoria: str,
    nivel: str = 'resultado',
) -> dict:
    inv = total_inv or _zeros(len(total_rec))
    dl = total_dl or _zeros(len(total_rec))
    valores = [total_rec[i] - total_desp[i] - inv[i] - dl[i] for i in range(len(total_rec))]
    return _linha_planilha(categoria=categoria, valores=valores, nivel=nivel, bloco='resultado')


def _bloco_emprestimos_planilha(empresa, ano: int) -> tuple[list[dict], list[Decimal]]:
    """
    Parcelas de empréstimo no ano (data_vencimento):
    valor do mês = valor_pago se pago/quitado, senão valor_parcela do contrato.
    """
    n = 12
    emprestimos = (
        Emprestimo.objects.filter(empresa=empresa)
        .select_related('banco')
        .prefetch_related(
            Prefetch(
                'parcelas',
                queryset=ParcelaEmprestimo.objects.filter(
                    data_vencimento__year=ano,
                ).order_by('numero'),
            )
        )
        .order_by('banco__nome', 'numero_contrato')
    )

    por_banco: dict[str, list[tuple[str, list[Decimal]]]] = defaultdict(list)
    total_mes = _zeros(n)

    for emp in emprestimos:
        parcelas = list(emp.parcelas.all())
        if not parcelas:
            continue
        vals = _zeros(n)
        for p in parcelas:
            if not p.data_vencimento or p.data_vencimento.year != ano:
                continue
            m = p.data_vencimento.month
            if p.status in ('paga', 'quitada') or (p.valor_pago or 0) > 0:
                vals[m - 1] += (
                    p.valor_pago if p.valor_pago is not None else (p.valor_parcela or Decimal('0'))
                )
            else:
                vals[m - 1] += p.valor_parcela or Decimal('0')
        if not _tem_movimento(vals):
            continue

        banco_nome = ''
        if emp.banco_id:
            banco_nome = (emp.banco.nome or '').strip()
        if not banco_nome:
            banco_nome = (emp.cooperativa or '').strip() or 'Sem banco'

        rotulo = f'EMPRÉSTIMO CTR {emp.numero_contrato}'.strip()
        if emp.cliente and emp.cliente.strip() and emp.cliente.strip().upper() not in rotulo.upper():
            rotulo = f'{emp.cliente.strip()} — CTR {emp.numero_contrato}'

        por_banco[banco_nome].append((rotulo, vals))
        total_mes = _somar_listas(total_mes, vals)

    linhas: list[dict] = []
    if not por_banco:
        linhas.append(
            _linha_planilha(
                grupo='EMPR.',
                categoria='EMPRÉSTIMOS (parcelas do contrato)',
                valores=total_mes,
                nivel='subtotal',
                bloco='emprestimo',
            )
        )
        return linhas, total_mes

    linhas.append(
        _linha_planilha(
            grupo='EMPR.',
            categoria='EMPRÉSTIMOS — da empresa e pagamento da empresa',
            valores=total_mes,
            nivel='subtotal',
            bloco='emprestimo',
        )
    )
    for banco_nome in sorted(por_banco.keys(), key=lambda s: s.upper()):
        contratos = por_banco[banco_nome]
        vals_banco = _zeros(n)
        for _rotulo, vals in contratos:
            vals_banco = _somar_listas(vals_banco, vals)
        linhas.append(
            _linha_planilha(
                grupo='EMPR.',
                categoria=banco_nome,
                valores=vals_banco,
                nivel='grupo',
                bloco='emprestimo',
            )
        )
        for rotulo, vals in contratos:
            if _tem_movimento(vals):
                linhas.append(
                    _linha_planilha(
                        categoria=rotulo,
                        valores=vals,
                        nivel='item',
                        indent=1,
                        bloco='emprestimo',
                    )
                )

    linhas.append(
        _linha_planilha(
            grupo='EMPR.',
            categoria='TOTAL EMPRÉSTIMOS (parcelas)',
            valores=total_mes,
            nivel='subtotal',
            bloco='emprestimo',
        )
    )
    return linhas, total_mes


def montar_linhas_planilha(empresa, ano: int) -> list[dict]:
    meses = range(1, 13)
    n = len(list(meses))
    categorias = list(Categoria.objects.filter(empresa=empresa))
    rec_cats = [c for c in categorias if c.tipo == 'R']
    desp_cats = [c for c in categorias if c.tipo == 'D']
    inv_cats = [c for c in categorias if c.tipo == 'I']
    lucro_cats = [c for c in categorias if c.tipo == 'L']

    mapa_rec = _mapa_receitas_por_categoria_mes(empresa, ano)
    mapa_desp = _mapa_despesas_por_categoria_mes(empresa, ano, 'D')
    mapa_inv = _mapa_despesas_por_categoria_mes(empresa, ano, 'I')
    mapa_lucro = _mapa_despesas_por_categoria_mes(empresa, ano, 'L')

    linhas: list[dict] = []
    total_rec = _serie_tipo(mapa_rec, rec_cats, meses)
    total_desp = _serie_tipo(mapa_desp, desp_cats, meses)
    total_inv = _serie_tipo(mapa_inv, inv_cats, meses)
    total_dl = _serie_tipo(mapa_lucro, lucro_cats, meses)

    # 1. RECEITA (tipo R)
    if _tem_movimento(total_rec) or rec_cats:
        linhas.append(
            _linha_planilha(grupo='TIPO R', categoria='RECEITA', valores=total_rec, nivel='subtotal', bloco='receita')
        )
        linhas.extend(_bloco_categorias_planilha(rec_cats, mapa_rec, meses, bloco='receita'))

    # 2. DESPESAS (tipo D)
    linhas.append(
        _linha_planilha(grupo='TIPO D', categoria='DESPESAS', valores=total_desp, nivel='subtotal', bloco='despesa')
    )
    linhas.extend(_bloco_categorias_planilha(desp_cats, mapa_desp, meses, bloco='despesa'))

    # 3. Resultado: Receita − Despesas
    linhas.append(
        _linha_resultado(
            total_rec, total_desp,
            categoria='RESULTADO (Receita − Despesas)',
        )
    )

    # 4. INVESTIMENTO (tipo I)
    linhas.append(
        _linha_planilha(grupo='TIPO I', categoria='INVESTIMENTO', valores=total_inv, nivel='subtotal', bloco='investimento')
    )
    linhas.extend(_bloco_categorias_planilha(inv_cats, mapa_inv, meses, bloco='investimento'))

    # 5. Resultado: Receita − Despesas − Investimento
    linhas.append(
        _linha_resultado(
            total_rec, total_desp, total_inv=total_inv,
            categoria='RESULTADO (Receita − Despesas − Investimento)',
        )
    )

    # 6. DISTRIBUIÇÃO DE LUCRO (tipo L)
    linhas.append(
        _linha_planilha(grupo='TIPO L', categoria='DISTRIBUIÇÃO DE LUCRO', valores=total_dl, nivel='subtotal', bloco='lucro')
    )
    linhas.extend(_bloco_categorias_planilha(lucro_cats, mapa_lucro, meses, bloco='lucro'))

    # 7. Resultado após distribuição
    resultado_pos_dl = [
        total_rec[i] - total_desp[i] - total_inv[i] - total_dl[i] for i in range(n)
    ]
    linhas.append(
        _linha_planilha(
            categoria='RESULTADO (Receita − Despesas − Investimento − Distribuição de Lucro)',
            valores=resultado_pos_dl,
            nivel='total',
            bloco='resultado',
        )
    )

    # 8. Empréstimos (parcelas) + Resultado Geral
    emp_linhas, total_emp = _bloco_emprestimos_planilha(empresa, ano)
    linhas.extend(emp_linhas)
    resultado_geral = [resultado_pos_dl[i] - total_emp[i] for i in range(n)]
    linhas.append(
        _linha_planilha(
            categoria='RESULTADO GERAL (após empréstimos)',
            valores=resultado_geral,
            nivel='total',
            bloco='resultado',
        )
    )

    return linhas


def _valores_linha_planilha(
    linhas: list[dict],
    categoria: str,
    *,
    nivel: str = 'subtotal',
) -> list[float]:
    for linha in linhas:
        if linha.get('categoria') == categoria and linha.get('nivel') == nivel:
            return [float(v or 0) for v in linha['valores']]
    return [0.0] * 12


def montar_grafico_planilha(linhas: list[dict], ano: int) -> dict:
    """Séries mensais para gráfico do modo planilha (totais da tabela)."""
    import json

    labels = [f'{MESES_CURTO[m - 1]}/{ano}' for m in range(1, 13)]
    receitas = _valores_linha_planilha(linhas, 'RECEITA')
    despesas = _valores_linha_planilha(linhas, 'DESPESAS')
    investimento = _valores_linha_planilha(linhas, 'INVESTIMENTO')
    lucro = _valores_linha_planilha(linhas, 'DISTRIBUIÇÃO DE LUCRO')
    resultado = _valores_linha_planilha(
        linhas,
        'RESULTADO (Receita − Despesas − Investimento − Distribuição de Lucro)',
        nivel='total',
    )
    resultado_rd = _valores_linha_planilha(linhas, 'RESULTADO (Receita − Despesas)', nivel='resultado')
    emprestimos = _valores_linha_planilha(
        linhas, 'TOTAL EMPRÉSTIMOS (parcelas)', nivel='subtotal',
    )
    if not any(emprestimos):
        emprestimos = _valores_linha_planilha(
            linhas, 'EMPRÉSTIMOS (parcelas do contrato)', nivel='subtotal',
        )
    resultado_geral = _valores_linha_planilha(
        linhas, 'RESULTADO GERAL (após empréstimos)', nivel='total',
    )

    series = (
        receitas + despesas + investimento + lucro + resultado
        + resultado_rd + emprestimos + resultado_geral
    )
    return {
        'labels_json': json.dumps(labels, ensure_ascii=False),
        'receitas_json': json.dumps(receitas),
        'despesas_json': json.dumps(despesas),
        'investimento_json': json.dumps(investimento),
        'lucro_json': json.dumps(lucro),
        'resultado_json': json.dumps(resultado),
        'resultado_rd_json': json.dumps(resultado_rd),
        'emprestimos_json': json.dumps(emprestimos),
        'resultado_geral_json': json.dumps(resultado_geral),
        'tem_dados': any(v != 0 for v in series),
    }


def _bloco_emprestimos_completo(empresa, ano: int) -> tuple[list[dict], dict]:
    """
    Empréstimos Real × Plan. para o modo completo:
    - Plan. = valor_parcela (vencimento no mês)
    - Real. = valor_pago (ou parcela se paga/quitada)
    """
    n = 12
    emprestimos = (
        Emprestimo.objects.filter(empresa=empresa)
        .select_related('banco')
        .prefetch_related(
            Prefetch(
                'parcelas',
                queryset=ParcelaEmprestimo.objects.filter(
                    data_vencimento__year=ano,
                ).order_by('numero'),
            )
        )
        .order_by('banco__nome', 'numero_contrato')
    )

    por_banco: dict[str, list] = defaultdict(list)
    total_real = _zeros(n)
    total_plan = _zeros(n)

    def _tem_cmp(valores):
        return any(
            (c.get('realizado') or 0) != 0 or (c.get('planejado') or 0) != 0
            for c in valores
        )

    for emp in emprestimos:
        parcelas = list(emp.parcelas.all())
        if not parcelas:
            continue
        real_mes = _zeros(n)
        plan_mes = _zeros(n)
        for p in parcelas:
            if not p.data_vencimento or p.data_vencimento.year != ano:
                continue
            m = p.data_vencimento.month
            valor_plan = p.valor_parcela or Decimal('0')
            plan_mes[m - 1] += valor_plan
            if p.status in ('paga', 'quitada') or (p.valor_pago or 0) > 0:
                real_mes[m - 1] += (
                    p.valor_pago if p.valor_pago is not None else valor_plan
                )

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
            total_real[i] += real_mes[i]
            total_plan[i] += plan_mes[i]

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
        'valores': [_celula_cmp(total_real[i], total_plan[i]) for i in range(n)],
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
            if _tem_cmp(c['valores']):
                linhas.append(c)

    total = {
        'categoria': {'nome': 'TOTAL EMPRÉSTIMOS (parcelas)', 'tipo': 'emprestimo'},
        'valores': [_celula_cmp(total_real[i], total_plan[i]) for i in range(n)],
        'subtotal': True,
        'emprestimo_bloco': True,
    }
    linhas.append(total)
    return linhas, total


def montar_dados_completos(empresa, ano: int) -> tuple[list[dict], dict]:
    """Modo comparativo Real × Planejado (legado)."""
    import json

    meses = range(1, 13)
    categorias = list(Categoria.objects.filter(empresa=empresa))
    rec_cats = [c for c in categorias if c.tipo == 'R']
    desp_cats = [c for c in categorias if c.tipo == 'D']
    inv_cats = [c for c in categorias if c.tipo == 'I']
    lucro_cats = [c for c in categorias if c.tipo == 'L']

    mapa_rec = _mapa_receitas_por_categoria_mes(empresa, ano)
    mapa_desp = _mapa_despesas_por_categoria_mes(empresa, ano, 'D')
    mapa_inv = _mapa_despesas_por_categoria_mes(empresa, ano, 'I')
    mapa_lucro = _mapa_despesas_por_categoria_mes(empresa, ano, 'L')
    mapa_plan = _mapa_planejado_por_categoria(empresa, ano)

    dados: list[dict] = []

    def _linha_tem_movimento(valores):
        return any(
            (c.get('realizado') or 0) != 0 or (c.get('planejado') or 0) != 0
            for c in valores
        )

    def _celulas_vazias(comparar=True):
        return [_celula_cmp(0, 0, comparar=comparar) for _ in meses]

    def _add_bloco_tipo(tipo_label, tipo_cod, mapa, cats, secao_grupo=''):
        total = {
            'categoria': {'nome': tipo_label, 'tipo': tipo_cod},
            'valores': [],
            'subtotal': True,
        }
        for mes in meses:
            real = sum(mapa.get((c.id, mes), Decimal('0')) for c in cats)
            plan = _plan_soma(mapa_plan, cats, mes)
            total['valores'].append(_celula_cmp(real, plan))
        if _linha_tem_movimento(total['valores']) or tipo_label in ('DESPESAS', 'INVESTIMENTO', 'DISTRIBUIÇÃO DE LUCRO'):
            if secao_grupo and total['valores']:
                pass
            dados.append(total)

        for idx, (nome_grupo, cats_grupo) in enumerate(_ordenar_grupos(cats), 1):
            cats_analiticas = [c for c in sorted(cats_grupo, key=lambda c: (c.classificacao, c.nome)) if c.sintetico != 'S']
            vals_grupo = _zeros(12)
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
                for mes in meses:
                    real = mapa.get((cat.id, mes), Decimal('0'))
                    plan = _plan_cat(mapa_plan, cat.id, mes)
                    linha['valores'].append(_celula_cmp(real, plan))
                    vals_grupo[mes - 1] += real
                if _linha_tem_movimento(linha['valores']):
                    linhas_cat.append(linha)

            if not linhas_cat:
                continue

            vals_grupo_cel = []
            for mes in meses:
                plan_g = sum(_plan_cat(mapa_plan, c.id, mes) for c in cats_analiticas)
                vals_grupo_cel.append(_celula_cmp(vals_grupo[mes - 1], plan_g))

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
        for mes in meses:
            val = NotaFiscalServico.objects.filter(
                empresa=empresa, data_emissao__year=ano, data_emissao__month=mes,
            ).aggregate(t=Sum(campo))['t'] or 0
            linha['valores'].append(_celula_cmp(val, 0, comparar=False))
        if _linha_tem_movimento(linha['valores']):
            dados.append(linha)

    receita_total = _add_bloco_tipo('RECEITA', 'receita', mapa_rec, rec_cats)
    despesa_total = _add_bloco_tipo('DESPESAS', 'despesa', mapa_desp, desp_cats)

    rd_linha = {'categoria': {'nome': 'RESULTADO (Receita − Despesas)', 'tipo': 'resultado'}, 'valores': [], 'subtotal': True}
    for mes in meses:
        r = receita_total['valores'][mes - 1]
        d = despesa_total['valores'][mes - 1]
        rd_linha['valores'].append(_celula_cmp(r['realizado'] - d['realizado'], r['planejado'] - d['planejado']))
    dados.append(rd_linha)

    investimento_total = _add_bloco_tipo('INVESTIMENTO', 'investimento', mapa_inv, inv_cats)

    ri_linha = {'categoria': {'nome': 'RESULTADO (Receita − Despesas − Investimento)', 'tipo': 'resultado'}, 'valores': [], 'subtotal': True}
    for mes in meses:
        rd = rd_linha['valores'][mes - 1]
        inv = investimento_total['valores'][mes - 1]
        ri_linha['valores'].append(_celula_cmp(rd['realizado'] - inv['realizado'], rd['planejado'] - inv['planejado']))
    dados.append(ri_linha)

    dl_total = _add_bloco_tipo('DISTRIBUIÇÃO DE LUCRO', 'lucro', mapa_lucro, lucro_cats)

    total_geral = {
        'categoria': {'nome': 'RESULTADO (Receita − Despesas − Investimento − Distribuição de Lucro)', 'tipo': 'total'},
        'valores': [],
        'subtotal': True,
    }
    for mes in meses:
        ri = ri_linha['valores'][mes - 1]
        dl = dl_total['valores'][mes - 1]
        total_geral['valores'].append(_celula_cmp(ri['realizado'] - dl['realizado'], ri['planejado'] - dl['planejado']))
    dados.append(total_geral)

    # Empréstimos (Real × Plan.) + Resultado Geral
    emp_linhas, emp_total = _bloco_emprestimos_completo(empresa, ano)
    dados.extend(emp_linhas)

    resultado_geral = {
        'categoria': {'nome': 'RESULTADO GERAL (após empréstimos)', 'tipo': 'total'},
        'valores': [],
        'subtotal': True,
        'resultado_geral': True,
    }
    for i in range(12):
        r = total_geral['valores'][i]
        e = emp_total['valores'][i]
        resultado_geral['valores'].append(
            _celula_cmp(
                Decimal(str(r.get('realizado') or 0)) - Decimal(str(e.get('realizado') or 0)),
                Decimal(str(r.get('planejado') or 0)) - Decimal(str(e.get('planejado') or 0)),
            )
        )
    dados.append(resultado_geral)

    labels = [f'{MESES_CURTO[m - 1]}/{ano}' for m in meses]

    def _serie(linha, chave):
        return [float(cel.get(chave) or 0) for cel in linha['valores']]

    grafico_torre = {
        'labels_json': json.dumps(labels, ensure_ascii=False),
        'receitas_real_json': json.dumps(_serie(receita_total, 'realizado')),
        'receitas_plan_json': json.dumps(_serie(receita_total, 'planejado')),
        'despesas_real_json': json.dumps(_serie(despesa_total, 'realizado')),
        'despesas_plan_json': json.dumps(_serie(despesa_total, 'planejado')),
        'resultado_real_json': json.dumps(_serie(total_geral, 'realizado')),
        'resultado_plan_json': json.dumps(_serie(total_geral, 'planejado')),
        'resultado_geral_real_json': json.dumps(_serie(resultado_geral, 'realizado')),
        'resultado_geral_plan_json': json.dumps(_serie(resultado_geral, 'planejado')),
        'emprestimos_real_json': json.dumps(_serie(emp_total, 'realizado')),
        'emprestimos_plan_json': json.dumps(_serie(emp_total, 'planejado')),
        'tem_dados': any(
            v != 0
            for serie in (
                _serie(receita_total, 'realizado'),
                _serie(despesa_total, 'realizado'),
                _serie(total_geral, 'realizado'),
                _serie(emp_total, 'planejado'),
                _serie(resultado_geral, 'realizado'),
            )
            for v in serie
        ),
    }

    return dados, grafico_torre


def cabecalhos_meses(ano: int) -> list[dict]:
    return [
        {'numero': m, 'nome': MESES_NOME[m - 1], 'rotulo': f'{MESES_NOME[m - 1]}-{ano}'}
        for m in range(1, 13)
    ]
