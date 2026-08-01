"""Resumo Conta Azul para o dashboard."""

from __future__ import annotations

import json
import re
from datetime import date
from decimal import Decimal

from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.db.models.functions import Coalesce

from categoria.models import Categoria, CentroCusto
from cliente.models import Cliente
from contasapagar.models import ContasaPagar
from contasareceber.models import ContaAReceber
from dashboard.conta_azul.config import config_da_empresa
from extrato.models import ContaBancaria, ExtratoMovimento, Lancamento


def _cliente_exibicao(empresa, valor_cliente: str) -> str:
    nome = (valor_cliente or '').strip()
    if not nome:
        return '—'
    if nome.startswith("{'") or nome.startswith('{"'):
        m = re.search(r"['\"]id['\"]\s*:\s*['\"]([^'\"]+)", nome)
        if m:
            cli = Cliente.objects.filter(empresa=empresa, conta_azul_id=m.group(1)).first()
            if cli:
                return cli.razao
        return '—'
    return nome


def _annotate_conciliado_receber(qs):
    mov_conc = ExtratoMovimento.objects.filter(
        lancamento__isnull=False,
        lancamento__conciliado=True,
    ).filter(
        Q(conta_receber_id=OuterRef('pk'))
        | Q(baixa_receber__conta_a_receber_id=OuterRef('pk'))
    )
    return qs.annotate(conciliado_extrato=Exists(mov_conc))


def _annotate_conciliado_pagar(qs):
    mov_conc = ExtratoMovimento.objects.filter(
        conta_pagar_id=OuterRef('pk'),
        lancamento__isnull=False,
        lancamento__conciliado=True,
    )
    return qs.annotate(conciliado_extrato=Exists(mov_conc))


def _conciliacao_linha(*, status: str, conciliado_extrato: bool, baixado_ca: bool) -> dict:
    if conciliado_extrato:
        return {
            'conciliado': True,
            'conciliado_rotulo': 'Sim',
            'conciliado_classe': 'success',
            'conciliado_titulo': 'Conciliado com extrato bancário',
        }
    if baixado_ca or status == 'pago':
        return {
            'conciliado': True,
            'conciliado_rotulo': 'CA',
            'conciliado_classe': 'info text-dark',
            'conciliado_titulo': 'Recebido/pago/baixado no Conta Azul (status ACQUITTED ou quitado)',
        }
    return {
        'conciliado': False,
        'conciliado_rotulo': 'Não',
        'conciliado_classe': 'secondary',
        'conciliado_titulo': 'Pendente / não conciliado',
    }


