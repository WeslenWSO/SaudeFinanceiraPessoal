from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.shortcuts import render, redirect
from django.db.models import Sum, F, Value, DecimalField, Case, When, Q, ExpressionWrapper
from django.db.models.functions import Coalesce, TruncMonth
from django.utils.dateparse import parse_date
from dateutil.relativedelta import relativedelta
import json
from .conta_azul_api import calcular_dre, calcular_dre_mensal, buscar_contas_a_receber

from empresa.models import Empresa
from notasfiscais.models import NotaFiscalServico
from regrarateio.models import LancamentoRateio
from regrarateio.services import query_contas_pagar_sem_lancamento_rateio_resumo
from socio.models import Socio
from contasareceber.models import BaixaContaAReceber, ContaAReceber
from contasapagar.models import ContasaPagar
from extrato.models import Lancamento, ContaBancaria
from SaudeFinanceira.buscajson import cnpj

#from SaudeFinanceira.buscajson import cnpj, cotacao


def _cap_empresa_q(empresa_id):
    return Q(empresa_id=empresa_id) | Q(empresa__isnull=True, fornecedor__empresa_id=empresa_id)


def _saldo_conta_extrato_ate(conta, empresa_id, ate: date) -> Decimal:
    """Saldo do extrato na data (inclusive), alinhado ao cadastro (saldo inicial + data base)."""
    movs = list(
        Lancamento.objects.filter(empresa_id=empresa_id, conta_id=conta.id, data__lte=ate).order_by(
            'data', 'criado_em', 'id'
        )
    )
    saldo_ini = conta.saldo_inicial or Decimal('0')
    data_base = conta.data_inicial_saldo
    if data_base:
        total_antes_base = sum(
            (m.valor for m in movs if m.data and m.data < data_base),
            Decimal('0'),
        )
        saldo_atual = saldo_ini - total_antes_base
        for m in movs:
            if m.data and m.data >= data_base:
                saldo_atual += m.valor
    else:
        saldo_atual = saldo_ini
        for m in movs:
            saldo_atual += m.valor
    return saldo_atual


def _saldo_extrato_empresa_ate(empresa_id, ate: date) -> Decimal:
    total = Decimal('0')
    for conta in ContaBancaria.objects.filter(empresa_id=empresa_id):
        total += _saldo_conta_extrato_ate(conta, empresa_id, ate)
    return total


