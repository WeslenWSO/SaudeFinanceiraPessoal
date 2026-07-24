"""Geração de lançamentos de rateio a partir de contas pagas/recebidas com regra e itens cadastrados."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q

from regrarateio.models import LancamentoRateio, RegraRateio, RegraRateioItem


def _periodo_contas_pagar_q(data_inicio, data_fim):
    """Conta entra no período se pagamento, vencimento ou emissão estiver no intervalo (como na lista por emissão)."""
    return (
        Q(dtPag__gte=data_inicio, dtPag__lte=data_fim)
        | Q(dtvenc__gte=data_inicio, dtvenc__lte=data_fim)
        | Q(dtEmissao__gte=data_inicio, dtEmissao__lte=data_fim)
    )


def _periodo_emissao_e_vencimento_contas_pagar_q(data_inicio, data_fim):
    """Conta entra no período quando emissão e vencimento estão ambos no intervalo filtrado."""
    return (
        Q(dtEmissao__gte=data_inicio, dtEmissao__lte=data_fim)
        & Q(dtvenc__gte=data_inicio, dtvenc__lte=data_fim)
    )


def _periodo_contas_pagar_alinhado_grade_resumo(data_inicio, data_fim):
    """
    Mesma janela temporal da grade «Rateio — pagamentos» no resumo de fechamento
    (``q_pgto_periodo`` em ``dashboard.views.resumo_fechamento``):
    categorias que não são distribuição de lucro (``tipo != 'L'``): data de **pagamento** no intervalo;
    categoria ``L``: data de **emissão** no intervalo.
    """
    return (
        Q(
            categoria__tipo='L',
            dtEmissao__gte=data_inicio,
            dtEmissao__lte=data_fim,
            dtEmissao__isnull=False,
        )
        | (
            ~Q(categoria__tipo='L')
            & Q(dtPag__gte=data_inicio, dtPag__lte=data_fim)
            & Q(dtPag__isnull=False)
        )
    )


def _empresa_contas_pagar_q(empresa_id):
    """
    Empresa da sessão: conta com ``empresa_id`` **ou** título antigo sem empresa mas com
    fornecedor vinculado à mesma empresa (comum após migrações / importações).
    """
    return Q(empresa_id=empresa_id) | Q(
        empresa__isnull=True,
        fornecedor__empresa_id=empresa_id,
    )


def _exists_itens_regra_rateio():
    """Para uso em annotate: existe RegraRateioItem ligado à regra da conta (``rateio_id``)."""
    return Exists(RegraRateioItem.objects.filter(regrarateio_id=OuterRef('rateio_id')))


def _exists_itens_regra_rateio_car():
    """Conta a receber: regra em ``regra_rateio_id``."""
    return Exists(RegraRateioItem.objects.filter(regrarateio_id=OuterRef('regra_rateio_id')))


def _base_valor_conta_pagar(conta):
    if conta.valorPago and conta.valorPago > 0:
        return conta.valorPago
    return conta.get_valor_total_com_ajustes()


def query_contas_pagar_sem_lancamento_rateio_resumo(
    empresa_id, data_inicio, data_fim, socio_ids=None
):
    """
    Contas a pagar **pagas** da empresa, **sem** ``LancamentoRateio`` no título, cuja data
    cai no **mesmo período** da grade «Rateio — pagamentos» do resumo de fechamento
    (``_periodo_contas_pagar_alinhado_grade_resumo``): para categorias que não são
    distribuição de lucro, **data de pagamento** no intervalo; para categoria «L»,
    **data de emissão** no intervalo.

    Com ``socio_ids``, restringe a títulos cuja regra (``rateio``) tem pelo menos um
    ``RegraRateioItem`` para um desses sócios (títulos sem regra somem ao filtrar sócio).
    """
    from contasapagar.models import ContasaPagar

    qs = (
        ContasaPagar.objects.filter(
            empresa_id=empresa_id,
            status='pago',
        )
        .filter(_periodo_contas_pagar_alinhado_grade_resumo(data_inicio, data_fim))
        .filter(
            ~Exists(
                LancamentoRateio.objects.filter(conta_pagar_id=OuterRef('pk'))
            )
        )
        .select_related('rateio', 'fornecedor', 'categoria')
        .order_by('-dtPag', '-dtvenc', '-id')
    )

    if socio_ids:
        regra_ids_com_socio = (
            RegraRateioItem.objects.filter(socios_id__in=list(socio_ids))
            .values_list('regrarateio_id', flat=True)
            .distinct()
        )
        qs = qs.filter(rateio_id__in=regra_ids_com_socio)

    caps = list(qs)
    regra_ids = {c.rateio_id for c in caps if c.rateio_id}
    itens_por_regra = {}
    if regra_ids:
        agg = (
            RegraRateioItem.objects.filter(regrarateio_id__in=regra_ids)
            .values('regrarateio_id')
            .annotate(n=Count('id'))
        )
        itens_por_regra = {row['regrarateio_id']: row['n'] for row in agg}

    resultado = []
    for cap in caps:
        tem_regra = cap.rateio_id is not None
        n_itens = itens_por_regra.get(cap.rateio_id, 0) if cap.rateio_id else 0
        tem_itens = n_itens > 0
        pode_aplicar = tem_regra and tem_itens

        if not tem_regra:
            rotulo = 'Sem regra no título'
        elif not tem_itens:
            rotulo = 'Regra sem sócios/%'
        else:
            rotulo = 'Pode aplicar'

        base = _base_valor_conta_pagar(cap)
        resultado.append(
            {
                'id': cap.id,
                'descricao': (cap.descricao or '')[:120],
                'fornecedor': str(cap.fornecedor) if cap.fornecedor_id else '',
                'dt_emissao': cap.dtEmissao.isoformat() if cap.dtEmissao else None,
                'dt_pag': cap.dtPag.isoformat() if cap.dtPag else None,
                'dt_venc': cap.dtvenc.isoformat() if cap.dtvenc else None,
                'valor_base': format(base, '.2f'),
                'regra': str(cap.rateio) if cap.rateio_id else '—',
                'ja_gerado': False,
                'tem_regra': tem_regra,
                'pode_aplicar': pode_aplicar,
                'rotulo_status': rotulo,
            }
        )
    return resultado


def query_contas_pagar_rateio_candidatas(
    empresa_id,
    data_inicio,
    data_fim,
    socio_ids=None,
    *,
    alinhado_grade_resumo=False,
):
    """
    Lista despesas sem pagamento no período para a empresa (inclui sem regra),
    usando emissão e vencimento dentro do mês/faixa filtrada no modal.

    ``pode_aplicar``: só verdadeiro com regra no título, itens na regra e ainda sem rateio gravado.

    ``socio_ids``: quando informado (lista de PK de Sócio), restringe a títulos cuja regra de rateio
    (``rateio``) possui pelo menos um ``RegraRateioItem`` para um desses sócios (como o filtro de
    sócio da grade de rateio por ``LancamentoRateio.socio_id``).

    ``alinhado_grade_resumo``: preserva compatibilidade para chamadores antigos.
    """
    from contasapagar.models import ContasaPagar

    if alinhado_grade_resumo:
        periodo_q = _periodo_contas_pagar_alinhado_grade_resumo(data_inicio, data_fim)
        status_q = Q(status='pago')
        sem_pagamento_q = Q()
    else:
        periodo_q = _periodo_emissao_e_vencimento_contas_pagar_q(data_inicio, data_fim)
        status_q = ~Q(status='cancelado')
        sem_pagamento_q = ~Q(status='pago') & Q(dtPag__isnull=True)

    qs = (
        ContasaPagar.objects.filter(status_q)
        .filter(sem_pagamento_q)
        .filter(_empresa_contas_pagar_q(empresa_id))
        .filter(periodo_q)
        .select_related('rateio', 'fornecedor', 'categoria')
        .order_by('-dtEmissao', '-dtvenc', '-id')
    )

    if socio_ids:
        regra_ids_com_socio = (
            RegraRateioItem.objects.filter(socios_id__in=list(socio_ids))
            .values_list('regrarateio_id', flat=True)
            .distinct()
        )
        qs = qs.filter(rateio_id__in=regra_ids_com_socio)

    caps = list(qs)
    ids = [c.id for c in caps]
    ja_ids = set(
        LancamentoRateio.objects.filter(conta_pagar_id__in=ids).values_list(
            'conta_pagar_id', flat=True
        )
    )

    # Contagem de itens por regra (evita N+1 e problemas de Exists em alguns SGBDs)
    regra_ids = {c.rateio_id for c in caps if c.rateio_id}
    itens_por_regra = {}
    if regra_ids:
        agg = (
            RegraRateioItem.objects.filter(regrarateio_id__in=regra_ids)
            .values('regrarateio_id')
            .annotate(n=Count('id'))
        )
        itens_por_regra = {row['regrarateio_id']: row['n'] for row in agg}

    resultado = []
    for cap in caps:
        ja = cap.id in ja_ids
        tem_regra = cap.rateio_id is not None
        n_itens = itens_por_regra.get(cap.rateio_id, 0) if cap.rateio_id else 0
        tem_itens = n_itens > 0
        pode_aplicar = tem_regra and tem_itens and not ja

        if ja:
            rotulo = 'Já rateado'
        elif not tem_regra:
            rotulo = 'Sem regra no título'
        elif not tem_itens:
            rotulo = 'Regra sem sócios/%'
        else:
            rotulo = 'Pode aplicar'

        base = _base_valor_conta_pagar(cap)
        resultado.append(
            {
                'id': cap.id,
                'descricao': (cap.descricao or '')[:120],
                'fornecedor': str(cap.fornecedor) if cap.fornecedor_id else '',
                'dt_emissao': cap.dtEmissao.isoformat() if cap.dtEmissao else None,
                'dt_pag': cap.dtPag.isoformat() if cap.dtPag else None,
                'dt_venc': cap.dtvenc.isoformat() if cap.dtvenc else None,
                'valor_base': format(base, '.2f'),
                'regra': str(cap.rateio) if cap.rateio_id else '—',
                'ja_gerado': ja,
                'tem_regra': tem_regra,
                'pode_aplicar': pode_aplicar,
                'rotulo_status': rotulo,
            }
        )
    return resultado


def _periodo_contas_receber_q(data_inicio, data_fim):
    """Título entra no período se recebimento, vencimento ou emissão estiver no intervalo."""
    return (
        Q(data_recebimento__gte=data_inicio, data_recebimento__lte=data_fim)
        | Q(data_vencimento__gte=data_inicio, data_vencimento__lte=data_fim)
        | Q(data_emissao__gte=data_inicio, data_emissao__lte=data_fim)
    )


def query_contas_receber_rateio_candidatas(empresa_id, data_inicio, data_fim):
    """
    Lista contas a receber **pagas** no período para a empresa (inclui sem regra no título).
    Mesma ideia de ``query_contas_pagar_rateio_candidatas``; lançamentos gerados com valor positivo.
    """
    from contasareceber.models import ContaAReceber

    qs = (
        ContaAReceber.objects.filter(status='pago')
        .filter(empresa_id=empresa_id)
        .filter(_periodo_contas_receber_q(data_inicio, data_fim))
        .select_related('regra_rateio', 'nota', 'nota__socio')
        .order_by('-data_recebimento', '-data_vencimento', '-id')
    )

    cars = list(qs)
    ids = [c.id for c in cars]
    ja_ids = set(
        LancamentoRateio.objects.filter(conta_receber_id__in=ids).values_list(
            'conta_receber_id', flat=True
        )
    )

    regra_ids = {c.regra_rateio_id for c in cars if c.regra_rateio_id}
    itens_por_regra = {}
    if regra_ids:
        agg = (
            RegraRateioItem.objects.filter(regrarateio_id__in=regra_ids)
            .values('regrarateio_id')
            .annotate(n=Count('id'))
        )
        itens_por_regra = {row['regrarateio_id']: row['n'] for row in agg}

    resultado = []
    for car in cars:
        ja = car.id in ja_ids
        tem_regra = car.regra_rateio_id is not None
        n_itens = itens_por_regra.get(car.regra_rateio_id, 0) if car.regra_rateio_id else 0
        tem_itens = n_itens > 0
        pode_aplicar = tem_regra and tem_itens and not ja

        if ja:
            rotulo = 'Já rateado'
        elif not tem_regra:
            rotulo = 'Sem regra no título'
        elif not tem_itens:
            rotulo = 'Regra sem sócios/%'
        else:
            rotulo = 'Pode aplicar'

        base = _base_valor_conta_receber(car)
        # Sócio cadastrado na conta a receber (via nota fiscal), não o da regra de rateio.
        socio_txt = '—'
        if car.nota_id and getattr(car.nota, 'socio_id', None):
            socio_txt = str(car.nota.socio)

        resultado.append(
            {
                'id': car.id,
                'descricao': (car.observacao or car.doc or car.cliente or '')[:120],
                'cliente': (car.cliente or '')[:120],
                'dt_emissao': car.data_emissao.isoformat() if car.data_emissao else None,
                'dt_pag': car.data_recebimento.isoformat() if car.data_recebimento else None,
                'dt_venc': car.data_vencimento.isoformat() if car.data_vencimento else None,
                'valor_base': format(base, '.2f'),
                'regra': str(car.regra_rateio) if car.regra_rateio_id else '—',
                'socio_txt': socio_txt,
                'ja_gerado': ja,
                'tem_regra': tem_regra,
                'pode_aplicar': pode_aplicar,
                'rotulo_status': rotulo,
            }
        )
    return resultado


def _base_valor_conta_receber(conta):
    if conta.valor_recebido and conta.valor_recebido > 0:
        return conta.valor_recebido
    return conta.valor_a_receber


def valor_base_titulo_de_lancamento(lancamento):
    """Valor base usado no rateio (mesma lógica da geração automática)."""
    if lancamento.conta_pagar_id:
        return _base_valor_conta_pagar(lancamento.conta_pagar)
    if lancamento.conta_receber_id:
        return _base_valor_conta_receber(lancamento.conta_receber)
    return Decimal('0')


def _gerar_linhas_rateio_conta_pagar(cap, regra, itens):
    """Cria lançamentos de rateio para uma conta a pagar. Retorna quantidade de linhas criadas."""
    base = _base_valor_conta_pagar(cap)
    data_pg = cap.dtPag or cap.dtvenc
    desc = (cap.descricao or '')[:255]
    criados = 0
    for item in itens:
        perc = item.percRateio or Decimal('0')
        bruto = (base * perc) / Decimal('100')
        valor = -bruto.quantize(Decimal('0.01'))
        LancamentoRateio.objects.create(
            empresa_id=cap.empresa_id,
            conta_pagar=cap,
            conta_receber=None,
            data_pagamento=data_pg,
            tipo=LancamentoRateio.TIPO_PGTO,
            descricao=desc,
            regra_rateio=regra,
            socio=item.socios,
            valor=valor,
        )
        criados += 1
    return criados


@transaction.atomic
def gerar_rateio_contas_pagar(empresa_id=None, conta_pagar_ids=None, regra_id_forcar=None):
    """
    Para cada conta a pagar paga: gera lançamentos por item da regra (valor negativo).

    Se ``regra_id_forcar`` for informado, essa regra é usada para **todos** os títulos
    selecionados (útil no modal sem regra no cadastro). Caso contrário, usa a regra
    já cadastrada em cada título (e exige itens na regra do título).

    Ignora contas que já possuem lançamentos de rateio.
    """
    from contasapagar.models import ContasaPagar

    regra_forcada = None
    if regra_id_forcar:
        qrf = RegraRateio.objects.filter(pk=regra_id_forcar)
        if empresa_id:
            qrf = qrf.filter(empresa_id=empresa_id)
        regra_forcada = qrf.first()
        if not regra_forcada or not RegraRateioItem.objects.filter(regrarateio=regra_forcada).exists():
            return 0, 0

    base_qs = ContasaPagar.objects.select_related('rateio', 'empresa', 'fornecedor')
    if conta_pagar_ids is not None:
        base_qs = base_qs.filter(~Q(status='cancelado')).filter(~Q(status='pago'), dtPag__isnull=True)
    else:
        base_qs = base_qs.filter(status='pago')
    if empresa_id:
        base_qs = base_qs.filter(_empresa_contas_pagar_q(empresa_id))
    if conta_pagar_ids is not None:
        base_qs = base_qs.filter(pk__in=conta_pagar_ids)

    if regra_forcada:
        qs = base_qs
    else:
        qs = (
            base_qs.filter(rateio__isnull=False)
            .annotate(_tem_itens_rateio=_exists_itens_regra_rateio())
            .filter(_tem_itens_rateio=True)
        )

    criados = 0
    ignorados = 0

    if conta_pagar_ids is not None:
        encontrados = set(qs.values_list('pk', flat=True))
        solicitados = set(int(x) for x in conta_pagar_ids)
        ignorados += len(solicitados - encontrados)

    for cap in qs:
        if LancamentoRateio.objects.filter(conta_pagar=cap).exists():
            ignorados += 1
            continue

        regra = regra_forcada if regra_forcada else cap.rateio
        if not regra:
            ignorados += 1
            continue
        if cap.empresa_id and regra.empresa_id != cap.empresa_id:
            ignorados += 1
            continue

        itens = list(RegraRateioItem.objects.filter(regrarateio=regra).select_related('socios'))
        if not itens:
            ignorados += 1
            continue

        criados += _gerar_linhas_rateio_conta_pagar(cap, regra, itens)

    return criados, ignorados


def _gerar_linhas_rateio_conta_receber(car, regra, itens):
    """Cria lançamentos de rateio para uma conta a receber. Retorna quantidade de linhas criadas."""
    base = _base_valor_conta_receber(car)
    data_pg = car.data_recebimento or car.data_vencimento
    desc = (car.observacao or car.cliente or car.doc or '')[:255]
    criados = 0
    for item in itens:
        perc = item.percRateio or Decimal('0')
        bruto = (base * perc) / Decimal('100')
        valor = bruto.quantize(Decimal('0.01'))
        LancamentoRateio.objects.create(
            empresa_id=car.empresa_id,
            conta_pagar=None,
            conta_receber=car,
            data_pagamento=data_pg,
            tipo=LancamentoRateio.TIPO_RECEBIMENTO,
            descricao=desc,
            regra_rateio=regra,
            socio=item.socios,
            valor=valor,
        )
        criados += 1
    return criados


def preview_linhas_rateio_por_regra(regra_id, valor_base, tipo_lancamento, empresa_id=None):
    """
    Retorna lista de dicts {socio_id, socio_nome, perc, valor} para exibição/JSON.
    tipo_lancamento: LancamentoRateio.TIPO_PGTO ou TIPO_RECEBIMENTO
    """
    q = RegraRateio.objects.filter(pk=regra_id)
    if empresa_id is not None:
        q = q.filter(empresa_id=empresa_id)
    regra = q.first()
    if not regra:
        return []
    itens = list(
        RegraRateioItem.objects.filter(regrarateio=regra)
        .select_related('socios')
        .order_by('socios_id')
    )
    base = valor_base if isinstance(valor_base, Decimal) else Decimal(str(valor_base))
    out = []
    for item in itens:
        perc = item.percRateio or Decimal('0')
        bruto = (base * perc) / Decimal('100')
        if tipo_lancamento == LancamentoRateio.TIPO_PGTO:
            valor = -bruto.quantize(Decimal('0.01'))
        else:
            valor = bruto.quantize(Decimal('0.01'))
        nome = str(item.socios) if item.socios_id else ''
        out.append(
            {
                'socio_id': item.socios_id,
                'socio_nome': nome,
                'perc': str(perc),
                'valor': str(valor),
            }
        )
    return out


@transaction.atomic
def reaplicar_regra_no_titulo(lancamento_id, nova_regra_id):
    """
    Remove todos os lançamentos de rateio do mesmo título (CAP ou CAR) e gera de novo
    conforme a nova regra e o valor base atual do título. Atualiza a regra no cadastro do título.

    Retorna (n_linhas_criadas,).
    """
    from contasapagar.models import ContasaPagar
    from contasareceber.models import ContaAReceber

    lanc = (
        LancamentoRateio.objects.select_related('conta_pagar', 'conta_receber', 'empresa')
        .filter(pk=lancamento_id)
        .first()
    )
    if not lanc:
        raise ValueError('Lançamento não encontrado.')

    empresa_titulo = lanc.empresa_id
    if not empresa_titulo and lanc.conta_pagar_id:
        empresa_titulo = lanc.conta_pagar.empresa_id
    if not empresa_titulo and lanc.conta_receber_id:
        empresa_titulo = lanc.conta_receber.empresa_id

    q = RegraRateio.objects.filter(pk=nova_regra_id)
    if empresa_titulo:
        q = q.filter(empresa_id=empresa_titulo)
    regra = q.first()
    if not regra:
        raise ValueError('Regra de rateio inválida ou não pertence à empresa do título.')

    itens = list(
        RegraRateioItem.objects.filter(regrarateio=regra).select_related('socios')
    )
    if not itens:
        raise ValueError('A regra selecionada não possui sócios e percentuais cadastrados.')

    if lanc.conta_pagar_id:
        cap = ContasaPagar.objects.select_for_update().get(pk=lanc.conta_pagar_id)
        LancamentoRateio.objects.filter(conta_pagar=cap).delete()
        cap.rateio = regra
        cap.save(update_fields=['rateio'])
        n = _gerar_linhas_rateio_conta_pagar(cap, regra, itens)
        return (n,)

    if lanc.conta_receber_id:
        car = ContaAReceber.objects.select_for_update().get(pk=lanc.conta_receber_id)
        LancamentoRateio.objects.filter(conta_receber=car).delete()
        car.regra_rateio = regra
        car.save(update_fields=['regra_rateio'])
        n = _gerar_linhas_rateio_conta_receber(car, regra, itens)
        return (n,)

    raise ValueError('Lançamento sem origem (conta a pagar/receber).')


@transaction.atomic
def gerar_rateio_contas_receber(empresa_id=None, conta_receber_ids=None, regra_id_forcar=None):
    """
    Gera lançamentos de rateio a partir de contas a receber **pagas** (valores positivos).

    - Sem ``conta_receber_ids``: comportamento em lote — títulos pagos, com regra e ``rateio='S'``,
      com itens na regra (como antes).
    - Com ``conta_receber_ids`` (modal): filtra pelos IDs; se ``regra_id_forcar`` for informado,
      usa essa regra nos títulos selecionados (títulos sem regra podem ser cobertos pela escolha no modal).
    """
    from contasareceber.models import ContaAReceber

    regra_forcada = None
    if regra_id_forcar:
        qrf = RegraRateio.objects.filter(pk=regra_id_forcar)
        if empresa_id:
            qrf = qrf.filter(empresa_id=empresa_id)
        regra_forcada = qrf.first()
        if not regra_forcada or not RegraRateioItem.objects.filter(regrarateio=regra_forcada).exists():
            return 0, 0

    base_qs = ContaAReceber.objects.filter(status='pago').select_related('regra_rateio', 'empresa')
    if empresa_id:
        base_qs = base_qs.filter(empresa_id=empresa_id)
    if conta_receber_ids is not None:
        base_qs = base_qs.filter(pk__in=conta_receber_ids)

    if regra_forcada:
        qs = base_qs
    elif conta_receber_ids is not None:
        qs = (
            base_qs.filter(regra_rateio__isnull=False)
            .annotate(_tem_itens_rateio=_exists_itens_regra_rateio_car())
            .filter(_tem_itens_rateio=True)
        )
    else:
        qs = (
            base_qs.filter(regra_rateio__isnull=False, regra_rateio__rateio='S')
            .annotate(_tem_itens_rateio=_exists_itens_regra_rateio_car())
            .filter(_tem_itens_rateio=True)
        )

    criados = 0
    ignorados = 0

    if conta_receber_ids is not None:
        encontrados = set(qs.values_list('pk', flat=True))
        solicitados = set(int(x) for x in conta_receber_ids)
        ignorados += len(solicitados - encontrados)

    for car in qs:
        if LancamentoRateio.objects.filter(conta_receber=car).exists():
            ignorados += 1
            continue

        regra = regra_forcada if regra_forcada else car.regra_rateio
        if not regra:
            ignorados += 1
            continue
        if car.empresa_id and regra.empresa_id != car.empresa_id:
            ignorados += 1
            continue

        itens = list(
            RegraRateioItem.objects.filter(regrarateio=regra).select_related('socios')
        )
        if not itens:
            ignorados += 1
            continue

        criados += _gerar_linhas_rateio_conta_receber(car, regra, itens)

    return criados, ignorados
