"""Indicadores gerenciais de estoque por empresa."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.db.models import Case, CharField, Count, F, Q, Sum, Value, When
from django.db.models.fields import DecimalField
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from estoque.alertas import contar_abaixo_estoque_minimo, queryset_abaixo_estoque_minimo
from estoque.models import MovimentoEstoque, NaturezaEstoque, ProdutoEstoque, RequisicaoEstoque, SaldoEstoqueSetor
from estoque.setores import SETOR_LISTA_CEGA_FARMACIA, SetorEstoque, rotulo_setor


def _fmt_moeda(valor) -> str:
    try:
        v = Decimal(str(valor or 0))
    except Exception:
        return '0,00'
    s = f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return s


def _fmt_numero(valor) -> str:
    try:
        v = Decimal(str(valor or 0))
    except Exception:
        return '0'
    if v == v.to_integral_value():
        return f'{int(v):,}'.replace(',', '.')
    s = f'{v:,.3f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return s.rstrip('0').rstrip(',')


def _valor_linha_custo_medio():
    return Coalesce(F('quantidade_estoque'), Decimal('0')) * Coalesce(
        F('valor_custo_medio'), Decimal('0')
    )


def _valor_linha_custo_contabil():
    return Coalesce(F('quantidade_estoque_contabil'), Decimal('0')) * Coalesce(
        F('valor_custo_contabil'), Decimal('0')
    )


_MESES_CURTO = ('Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez')


def _periodo_mes(ref: date | None = None) -> tuple[date, date]:
    hoje = ref or timezone.localdate()
    ini = hoje.replace(day=1)
    fim = hoje.replace(day=monthrange(hoje.year, hoje.month)[1])
    return ini, fim


def _primeiro_dia_mes(d: date) -> date:
    return d.replace(day=1)


def _add_meses(d: date, delta: int) -> date:
    m = d.month - 1 + delta
    y = d.year + m // 12
    m = m % 12 + 1
    return date(y, m, 1)


def _ultimos_12_meses(ref: date | None = None) -> list[tuple[date, date, str, str]]:
    """(início, fim, rótulo gráfico, chave YYYY-MM) dos últimos 12 meses."""
    ref_m = _primeiro_dia_mes(ref or timezone.localdate())
    out: list[tuple[date, date, str, str]] = []
    for i in range(11, -1, -1):
        ini = _add_meses(ref_m, -i)
        fim = ini.replace(day=monthrange(ini.year, ini.month)[1])
        rotulo = f'{_MESES_CURTO[ini.month - 1]}/{ini.strftime("%y")}'
        chave = ini.strftime('%Y-%m')
        out.append((ini, fim, rotulo, chave))
    return out


def _valor_movimento():
    return Coalesce(F('quantidade'), Decimal('0')) * Coalesce(F('valor_unitario'), Decimal('0'))


def _top_saidas_queryset(movs_baixa, *, limit: int = 10):
    dec = DecimalField(max_digits=18, decimal_places=2)
    return (
        movs_baixa.values('produto__codigo_produto', 'produto__descricao')
        .annotate(
            qtd=Sum('quantidade'),
            valor=Sum(_valor_movimento(), output_field=dec),
        )
        .order_by('-qtd')[:limit]
    )


def _serializar_top_saidas(rows) -> list[dict]:
    return [
        {
            'codigo': row['produto__codigo_produto'],
            'descricao': row['produto__descricao'],
            'qtd_fmt': _fmt_numero(row['qtd']),
            'valor_fmt': _fmt_moeda(row['valor']),
            'qtd': float(row['qtd'] or 0),
            'valor': float(row['valor'] or 0),
        }
        for row in rows
    ]


def _setor_consumo_movimento():
    """Setor onde a baixa/consumo é contabilizado."""
    return Case(
        When(setor_destino__gt='', then=F('setor_destino')),
        default=F('setor_origem'),
        output_field=CharField(),
    )


def _merge_setor_map(
    dest: dict[str, dict],
    rows,
    setor_key: str,
    *,
    campo_qtd: str,
    campo_val: str,
    prefix: str,
) -> None:
    for row in rows:
        setor = (row.get(setor_key) or '').strip() or SetorEstoque.FARMACIA
        if setor not in dest:
            dest[setor] = _linha_setor_vazia(setor)
        dest[setor][f'{prefix}_qtd'] += row[campo_qtd] or Decimal('0')
        dest[setor][f'{prefix}_valor'] += row[campo_val] or Decimal('0')


def _linha_setor_vazia(setor: str) -> dict:
    return {
        'setor': setor,
        'rotulo': rotulo_setor(setor),
        'estoque_qtd': Decimal('0'),
        'estoque_valor': Decimal('0'),
        'estoque_itens': 0,
        'entrada_qtd': Decimal('0'),
        'entrada_valor': Decimal('0'),
        'saida_qtd': Decimal('0'),
        'saida_valor': Decimal('0'),
    }


def _montar_dados_por_setor(
    empresa_id: int,
    *,
    ini: date,
    fim: date,
    qs_farm,
    movs_mes,
    dec: DecimalField,
) -> list[dict]:
    por_setor: dict[str, dict] = {}

    farm_qtd = qs_farm.aggregate(
        total=Coalesce(Sum('quantidade_estoque'), Decimal('0')),
        valor=Sum(_valor_linha_custo_medio(), output_field=dec),
        itens=Count('id', filter=Q(quantidade_estoque__gt=0)),
    )
    por_setor[SetorEstoque.FARMACIA] = {
        **_linha_setor_vazia(SetorEstoque.FARMACIA),
        'estoque_qtd': farm_qtd['total'] or Decimal('0'),
        'estoque_valor': farm_qtd['valor'] or Decimal('0'),
        'estoque_itens': farm_qtd['itens'] or 0,
    }

    saldos_setor = (
        SaldoEstoqueSetor.objects.filter(
            produto__empresa_id=empresa_id,
            produto__natureza=NaturezaEstoque.CONSUMIVEL,
        )
        .exclude(setor=SetorEstoque.FARMACIA)
        .values('setor')
        .annotate(
            qtd=Coalesce(Sum('quantidade'), Decimal('0')),
            valor=Sum(
                Coalesce(F('quantidade'), Decimal('0'))
                * Coalesce(F('produto__valor_custo_medio'), Decimal('0')),
                output_field=dec,
            ),
            itens=Count('produto', filter=Q(quantidade__gt=0)),
        )
    )
    for row in saldos_setor:
        setor = (row['setor'] or '').strip()
        if not setor:
            continue
        por_setor[setor] = {
            **_linha_setor_vazia(setor),
            'estoque_qtd': row['qtd'] or Decimal('0'),
            'estoque_valor': row['valor'] or Decimal('0'),
            'estoque_itens': row['itens'] or 0,
        }

    val_mov = Sum(_valor_movimento(), output_field=dec)

    setor_entrada_nf = Case(
        When(setor_destino__gt='', then=F('setor_destino')),
        default=Value(SetorEstoque.FARMACIA),
        output_field=CharField(),
    )
    _merge_setor_map(
        por_setor,
        movs_mes.filter(tipo=MovimentoEstoque.Tipo.ENTRADA_NF)
        .annotate(setor_ref=setor_entrada_nf)
        .values('setor_ref')
        .annotate(qtd=Sum('quantidade'), val=val_mov),
        'setor_ref',
        campo_qtd='qtd',
        campo_val='val',
        prefix='entrada',
    )

    _merge_setor_map(
        por_setor,
        movs_mes.filter(tipo=MovimentoEstoque.Tipo.TRANSFERENCIA)
        .values('setor_destino')
        .annotate(qtd=Sum('quantidade'), val=val_mov),
        'setor_destino',
        campo_qtd='qtd',
        campo_val='val',
        prefix='entrada',
    )

    _merge_setor_map(
        por_setor,
        movs_mes.filter(tipo=MovimentoEstoque.Tipo.TRANSFERENCIA)
        .values('setor_origem')
        .annotate(qtd=Sum('quantidade'), val=val_mov),
        'setor_origem',
        campo_qtd='qtd',
        campo_val='val',
        prefix='saida',
    )

    _merge_setor_map(
        por_setor,
        movs_mes.filter(tipo=MovimentoEstoque.Tipo.BAIXA)
        .annotate(setor_ref=_setor_consumo_movimento())
        .values('setor_ref')
        .annotate(qtd=Sum('quantidade'), val=val_mov),
        'setor_ref',
        campo_qtd='qtd',
        campo_val='val',
        prefix='saida',
    )

    ordem = [s[0] for s in SETOR_LISTA_CEGA_FARMACIA]
    ordem_idx = {c: i for i, c in enumerate(ordem)}

    linhas = []
    for setor_val, _rotulo in SETOR_LISTA_CEGA_FARMACIA:
        base = por_setor.get(setor_val) or _linha_setor_vazia(setor_val)
        linhas.append(
            {
                'setor': setor_val,
                'rotulo': base['rotulo'],
                'estoque_qtd_fmt': _fmt_numero(base['estoque_qtd']),
                'estoque_valor_fmt': _fmt_moeda(base['estoque_valor']),
                'estoque_itens': base['estoque_itens'],
                'entrada_qtd_fmt': _fmt_numero(base['entrada_qtd']),
                'entrada_valor_fmt': _fmt_moeda(base['entrada_valor']),
                'saida_qtd_fmt': _fmt_numero(base['saida_qtd']),
                'saida_valor_fmt': _fmt_moeda(base['saida_valor']),
                'estoque_qtd': float(base['estoque_qtd']),
                'entrada_qtd': float(base['entrada_qtd']),
                'saida_qtd': float(base['saida_qtd']),
            },
        )

    extras = [s for s in por_setor if s not in ordem_idx]
    for setor in sorted(extras, key=lambda s: por_setor[s]['rotulo'].lower()):
        base = por_setor[setor]
        linhas.append(
            {
                'setor': setor,
                'rotulo': base['rotulo'],
                'estoque_qtd_fmt': _fmt_numero(base['estoque_qtd']),
                'estoque_valor_fmt': _fmt_moeda(base['estoque_valor']),
                'estoque_itens': base['estoque_itens'],
                'entrada_qtd_fmt': _fmt_numero(base['entrada_qtd']),
                'entrada_valor_fmt': _fmt_moeda(base['entrada_valor']),
                'saida_qtd_fmt': _fmt_numero(base['saida_qtd']),
                'saida_valor_fmt': _fmt_moeda(base['saida_valor']),
                'estoque_qtd': float(base['estoque_qtd']),
                'entrada_qtd': float(base['entrada_qtd']),
                'saida_qtd': float(base['saida_qtd']),
            },
        )
    return linhas


def _serie_saidas_12_meses(empresa_id: int, ref: date | None = None) -> dict:
    meses = _ultimos_12_meses(ref)
    ini_global = meses[0][0]
    fim_global = meses[-1][1]
    dec = DecimalField(max_digits=18, decimal_places=2)

    por_mes = {
        row['mes'].strftime('%Y-%m'): row
        for row in (
            MovimentoEstoque.objects.filter(
                empresa_id=empresa_id,
                tipo=MovimentoEstoque.Tipo.BAIXA,
                criado_em__date__gte=ini_global,
                criado_em__date__lte=fim_global,
            )
            .annotate(mes=TruncMonth('criado_em'))
            .values('mes')
            .annotate(
                qtd=Sum('quantidade'),
                valor=Sum(_valor_movimento(), output_field=dec),
            )
        )
        if row['mes']
    }

    labels: list[str] = []
    qtds: list[float] = []
    valores: list[float] = []
    for _ini, _fim, rotulo, chave in meses:
        labels.append(rotulo)
        row = por_mes.get(chave)
        qtds.append(float(row['qtd'] or 0) if row else 0.0)
        valores.append(float(row['valor'] or 0) if row else 0.0)

    return {
        'labels': labels,
        'qtd': qtds,
        'valor': valores,
        'inicio': ini_global,
        'fim': fim_global,
    }


def montar_kpis_estoque(empresa_id: int | None, *, ref: date | None = None) -> dict:
    vazio = {
        'empresa_id': empresa_id,
        'periodo_inicio': None,
        'periodo_fim': None,
        'periodo_rotulo': '',
        'farmacia_produtos': 0,
        'farmacia_com_saldo': 0,
        'abaixo_minimo': 0,
        'valor_farmacia_medio_fmt': '0,00',
        'valor_farmacia_contabil_fmt': '0,00',
        'imobilizado_itens': 0,
        'valor_imobilizado_fmt': '0,00',
        'requisicoes_rascunho': 0,
        'requisicoes_mes': 0,
        'mov_entradas_mes': 0,
        'mov_baixas_mes': 0,
        'mov_transferencias_mes': 0,
        'mov_ajustes_mes': 0,
        'inventarios_abertos': 0,
        'alertas_amostra': [],
        'top_saidas_mes': [],
        'top_saidas_12m': [],
        'destaque_saida_qtd_mes': None,
        'destaque_saida_valor_mes': None,
        'chart_12m_labels': [],
        'chart_12m_qtd': [],
        'chart_12m_valor': [],
        'por_setor': [],
    }
    if not empresa_id:
        return vazio

    ini, fim = _periodo_mes(ref)
    dec = DecimalField(max_digits=18, decimal_places=2)

    qs_farm = ProdutoEstoque.objects.filter(
        empresa_id=empresa_id,
        natureza=NaturezaEstoque.CONSUMIVEL,
    )
    qs_imob = ProdutoEstoque.objects.filter(
        empresa_id=empresa_id,
        natureza=NaturezaEstoque.IMOBILIZADO,
    )

    agg_farm = qs_farm.aggregate(
        total=Count('id'),
        com_saldo=Count('id', filter=Q(quantidade_estoque__gt=0)),
        valor_medio=Sum(_valor_linha_custo_medio(), output_field=dec),
        valor_contabil=Sum(_valor_linha_custo_contabil(), output_field=dec),
    )
    agg_imob = qs_imob.aggregate(
        total=Count('id'),
        valor=Sum(_valor_linha_custo_medio(), output_field=dec),
    )

    movs = MovimentoEstoque.objects.filter(
        empresa_id=empresa_id,
        criado_em__date__gte=ini,
        criado_em__date__lte=fim,
    )
    mov_por_tipo = {
        row['tipo']: row['n']
        for row in movs.values('tipo').annotate(n=Count('id'))
    }

    movs_baixa_mes = movs.filter(tipo=MovimentoEstoque.Tipo.BAIXA)
    top_saidas_mes_rows = list(_top_saidas_queryset(movs_baixa_mes, limit=12))
    top_saidas_mes = _serializar_top_saidas(top_saidas_mes_rows)

    dec_mov = DecimalField(max_digits=18, decimal_places=2)
    top_valor_mes_row = (
        movs_baixa_mes.values('produto__codigo_produto', 'produto__descricao')
        .annotate(
            qtd=Sum('quantidade'),
            valor=Sum(_valor_movimento(), output_field=dec_mov),
        )
        .order_by('-valor')
        .first()
    )

    meses_12 = _ultimos_12_meses(ref)
    movs_baixa_12 = MovimentoEstoque.objects.filter(
        empresa_id=empresa_id,
        tipo=MovimentoEstoque.Tipo.BAIXA,
        criado_em__date__gte=meses_12[0][0],
        criado_em__date__lte=meses_12[-1][1],
    )
    top_saidas_12m = _serializar_top_saidas(_top_saidas_queryset(movs_baixa_12, limit=15))
    chart = _serie_saidas_12_meses(empresa_id, ref)

    try:
        from inventario.models import Inventario

        inv_abertos = Inventario.objects.filter(
            empresa_id=empresa_id,
            aberto=True,
            estoque_aplicado_em__isnull=True,
        ).count()
    except Exception:
        inv_abertos = 0

    alertas = list(
        queryset_abaixo_estoque_minimo(empresa_id).values(
            'codigo_produto',
            'descricao',
            'quantidade_estoque',
            'estoque_minimo',
        )[:10]
    )

    mes_nome = ini.strftime('%m/%Y')
    por_setor = _montar_dados_por_setor(
        empresa_id,
        ini=ini,
        fim=fim,
        qs_farm=qs_farm,
        movs_mes=movs,
        dec=dec,
    )

    return {
        'empresa_id': empresa_id,
        'periodo_inicio': ini,
        'periodo_fim': fim,
        'periodo_rotulo': mes_nome,
        'farmacia_produtos': agg_farm['total'] or 0,
        'farmacia_com_saldo': agg_farm['com_saldo'] or 0,
        'abaixo_minimo': contar_abaixo_estoque_minimo(empresa_id),
        'valor_farmacia_medio_fmt': _fmt_moeda(agg_farm['valor_medio']),
        'valor_farmacia_contabil_fmt': _fmt_moeda(agg_farm['valor_contabil']),
        'imobilizado_itens': agg_imob['total'] or 0,
        'valor_imobilizado_fmt': _fmt_moeda(agg_imob['valor']),
        'requisicoes_rascunho': RequisicaoEstoque.objects.filter(
            empresa_id=empresa_id,
            status=RequisicaoEstoque.Status.RASCUNHO,
        ).count(),
        'requisicoes_mes': RequisicaoEstoque.objects.filter(
            empresa_id=empresa_id,
            status=RequisicaoEstoque.Status.CONCLUIDA,
            concluida_em__date__gte=ini,
            concluida_em__date__lte=fim,
        ).count(),
        'mov_entradas_mes': mov_por_tipo.get(MovimentoEstoque.Tipo.ENTRADA_NF, 0),
        'mov_baixas_mes': mov_por_tipo.get(MovimentoEstoque.Tipo.BAIXA, 0),
        'mov_transferencias_mes': mov_por_tipo.get(MovimentoEstoque.Tipo.TRANSFERENCIA, 0),
        'mov_ajustes_mes': mov_por_tipo.get(MovimentoEstoque.Tipo.AJUSTE, 0),
        'inventarios_abertos': inv_abertos,
        'alertas_amostra': alertas,
        'top_saidas_mes': top_saidas_mes,
        'top_saidas_12m': top_saidas_12m,
        'destaque_saida_qtd_mes': top_saidas_mes[0] if top_saidas_mes else None,
        'destaque_saida_valor_mes': (
            {
                'codigo': top_valor_mes_row['produto__codigo_produto'],
                'descricao': top_valor_mes_row['produto__descricao'],
                'qtd_fmt': _fmt_numero(top_valor_mes_row['qtd']),
                'valor_fmt': _fmt_moeda(top_valor_mes_row['valor']),
            }
            if top_valor_mes_row and (top_valor_mes_row['valor'] or 0) > 0
            else None
        ),
        'chart_12m_labels': chart['labels'],
        'chart_12m_qtd': chart['qtd'],
        'chart_12m_valor': chart['valor'],
        'chart_12m_inicio': chart['inicio'],
        'chart_12m_fim': chart['fim'],
        'por_setor': por_setor,
    }