def dashboard_inicio(request):
    """Painel principal: cards do mês, saldos por banco/sócio, formas de pagamento, categorias no ano e tabela diária."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return redirect('selecao_empresa')

    hoje = date.today()
    try:
        ano_ref = int(request.GET.get('ano') or hoje.year)
        mes_ref = int(request.GET.get('mes') or hoje.month)
    except (TypeError, ValueError):
        ano_ref, mes_ref = hoje.year, hoje.month
    if mes_ref < 1 or mes_ref > 12:
        mes_ref = hoje.month
    if ano_ref < 2000 or ano_ref > 2100:
        ano_ref = hoje.year

    primeiro_mes = date(ano_ref, mes_ref, 1)
    ultimo_mes = date(ano_ref, mes_ref, monthrange(ano_ref, mes_ref)[1])
    dia_antes_mes = primeiro_mes - timedelta(days=1)

    meses_pt = [
        '',
        'Janeiro',
        'Fevereiro',
        'Março',
        'Abril',
        'Maio',
        'Junho',
        'Julho',
        'Agosto',
        'Setembro',
        'Outubro',
        'Novembro',
        'Dezembro',
    ]
    titulo_mes = f'{meses_pt[mes_ref]} {ano_ref}'

    # --- Extrato no mês (todas as contas da empresa) ---
    lanc_mes = Lancamento.objects.filter(
        empresa_id=empresa_id,
        data__gte=primeiro_mes,
        data__lte=ultimo_mes,
    )
    receita_mes = lanc_mes.filter(valor__gt=0).aggregate(s=Coalesce(Sum('valor'), Value(Decimal('0'))))['s'] or Decimal(
        '0'
    )
    despesa_mes_raw = lanc_mes.filter(valor__lt=0).aggregate(s=Coalesce(Sum('valor'), Value(Decimal('0'))))['s'] or Decimal(
        '0'
    )
    despesa_mes_abs = abs(despesa_mes_raw)
    saldo_fluxo_mes = receita_mes + despesa_mes_raw

    def _label_conta_extrato_row(row):
        partes = []
        if row.get('conta__banco__nome'):
            partes.append(str(row['conta__banco__nome']))
        if row.get('conta__descricao'):
            partes.append(str(row['conta__descricao']))
        ag = (row.get('conta__agencia') or '').strip()
        ct = (row.get('conta__conta') or '').strip()
        if ag or ct:
            partes.append(f'{ag}/{ct}'.strip('/'))
        if len(partes) > 1:
            return ' — '.join(partes)
        if partes:
            return partes[0]
        if row.get('conta_id'):
            return f'Conta #{row["conta_id"]}'
        return 'Conta'

    rec_por_conta = (
        lanc_mes.filter(valor__gt=0)
        .values('conta_id', 'conta__banco__nome', 'conta__descricao', 'conta__agencia', 'conta__conta')
        .annotate(total=Coalesce(Sum('valor'), Value(Decimal('0'))))
        .order_by('-total')
    )
    pie_rec_labels = []
    pie_rec_vals = []
    for row in rec_por_conta:
        t = row['total'] or Decimal('0')
        if t > 0:
            pie_rec_labels.append(_label_conta_extrato_row(row))
            pie_rec_vals.append(float(t))

    des_por_conta = (
        lanc_mes.filter(valor__lt=0)
        .values('conta_id', 'conta__banco__nome', 'conta__descricao', 'conta__agencia', 'conta__conta')
        .annotate(total=Coalesce(Sum('valor'), Value(Decimal('0'))))
        .order_by('-total')
    )
    pie_des_labels = []
    pie_des_vals = []
    for row in des_por_conta:
        t = row['total'] or Decimal('0')
        if t < 0:
            pie_des_labels.append(_label_conta_extrato_row(row))
            pie_des_vals.append(float(abs(t)))

    saldo_extrato_fim_mes = _saldo_extrato_empresa_ate(empresa_id, ultimo_mes)

    # Saldo por banco (conta) ao fim do mês
    contas = list(ContaBancaria.objects.filter(empresa_id=empresa_id).select_related('banco'))
    saldos_por_banco = []
    for c in contas:
        saldos_por_banco.append(
            {
                'conta': c,
                'saldo': _saldo_conta_extrato_ate(c, empresa_id, ultimo_mes),
            }
        )
    saldos_por_banco.sort(key=lambda x: str(x['conta']))

    # Recebido no mês por sócio (baixas)
    baixas_mes = BaixaContaAReceber.objects.filter(
        empresa_id=empresa_id,
        data_recebimento__gte=primeiro_mes,
        data_recebimento__lte=ultimo_mes,
    ).select_related('conta_a_receber', 'conta_a_receber__socio')

    por_socio = defaultdict(lambda: Decimal('0'))
    for bx in baixas_mes:
        car = bx.conta_a_receber
        nome = str(car.socio) if car.socio_id else 'Sem sócio'
        por_socio[nome] += bx.valor_recebido or Decimal('0')
    saldos_por_socio = sorted(
        [{'socio': k, 'total': v} for k, v in por_socio.items()],
        key=lambda x: (-x['total'], x['socio']),
    )

    # Faturado / a receber / recebido (mês)
    valor_faturado_mes = (
        NotaFiscalServico.objects.filter(
            empresa_id=empresa_id,
            data_emissao__gte=primeiro_mes,
            data_emissao__lte=ultimo_mes,
            data_cancelamento__isnull=True,
        ).aggregate(s=Coalesce(Sum('valor_liquido'), Value(Decimal('0'))))['s']
        or Decimal('0')
    )
    valor_a_receber_mes = (
        ContaAReceber.objects.filter(
            empresa_id=empresa_id,
            data_emissao__gte=primeiro_mes,
            data_emissao__lte=ultimo_mes,
        ).aggregate(s=Coalesce(Sum('valor_a_receber'), Value(Decimal('0'))))['s']
        or Decimal('0')
    )
    valor_recebido_mes = (
        baixas_mes.aggregate(s=Coalesce(Sum('valor_recebido'), Value(Decimal('0'))))['s'] or Decimal('0')
    )

    # Forma de pagamento (mês) — recebimentos por cobrança na conta a receber
    fp_car = (
        ContaAReceber.objects.filter(
            empresa_id=empresa_id,
            data_recebimento__gte=primeiro_mes,
            data_recebimento__lte=ultimo_mes,
            forma_pagamento__isnull=False,
        )
        .values('forma_pagamento__descricao')
        .annotate(total=Coalesce(Sum('valor_recebido'), Value(Decimal('0'))))
        .order_by('-total')
    )
    fp_cap = (
        ContasaPagar.objects.filter(
            _cap_empresa_q(empresa_id),
            status='pago',
            dtPag__gte=primeiro_mes,
            dtPag__lte=ultimo_mes,
        )
        .values('cobranca__descricao')
        .annotate(total=Coalesce(Sum('valorPago'), Value(Decimal('0'))))
        .order_by('-total')
    )

    # Categorias — ano vigente
    ano_ini = date(hoje.year, 1, 1)
    ano_fim = date(hoje.year, 12, 31)
    valor_cap_expr = ExpressionWrapper(
        F('valorDoc') + F('juros') + F('multa') - F('desconto'),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    despesas_cat_ano = list(
        ContasaPagar.objects.filter(
            _cap_empresa_q(empresa_id),
            status='pago',
            dtPag__gte=ano_ini,
            dtPag__lte=ano_fim,
            categoria__isnull=False,
        )
        .values('categoria__nome', 'categoria__tipo')
        .annotate(total=Coalesce(Sum(valor_cap_expr), Value(Decimal('0'))))
        .order_by('-total')[:25]
    )
    receitas_cat_ano = list(
        ContaAReceber.objects.filter(
            empresa_id=empresa_id,
            status='pago',
            data_recebimento__gte=ano_ini,
            data_recebimento__lte=ano_fim,
            categoria__isnull=False,
        )
        .values('categoria__nome', 'categoria__tipo')
        .annotate(total=Coalesce(Sum('valor_recebido'), Value(Decimal('0'))))
        .order_by('-total')[:25]
    )

    # Tabela dia a dia no mês (extrato)
    saldo_cum = _saldo_extrato_empresa_ate(empresa_id, dia_antes_mes)
    tabela_dias = []
    for d in range(1, ultimo_mes.day + 1):
        dia = date(ano_ref, mes_ref, d)
        qs_d = Lancamento.objects.filter(empresa_id=empresa_id, data=dia)
        rec_d = qs_d.filter(valor__gt=0).aggregate(s=Coalesce(Sum('valor'), Value(Decimal('0'))))['s'] or Decimal('0')
        des_d_raw = (
            qs_d.filter(valor__lt=0).aggregate(s=Coalesce(Sum('valor'), Value(Decimal('0'))))['s'] or Decimal('0')
        )
        net_d = rec_d + des_d_raw
        saldo_cum += net_d
        tabela_dias.append(
            {
                'dia': dia,
                'dia_num': d,
                'receita': rec_d,
                'despesas': abs(des_d_raw),
                'saldo': saldo_cum,
            }
        )

    context = {
        'titulo': 'Dashboard',
        'titulo_mes': titulo_mes,
        'ano_ref': ano_ref,
        'mes_ref': mes_ref,
        'ano_vigente': hoje.year,
        'primeiro_mes': primeiro_mes,
        'ultimo_mes': ultimo_mes,
        'receita_mes': receita_mes,
        'despesa_mes': despesa_mes_abs,
        'pie_receita_chart_labels': json.dumps(pie_rec_labels, ensure_ascii=False),
        'pie_receita_chart_data': json.dumps(pie_rec_vals),
        'pie_despesa_chart_labels': json.dumps(pie_des_labels, ensure_ascii=False),
        'pie_despesa_chart_data': json.dumps(pie_des_vals),
        'pie_receita_has_data': bool(pie_rec_vals),
        'pie_despesa_has_data': bool(pie_des_vals),
        'saldo_fluxo_mes': saldo_fluxo_mes,
        'saldo_extrato_fim_mes': saldo_extrato_fim_mes,
        'saldos_por_banco': saldos_por_banco,
        'saldos_por_socio': saldos_por_socio,
        'valor_faturado_mes': valor_faturado_mes,
        'valor_a_receber_mes': valor_a_receber_mes,
        'valor_recebido_mes': valor_recebido_mes,
        'fp_car': fp_car,
        'fp_cap': fp_cap,
        'despesas_cat_ano': despesas_cat_ano,
        'receitas_cat_ano': receitas_cat_ano,
        'tabela_dias': tabela_dias,
    }
    return render(request, 'dashboard_inicio.html', context)


# Create your views here.
#@login_required(redirect_field_name='login')

def relatorio_mensal(request):
   titulo = 'Relatório Mensal'

   # Obter empresa da sessão
   empresa_id = request.session.get('empresa_id')
   if not empresa_id:
       return redirect('selecao_empresa')

   # Nomes dos meses em português
   meses_pt = ['', 'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
               'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro']

   # Últimos 12 meses
   hoje = datetime.now()
   current_month_start = hoje.replace(day=1)

   # Dados mensais
   dados_mensais = []

   for i in range(11, -1, -1):  # from 11 (oldest) to 0 (current)
       month_start = current_month_start - relativedelta(months=i)
       month_end = month_start + relativedelta(months=1)

       # Totais das notas fiscais do mês
       notas_mes = NotaFiscalServico.objects.filter(
           empresa_id=empresa_id,
           data_emissao__gte=month_start,
           data_emissao__lt=month_end
       )

       total_nota_bruta = notas_mes.aggregate(Sum('valor_bruto'))['valor_bruto__sum'] or 0
       total_nota_liquida = notas_mes.aggregate(Sum('valor_liquido'))['valor_liquido__sum'] or 0

       # Totais das contas a receber do mês
       contas_mes = ContaAReceber.objects.filter(
           empresa_id=empresa_id,
           data_emissao__gte=month_start,
           data_emissao__lt=month_end
       )

       total_contas_a_receber = contas_mes.aggregate(Sum('valor_a_receber'))['valor_a_receber__sum'] or 0
       total_recebido = contas_mes.aggregate(Sum('valor_recebido'))['valor_recebido__sum'] or 0

       # Cálculo do "meses"
       meses = total_nota_liquida  - total_recebido

       dados_mensais.append({
           'mes': month_start.strftime('%Y-%m'),
           'mes_nome': f"{meses_pt[month_start.month]} {month_start.year}",
           'total_nota_bruta': total_nota_bruta,
           'total_nota_liquida': total_nota_liquida,
           'total_contas_a_receber': total_contas_a_receber,
           'total_recebido': total_recebido,
           'meses': meses
       })

   # Dados para o gráfico
   chart_labels = [d['mes_nome'] for d in dados_mensais]
   chart_liquida = [float(d['total_nota_liquida']) for d in dados_mensais]
   chart_recebido = [float(d['total_recebido']) for d in dados_mensais]

   return render(request, 'relatorio_mensal.html', {
       'titulo': titulo,
       'dados_mensais': dados_mensais,
       'chart_labels': json.dumps(chart_labels),
       'chart_liquida': json.dumps(chart_liquida),
       'chart_recebido': json.dumps(chart_recebido)
   })


def _fmt_moeda_br(d):
    """Decimal → texto pt-BR (ex.: 1.234,56)."""
    if d is None:
        return '0,00'
    x = d if isinstance(d, Decimal) else Decimal(str(d))
    neg = x < 0
    a = abs(x).quantize(Decimal('0.01'))
    s = f'{a:.2f}'
    int_part, frac = s.split('.')
    chunks = []
    i = len(int_part)
    while i > 0:
        chunks.insert(0, int_part[max(0, i - 3) : i])
        i -= 3
    int_grp = '.'.join(chunks)
    out = f'{int_grp},{frac}'
    return ('-' if neg else '') + out


def _fmt_cnpj_br(raw):
    """CNPJ só dígitos → 00.000.000/0001-00."""
    if raw is None or raw == '':
        return ''
    d = ''.join(c for c in str(raw) if c.isdigit())
    if len(d) != 14:
        return str(raw).strip()
    return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}'


def _fmt_datas_unicas(dates_set):
    """Conjunto de date → 'dd/mm/aaaa, ...' ordenado (uso no resumo consolidado, se necessário)."""
    if not dates_set:
        return ''
    return ', '.join(d.strftime('%d/%m/%Y') for d in sorted(dates_set))


def resumo_fechamento(request):
    """
    Grade de faturamento por sócio no período (NFSe, competência = data de emissão).
    Coluna Simples Nacional: 0,00 (sem campo por nota no cadastro atual).
    """
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return redirect('selecao_empresa')

    empresa_ctx = Empresa.objects.filter(pk=empresa_id).first()
    empresa_razao_social = (empresa_ctx.razao or '').strip() if empresa_ctx else ''
    empresa_cnpj_fmt = _fmt_cnpj_br(empresa_ctx.cnpj) if empresa_ctx else ''

    meses_pt = [
        '',
        'Janeiro',
        'Fevereiro',
        'Março',
        'Abril',
        'Maio',
        'Junho',
        'Julho',
        'Agosto',
        'Setembro',
        'Outubro',
        'Novembro',
        'Dezembro',
    ]

    hoje = date.today()
    primeiro = date(hoje.year, hoje.month, 1)
    ultimo = date(hoje.year, hoje.month, monthrange(hoje.year, hoje.month)[1])

    di_str = (request.GET.get('data_inicio') or '').strip()
    df_str = (request.GET.get('data_fim') or '').strip()
    data_inicio = parse_date(di_str) if di_str else primeiro
    data_fim = parse_date(df_str) if df_str else ultimo
    if not data_inicio:
        data_inicio = primeiro
    if not data_fim:
        data_fim = ultimo
    if data_inicio > data_fim:
        data_inicio, data_fim = data_fim, data_inicio

    # Um ou mais IDs em ?socio=1&socio=2 (multiselect); vazio = todos os sócios
    filtro_socio_ids = []
    _seen_socio = set()
    for raw in request.GET.getlist('socio'):
        r = (raw or '').strip()
        if not r.isdigit():
            continue
        sid = int(r)
        if sid in _seen_socio:
            continue
        if Socio.objects.filter(pk=sid, empresa_id=empresa_id).exists():
            filtro_socio_ids.append(sid)
            _seen_socio.add(sid)

    socios = Socio.objects.filter(empresa_id=empresa_id).order_by('socio', 'lastname')

    if data_inicio.year == data_fim.year and data_inicio.month == data_fim.month:
        periodo_titulo = f'{meses_pt[data_inicio.month]} de {data_inicio.year}'
    else:
        periodo_titulo = (
            f'{data_inicio.strftime("%d/%m/%Y")} a {data_fim.strftime("%d/%m/%Y")}'
        )

    notas = (
        NotaFiscalServico.objects.filter(
            empresa_id=empresa_id,
            data_emissao__gte=data_inicio,
            data_emissao__lte=data_fim,
            data_cancelamento__isnull=True,
        )
        .select_related('socio')
        .order_by('socio_id', 'data_emissao')
    )
    if filtro_socio_ids:
        notas = notas.filter(socio_id__in=filtro_socio_ids)

    acc = defaultdict(
        lambda: {
            'socio_nome': '',
            'fat_bruto': Decimal('0'),
            'fat_liquido_nf': Decimal('0'),
            'pis': Decimal('0'),
            'cofins': Decimal('0'),
            'iss': Decimal('0'),
            'csll': Decimal('0'),
            'irpj': Decimal('0'),
            'irpj_ad': Decimal('0'),
            'simples': Decimal('0'),
        }
    )

    for n in notas:
        key = n.socio_id if n.socio_id is not None else 0
        row = acc[key]
        if not row['socio_nome']:
            row['socio_nome'] = str(n.socio) if n.socio else 'Sem sócio'
        row['fat_bruto'] += n.valor_bruto or Decimal('0')
        row['fat_liquido_nf'] += n.valor_liquido or Decimal('0')
        row['pis'] += n.pisapuracao or Decimal('0')
        row['cofins'] += n.cofinsapuracao or Decimal('0')
        row['iss'] += n.issapuracao or Decimal('0')
        row['csll'] += n.csllapuracao or Decimal('0')
        row['irpj'] += n.irpjapuracao or Decimal('0')
        row['irpj_ad'] += n.irpjadicional or Decimal('0')

    linhas = []
    tot = {
        'fat_bruto': Decimal('0'),
        'fat_liquido_nf': Decimal('0'),
        'imp_soma': Decimal('0'),
        'pis': Decimal('0'),
        'cofins': Decimal('0'),
        'iss': Decimal('0'),
        'csll': Decimal('0'),
        'irpj': Decimal('0'),
        'irpj_ad': Decimal('0'),
        'simples': Decimal('0'),
        'fat_liquido_final': Decimal('0'),
    }

    for _k, r in sorted(acc.items(), key=lambda x: x[1]['socio_nome'].lower()):
        imp = (
            r['pis']
            + r['cofins']
            + r['iss']
            + r['csll']
            + r['irpj']
            + r['irpj_ad']
            + r['simples']
        )
        liq_final = r['fat_bruto'] - imp
        linhas.append(
            {
                'socio_nome': r['socio_nome'],
                'fat_bruto_txt': _fmt_moeda_br(r['fat_bruto']),
                'fat_liquido_nf_txt': _fmt_moeda_br(r['fat_liquido_nf']),
                'imp_soma_txt': _fmt_moeda_br(imp),
                'pis_txt': _fmt_moeda_br(r['pis']),
                'cofins_txt': _fmt_moeda_br(r['cofins']),
                'iss_txt': _fmt_moeda_br(r['iss']),
                'csll_txt': _fmt_moeda_br(r['csll']),
                'irpj_txt': _fmt_moeda_br(r['irpj']),
                'irpj_ad_txt': _fmt_moeda_br(r['irpj_ad']),
                'simples_txt': _fmt_moeda_br(r['simples']),
                'fat_liquido_final_txt': _fmt_moeda_br(liq_final),
            }
        )
        tot['fat_bruto'] += r['fat_bruto']
        tot['fat_liquido_nf'] += r['fat_liquido_nf']
        tot['imp_soma'] += imp
        tot['pis'] += r['pis']
        tot['cofins'] += r['cofins']
        tot['iss'] += r['iss']
        tot['csll'] += r['csll']
        tot['irpj'] += r['irpj']
        tot['irpj_ad'] += r['irpj_ad']
        tot['simples'] += r['simples']
        tot['fat_liquido_final'] += liq_final

    totais_linha = {
        'fat_bruto_txt': _fmt_moeda_br(tot['fat_bruto']),
        'fat_liquido_nf_txt': _fmt_moeda_br(tot['fat_liquido_nf']),
        'imp_soma_txt': _fmt_moeda_br(tot['imp_soma']),
        'pis_txt': _fmt_moeda_br(tot['pis']),
        'cofins_txt': _fmt_moeda_br(tot['cofins']),
        'iss_txt': _fmt_moeda_br(tot['iss']),
        'csll_txt': _fmt_moeda_br(tot['csll']),
        'irpj_txt': _fmt_moeda_br(tot['irpj']),
        'irpj_ad_txt': _fmt_moeda_br(tot['irpj_ad']),
        'simples_txt': _fmt_moeda_br(tot['simples']),
        'fat_liquido_final_txt': _fmt_moeda_br(tot['fat_liquido_final']),
    }

    dec_ann = DecimalField(max_digits=18, decimal_places=2)
    zd = Value(0, output_field=dec_ann)

    def _norm_sid(v):
        return 0 if v is None else int(v)

    def _to_dec(x):
        if x is None:
            return Decimal('0')
        return x if isinstance(x, Decimal) else Decimal(str(x))

    def _map_car_agg(qs, field_name='nota__socio_id'):
        m = defaultdict(lambda: Decimal('0'))
        for row in qs:
            m[_norm_sid(row[field_name])] += _to_dec(row.get('t'))
        return m

    # Valor efetivamente recebido na baixa: alguns títulos ficam status pago/cartão com valor_recebido zerado.
    recebido_efetivo = Case(
        When(
            Q(status__in=['pago', 'cartao'])
            & (Q(valor_recebido__isnull=True) | Q(valor_recebido=0)),
            then=Coalesce(F('valor_a_receber'), zd),
        ),
        default=Coalesce(F('valor_recebido'), zd),
        output_field=dec_ann,
    )

    # Contas a receber da empresa. Parcela sem NF: sócio = «Sem sócio» (nota__socio_id nulo).
    car_soc = ContaAReceber.objects.filter(empresa_id=empresa_id)
    if filtro_socio_ids:
        contas_car_com_rateio_socio = (
            LancamentoRateio.objects.filter(
                empresa_id=empresa_id,
                tipo=LancamentoRateio.TIPO_RECEBIMENTO,
                socio_id__in=filtro_socio_ids,
                data_pagamento__gte=data_inicio,
                data_pagamento__lte=data_fim,
                conta_receber_id__isnull=False,
            )
            .values_list('conta_receber_id', flat=True)
            .distinct()
        )
        car_soc = car_soc.filter(
            Q(nota__socio_id__in=filtro_socio_ids) | Q(pk__in=contas_car_com_rateio_socio)
        )

    # Valor recebido (d): soma dos lançamentos de rateio RECEBIMENTO no período + parcelas
    # recebidas no período que não têm rateio nesse intervalo (evita duplicar).
    contas_com_rateio_rec_periodo = set(
        LancamentoRateio.objects.filter(
            empresa_id=empresa_id,
            tipo=LancamentoRateio.TIPO_RECEBIMENTO,
            data_pagamento__gte=data_inicio,
            data_pagamento__lte=data_fim,
            conta_receber_id__isnull=False,
        ).values_list('conta_receber_id', flat=True)
    )

    d_map = defaultdict(lambda: Decimal('0'))
    lr_rec_qs = LancamentoRateio.objects.filter(
        empresa_id=empresa_id,
        tipo=LancamentoRateio.TIPO_RECEBIMENTO,
        data_pagamento__gte=data_inicio,
        data_pagamento__lte=data_fim,
    )
    if filtro_socio_ids:
        lr_rec_qs = lr_rec_qs.filter(socio_id__in=filtro_socio_ids)
    for row in lr_rec_qs.values('socio_id').annotate(t=Sum(F('valor'))):
        d_map[_norm_sid(row['socio_id'])] += _to_dec(row.get('t'))

    q_car_sem_rateio_periodo = car_soc.filter(
        data_recebimento__gte=data_inicio,
        data_recebimento__lte=data_fim,
        data_recebimento__isnull=False,
    ).exclude(status='cancelado').exclude(pk__in=contas_com_rateio_rec_periodo)

    for row in q_car_sem_rateio_periodo.values('nota__socio_id').annotate(
        t=Sum(recebido_efetivo)
    ):
        d_map[_norm_sid(row['nota__socio_id'])] += _to_dec(row.get('t'))

    qe = car_soc.filter(
        data_emissao__gte=data_inicio,
        data_emissao__lte=data_fim,
        status__in=['pendente', 'vencido'],
    )
    e_map = _map_car_agg(
        qe.values('nota__socio_id').annotate(
            t=Sum(
                F('valor_a_receber') - Coalesce(F('valor_recebido'), zd),
                output_field=dec_ann,
            )
        )
    )

    qf = car_soc.filter(
        nota_id__isnull=False,
        data_recebimento__gte=data_inicio,
        data_recebimento__lte=data_fim,
        data_recebimento__isnull=False,
        nota__data_emissao__lt=data_inicio,
    ).exclude(status='cancelado')
    f_map = _map_car_agg(
        qf.values('nota__socio_id').annotate(t=Sum(recebido_efetivo))
    )

    # Rec. caixa (j): soma dos valores recebidos nas baixas cuja conta de destino é tipo Caixa
    # (valor recebido + juros + tarifas − desconto), por sócio da NF do título.
    dec_bx = DecimalField(max_digits=18, decimal_places=2)
    valor_efetivo_baixa_caixa = (
        Coalesce(F('valor_recebido'), Value(0), output_field=dec_bx)
        + Coalesce(F('juros'), Value(0), output_field=dec_bx)
        + Coalesce(F('tarifas'), Value(0), output_field=dec_bx)
        - Coalesce(F('desconto'), Value(0), output_field=dec_bx)
    )
    j_map = defaultdict(lambda: Decimal('0'))
    for row in (
        BaixaContaAReceber.objects.filter(
            empresa_id=empresa_id,
            data_recebimento__gte=data_inicio,
            data_recebimento__lte=data_fim,
            conta_banco__tipo='CAIXA',
            conta_a_receber__in=car_soc,
        )
        .exclude(conta_a_receber__status='cancelado')
        .values('conta_a_receber__nota__socio_id')
        .annotate(t=Sum(valor_efetivo_baixa_caixa))
    ):
        j_map[_norm_sid(row['conta_a_receber__nota__socio_id'])] += _to_dec(row.get('t'))

    # Rateio PGTO: despesas (não dist. lucro) pelo período da data de pagamento do lançamento;
    # distribuição de lucro (L) pelo período da data de emissão do título (CAP).
    rateio_pg_nao_l = LancamentoRateio.objects.filter(
        empresa_id=empresa_id,
        tipo=LancamentoRateio.TIPO_PGTO,
        data_pagamento__gte=data_inicio,
        data_pagamento__lte=data_fim,
    ).exclude(conta_pagar__categoria__tipo='L')
    rateio_pg_dist = LancamentoRateio.objects.filter(
        empresa_id=empresa_id,
        tipo=LancamentoRateio.TIPO_PGTO,
        conta_pagar__categoria__tipo='L',
        conta_pagar__dtEmissao__gte=data_inicio,
        conta_pagar__dtEmissao__lte=data_fim,
        conta_pagar__dtEmissao__isnull=False,
    )
    if filtro_socio_ids:
        rateio_pg_nao_l = rateio_pg_nao_l.filter(socio_id__in=filtro_socio_ids)
        rateio_pg_dist = rateio_pg_dist.filter(socio_id__in=filtro_socio_ids)

    i_map = defaultdict(lambda: Decimal('0'))
    for row in rateio_pg_nao_l.values('socio_id').annotate(t=Sum(F('valor'))):
        sid = _norm_sid(row['socio_id'])
        i_map[sid] += -_to_dec(row.get('t'))

    l_map = defaultdict(lambda: Decimal('0'))
    for row in rateio_pg_dist.values('socio_id').annotate(t=Sum(F('valor'))):
        sid = _norm_sid(row['socio_id'])
        l_map[sid] += -_to_dec(row.get('t'))

    acc_nf = {}
    for k_acc, r_acc in acc.items():
        imp = (
            r_acc['pis']
            + r_acc['cofins']
            + r_acc['iss']
            + r_acc['csll']
            + r_acc['irpj']
            + r_acc['irpj_ad']
            + r_acc['simples']
        )
        acc_nf[k_acc] = {
            'nome': r_acc['socio_nome'],
            'fat_bruto': r_acc['fat_bruto'],
            'fat_liquido_nf': r_acc['fat_liquido_nf'],
            'imposto': imp,
        }

    chaves_resumo = (
        set(acc_nf.keys())
        | set(d_map.keys())
        | set(e_map.keys())
        | set(f_map.keys())
        | set(j_map.keys())
        | set(i_map.keys())
        | set(l_map.keys())
    )
    socio_nomes = {0: 'Sem sócio'}
    for s in socios:
        socio_nomes[s.id] = str(s)

    if filtro_socio_ids:
        ordem_ids = list(filtro_socio_ids)
    else:
        ordem_ids = [s.id for s in socios]
        for k in sorted(chaves_resumo):
            if k == 0 or k in ordem_ids:
                continue
            ordem_ids.append(k)
        if 0 in chaves_resumo:
            ordem_ids.append(0)
    if not ordem_ids:
        ordem_ids = sorted(x for x in chaves_resumo if x != 0) + ([0] if 0 in chaves_resumo else [])

    resumo_consolidado_linhas = []
    tot_cons = {
        'b': Decimal('0'),
        'c': Decimal('0'),
        'd': Decimal('0'),
        'e': Decimal('0'),
        'f': Decimal('0'),
        'g': Decimal('0'),
        'h': Decimal('0'),
        'i': Decimal('0'),
        'j': Decimal('0'),
        'l': Decimal('0'),
        'k': Decimal('0'),
    }

    for sid in ordem_ids:
        if sid in acc_nf:
            ar = acc_nf[sid]
            nome = ar['nome']
            b = ar['fat_bruto']
            c = ar['fat_liquido_nf']
            h = ar['imposto']
        else:
            nome = socio_nomes.get(sid, f'Sócio #{sid}')
            b = c = h = Decimal('0')
        d = d_map[sid]
        e = e_map[sid]
        f_ant = f_map[sid]
        g = d + f_ant
        i_desp = i_map[sid]
        j_caixa = j_map[sid]
        l_dist = l_map[sid]
        k_saldo = g - h - i_desp - j_caixa - l_dist

        resumo_consolidado_linhas.append(
            {
                'socio_id': sid,
                'k_val': k_saldo,
                'socio_nome': nome,
                'b_txt': _fmt_moeda_br(b),
                'c_txt': _fmt_moeda_br(c),
                'd_txt': _fmt_moeda_br(d),
                'e_txt': _fmt_moeda_br(e),
                'f_txt': _fmt_moeda_br(f_ant),
                'g_txt': _fmt_moeda_br(g),
                'h_txt': _fmt_moeda_br(h),
                'i_txt': _fmt_moeda_br(i_desp),
                'j_txt': _fmt_moeda_br(j_caixa),
                'l_txt': _fmt_moeda_br(l_dist),
                'k_txt': _fmt_moeda_br(k_saldo),
                'k_negativo': k_saldo < 0,
            }
        )
        tot_cons['b'] += b
        tot_cons['c'] += c
        tot_cons['d'] += d
        tot_cons['e'] += e
        tot_cons['f'] += f_ant
        tot_cons['g'] += g
        tot_cons['h'] += h
        tot_cons['i'] += i_desp
        tot_cons['j'] += j_caixa
        tot_cons['l'] += l_dist
        tot_cons['k'] += k_saldo

    totais_consolidado = {key: _fmt_moeda_br(val) for key, val in tot_cons.items()}
    totais_consolidado['k_negativo'] = tot_cons['k'] < 0

    def _parse_pl_get(get_dict, key):
        s = (get_dict.get(key) or '').strip().replace(' ', '').replace(',', '.')
        if not s:
            return Decimal('0')
        try:
            return Decimal(s)
        except Exception:
            return Decimal('0')

    def _fmt_input_moeda_br(d):
        x = d if isinstance(d, Decimal) else Decimal(str(d))
        neg = x < 0
        a = abs(x).quantize(Decimal('0.01'))
        s = f'{a:.2f}'.replace('.', ',')
        return ('-' if neg else '') + s

    grade_prolabore_linhas = []
    tot_prolabore = Decimal('0')
    for row in resumo_consolidado_linhas:
        sid = row['socio_id']
        k = row['k_val']
        pl = _parse_pl_get(request.GET, f'pl_{sid}')
        div = k - pl
        tot_prolabore += pl
        grade_prolabore_linhas.append(
            {
                'socio_id': sid,
                'socio_nome': row['socio_nome'],
                'saldo_txt': row['k_txt'],
                'saldo_negativo': row['k_negativo'],
                'pl_name': f'pl_{sid}',
                'pl_value': _fmt_input_moeda_br(pl),
                'dividendo_txt': _fmt_moeda_br(div),
                'dividendo_negativo': div < 0,
            }
        )
    tot_dividendo = tot_cons['k'] - tot_prolabore
    totais_prolabore = {
        'saldo_txt': _fmt_moeda_br(tot_cons['k']),
        'prolabore_txt': _fmt_moeda_br(tot_prolabore),
        'dividendo_txt': _fmt_moeda_br(tot_dividendo),
        'dividendo_negativo': tot_dividendo < 0,
    }

    def _grade_rateio_por_queryset(qs):
        out = []
        soma = Decimal('0')
        for lr in qs:
            v = lr.valor if lr.valor is not None else Decimal('0')
            soma += v
            if lr.conta_receber_id and lr.conta_receber.nota_id:
                nota_txt = lr.conta_receber.nota.numero_nota
            else:
                nota_txt = '—'
            if lr.conta_pagar_id:
                vt = lr.conta_pagar.valorDoc
            elif lr.conta_receber_id:
                vt = lr.conta_receber.valor_a_receber
            else:
                vt = Decimal('0')
            if vt is None:
                vt = Decimal('0')
            if lr.conta_pagar_id and lr.conta_pagar:
                cap = lr.conta_pagar
                emissao = cap.dtEmissao
                emissao_txt = emissao.strftime('%d/%m/%Y') if emissao else '—'
                # Data de pagamento na grade = do título (CAP.dtPag) quando houver; senão o lançamento de rateio
                pgto_ref = cap.dtPag or lr.data_pagamento
                data_txt = (
                    pgto_ref.strftime('%d/%m/%Y') if pgto_ref else '—'
                )
            else:
                emissao_txt = '—'
                data_txt = (
                    lr.data_pagamento.strftime('%d/%m/%Y')
                    if lr.data_pagamento
                    else '—'
                )
            out.append(
                {
                    'data_txt': data_txt,
                    'emissao_txt': emissao_txt,
                    'nota_txt': nota_txt,
                    'titulo_valor_txt': _fmt_moeda_br(vt),
                    'descricao': (lr.descricao or '').strip() or '—',
                    'socio_nome': str(lr.socio) if lr.socio_id else '—',
                    'valor_txt': _fmt_moeda_br(v),
                    'valor_negativo': v < 0,
                }
            )
        return out, soma

    rateio_related = (
        'socio',
        'conta_pagar',
        'conta_pagar__categoria',
        'conta_receber',
        'conta_receber__nota',
    )
    q_pgto_periodo = (
        Q(
            data_pagamento__gte=data_inicio,
            data_pagamento__lte=data_fim,
        )
        & ~Q(conta_pagar__categoria__tipo='L')
    ) | Q(
        conta_pagar__categoria__tipo='L',
        conta_pagar__dtEmissao__gte=data_inicio,
        conta_pagar__dtEmissao__lte=data_fim,
        conta_pagar__dtEmissao__isnull=False,
    )
    qs_pg = (
        LancamentoRateio.objects.filter(
            empresa_id=empresa_id,
            tipo=LancamentoRateio.TIPO_PGTO,
        )
        .filter(q_pgto_periodo)
        .select_related(*rateio_related)
        .distinct()
        .order_by('-data_pagamento', '-id')
    )
    if filtro_socio_ids:
        qs_pg = qs_pg.filter(socio_id__in=filtro_socio_ids)
    grade_rateio_pagamento, total_rateio_pg = _grade_rateio_por_queryset(qs_pg)

    filtro_socio_nome = None
    if filtro_socio_ids:
        id_to_str = {
            s.id: str(s)
            for s in Socio.objects.filter(pk__in=filtro_socio_ids, empresa_id=empresa_id)
        }
        filtro_socio_nome = ', '.join(
            id_to_str[i] for i in filtro_socio_ids if i in id_to_str
        )

    def _dt_iso_br(val):
        if not val:
            return '—'
        try:
            return datetime.fromisoformat(str(val)[:10]).strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            return '—'

    _cand_cap = query_contas_pagar_sem_lancamento_rateio_resumo(
        empresa_id,
        data_inicio,
        data_fim,
        socio_ids=filtro_socio_ids if filtro_socio_ids else None,
    )
    _rows_cap = []
    for r in _cand_cap:
        vb = Decimal(str(r['valor_base']))
        _rows_cap.append(
            (
                r.get('dt_pag') or '',
                {
                    'id_titulo': r['id'],
                    'emissao_txt': _dt_iso_br(r.get('dt_emissao')),
                    'data_txt': _dt_iso_br(r.get('dt_pag')),
                    'contraparte': r.get('fornecedor') or '—',
                    'descricao': (r.get('descricao') or '')[:200],
                    'valor_txt': _fmt_moeda_br(vb),
                    'regra': r.get('regra') or '—',
                    'motivo': r.get('rotulo_status') or '—',
                },
            )
        )
    _rows_cap.sort(key=lambda t: t[0], reverse=True)
    pagamentos_sem_rateio_pagar = [t[1] for t in _rows_cap]

    # Contas a receber recebidas no período (mesmo filtro de sócio que car_soc + datas do formulário)
    def _valor_recebido_linha_cr(c):
        """Valor efetivo: soma das baixas com data no período; senão campo na parcela; senão face para pago/cartão zerado."""
        soma_bx = Decimal('0')
        for bx in c.baixas.all():
            if bx.data_recebimento and data_inicio <= bx.data_recebimento <= data_fim:
                soma_bx += (bx.valor_recebido or Decimal('0')) + (bx.juros or Decimal('0')) + (bx.tarifas or Decimal('0')) - (bx.desconto or Decimal('0'))
        if soma_bx != 0:
            return soma_bx
        vpar = c.valor_recebido if c.valor_recebido is not None else Decimal('0')
        if vpar != 0:
            return vpar
        if c.status in ('pago', 'cartao') and (c.valor_recebido is None or c.valor_recebido == 0):
            return c.valor_a_receber or Decimal('0')
        return Decimal('0')

    q_cr_periodo = (
        car_soc.filter(
            data_recebimento__gte=data_inicio,
            data_recebimento__lte=data_fim,
            data_recebimento__isnull=False,
        )
        .exclude(status='cancelado')
        .select_related('nota', 'nota__socio', 'socio')
        .prefetch_related('baixas')
        .order_by('-data_recebimento', '-id')
    )
    contas_recebidas_periodo = []
    soma_cr_valor = Decimal('0')
    for c in q_cr_periodo:
        vr = _valor_recebido_linha_cr(c)
        soma_cr_valor += vr
        if c.socio_id:
            st = str(c.socio)
        elif c.nota_id and getattr(c.nota, 'socio_id', None):
            st = str(c.nota.socio)
        else:
            st = '—'
        contas_recebidas_periodo.append(
            {
                'id': c.pk,
                'cliente': (c.cliente or '—')[:120],
                'emissao_txt': c.data_emissao.strftime('%d/%m/%Y') if c.data_emissao else '—',
                'recebimento_txt': c.data_recebimento.strftime('%d/%m/%Y') if c.data_recebimento else '—',
                'nota_txt': c.nota.numero_nota if c.nota_id else '—',
                'socio_txt': st,
                'parcela': c.parcela or '—',
                'doc': ((c.doc or '')[:60] or '—'),
                'valor_txt': _fmt_moeda_br(vr),
            }
        )

    return render(
        request,
        'resumo_fechamento.html',
        {
            'titulo': 'Resumo fechamento',
            'empresa_razao_social': empresa_razao_social,
            'empresa_cnpj_fmt': empresa_cnpj_fmt,
            'periodo_titulo': periodo_titulo,
            'data_inicio': data_inicio.isoformat(),
            'data_fim': data_fim.isoformat(),
            'socios': socios,
            'filtro_socio_ids': filtro_socio_ids,
            'filtro_socio_nome': filtro_socio_nome,
            'grade_linhas': linhas,
            'totais_linha': totais_linha,
            'tem_linhas': bool(linhas),
            'grade_rateio_pagamento': grade_rateio_pagamento,
            'tem_grade_rateio_pg': bool(grade_rateio_pagamento),
            'rateio_pg_total_txt': _fmt_moeda_br(total_rateio_pg),
            'resumo_consolidado_linhas': resumo_consolidado_linhas,
            'totais_consolidado': totais_consolidado,
            'tem_resumo_consolidado': bool(resumo_consolidado_linhas),
            'grade_prolabore_linhas': grade_prolabore_linhas,
            'tem_grade_prolabore': bool(grade_prolabore_linhas),
            'totais_prolabore': totais_prolabore,
            'pagamentos_sem_rateio_pagar': pagamentos_sem_rateio_pagar,
            'tem_sem_rateio_pagar': bool(pagamentos_sem_rateio_pagar),
            'contas_recebidas_periodo': contas_recebidas_periodo,
            'tem_contas_recebidas_periodo': bool(contas_recebidas_periodo),
            'contas_recebidas_total_txt': _fmt_moeda_br(soma_cr_valor),
        },
    )