def montar_resumo_conta_azul(empresa, data_inicio: date, data_fim: date) -> dict:
    cfg = config_da_empresa(empresa)
    conectado = bool(cfg and cfg.tem_refresh_token())
    credenciais_ok = bool(cfg and cfg.credenciais_preenchidas())

    resumo = {
        'conectado': conectado,
        'credenciais_ok': credenciais_ok,
        'token_valido': bool(cfg and cfg.token_valido()),
        'ultima_sync': cfg.atualizado_em if cfg else None,
        'config_url': f'/empresa/{empresa.pk}/conta-azul/' if empresa.pk else '',
        'sync_completa_url': f'/empresa/{empresa.pk}/conta-azul/sincronizar/' if empresa.pk else '',
        'ambiente': cfg.ambiente if cfg else '',
        'empresa_nome': empresa.razao if empresa else '',
        'totais': {
            'receitas': Decimal('0'),
            'despesas': Decimal('0'),
            'transferencias': Decimal('0'),
            'saldo_contas_ca': Decimal('0'),
        },
        'contagens': {
            'categorias': Categoria.objects.filter(empresa=empresa).exclude(conta_azul_id='').count(),
            'centros_custo': CentroCusto.objects.filter(empresa=empresa).count(),
            'contas': ContaBancaria.objects.filter(empresa=empresa).exclude(conta_azul_id='').count(),
        },
        'receitas': [],
        'despesas': [],
        'transferencias': [],
        'categorias': list(
            Categoria.objects.filter(empresa=empresa)
            .exclude(conta_azul_id='')
            .order_by('nome')[:20]
            .values('nome', 'tipo', 'conta_azul_id')
        ),
        'centros_custo': list(
            CentroCusto.objects.filter(empresa=empresa).order_by('nome')[:20].values('nome', 'ativo')
        ),
        'contas_display': [],
        'chart_categorias_labels': '[]',
        'chart_categorias_data': '[]',
        'erro': None,
    }

    if not conectado:
        return resumo

    qs_rec = ContaAReceber.objects.filter(
        empresa=empresa,
        data_vencimento__gte=data_inicio,
        data_vencimento__lte=data_fim,
    ).exclude(conta_azul_parcela_id='')
    qs_desp = ContasaPagar.objects.filter(
        empresa=empresa,
        dtvenc__gte=data_inicio,
        dtvenc__lte=data_fim,
    ).exclude(conta_azul_parcela_id='')
    qs_trans = Lancamento.objects.filter(
        empresa=empresa,
        origem='CONTA_AZUL',
        data__gte=data_inicio,
        data__lte=data_fim,
    )

    resumo['totais']['receitas'] = qs_rec.aggregate(
        t=Coalesce(Sum('valor_a_receber'), Decimal('0')),
    )['t'] or Decimal('0')
    resumo['totais']['despesas'] = qs_desp.aggregate(
        t=Coalesce(Sum('valorDoc'), Decimal('0')),
    )['t'] or Decimal('0')
    resumo['totais']['transferencias'] = abs(
        qs_trans.aggregate(t=Coalesce(Sum('valor'), Decimal('0')))['t'] or Decimal('0')
    )

    receitas_raw = list(
        _annotate_conciliado_receber(
            qs_rec.select_related('categoria', 'conta_banco', 'forma_pagamento')
        )
        .order_by('-data_vencimento')[:25]
        .values(
            'data_vencimento', 'cliente', 'valor_a_receber', 'status',
            'categoria__nome', 'conta_azul_parcela_id', 'observacao',
            'conta_banco__descricao', 'forma_pagamento__descricao',
            'data_recebimento', 'valor_recebido', 'conciliado_extrato',
        )
    )
    for row in receitas_raw:
        row['cliente'] = _cliente_exibicao(empresa, row.get('cliente') or '')
        baixado_ca = (
            row.get('status') == 'pago'
            or bool(row.get('data_recebimento'))
            or (row.get('valor_recebido') or Decimal('0')) > Decimal('0')
        )
        row.update(
            _conciliacao_linha(
                status=row.get('status') or '',
                conciliado_extrato=bool(row.get('conciliado_extrato')),
                baixado_ca=baixado_ca,
            )
        )
    resumo['receitas'] = receitas_raw
    despesas_raw = list(
        _annotate_conciliado_pagar(
            qs_desp.select_related('categoria', 'fornecedor', 'conta_banco', 'cobranca')
        )
        .order_by('-dtvenc')[:25]
        .values(
            'dtvenc', 'descricao', 'valorDoc', 'fornecedor__razao', 'status',
            'categoria__nome', 'conta_azul_parcela_id',
            'conta_banco__descricao', 'cobranca__descricao',
            'dtPag', 'valorPago', 'conciliado_extrato',
        )
    )
    for row in despesas_raw:
        baixado_ca = bool(row.get('dtPag')) or (row.get('valorPago') or Decimal('0')) > Decimal('0')
        row.update(
            _conciliacao_linha(
                status=row.get('status') or ('pago' if baixado_ca else 'pendente'),
                conciliado_extrato=bool(row.get('conciliado_extrato')),
                baixado_ca=baixado_ca,
            )
        )
    resumo['despesas'] = despesas_raw
    resumo['transferencias'] = list(
        qs_trans.select_related('conta')
        .order_by('-data')[:15]
        .values('data', 'historico', 'valor', 'conta__descricao')
    )

    por_cat = (
        qs_rec.filter(categoria__isnull=False)
        .values('categoria__nome')
        .annotate(total=Coalesce(Sum('valor_a_receber'), Decimal('0')))
        .order_by('-total')[:10]
    )
    labels = [r['categoria__nome'] or '—' for r in por_cat]
    vals = [float(r['total']) for r in por_cat]
    resumo['chart_categorias_labels'] = json.dumps(labels, ensure_ascii=False)
    resumo['chart_categorias_data'] = json.dumps(vals)

    contas_qs = (
        ContaBancaria.objects.filter(empresa=empresa)
        .exclude(conta_azul_id='')
        .select_related('banco')
        .order_by('descricao')[:20]
    )
    total_saldo_ca = Decimal('0')
    contas_display = []
    for c in contas_qs:
        saldo = c.saldo_conta_azul
        if saldo is not None:
            total_saldo_ca += saldo
        contas_display.append(
            {
                'nome': c.descricao or str(c),
                'banco': str(c.banco),
                'ativo': c.status == 'A',
                'saldo': saldo,
                'saldo_em': c.saldo_conta_azul_em,
            }
        )
    resumo['contas_display'] = contas_display
    resumo['totais']['saldo_contas_ca'] = total_saldo_ca

    return resumo
