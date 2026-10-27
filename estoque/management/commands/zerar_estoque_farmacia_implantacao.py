"""
Zera saldos e apaga histórico operacional da farmácia (consumíveis) para implantar inventário.

Não remove cadastro de produtos nem imobilizado.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from empresa.models import Empresa
from estoque.models import (
    EntradaEstoqueNota,
    MovimentoEstoque,
    NaturezaEstoque,
    ProdutoEstoque,
    RequisicaoEstoque,
    SaldoEstoqueSetor,
)

CONFIRM_TOKEN = 'ZERAR_FARMACIA'


def _escopo_consumivel(empresa_id: int):
    return ProdutoEstoque.objects.filter(
        empresa_id=empresa_id,
        natureza=NaturezaEstoque.CONSUMIVEL,
    )


def _contagens(empresa_id: int) -> dict[str, int]:
    produtos = _escopo_consumivel(empresa_id)
    pks = list(produtos.values_list('pk', flat=True))
    if not pks:
        return {
            'produtos': 0,
            'com_saldo': 0,
            'movimentos': 0,
            'entradas_nf': 0,
            'requisicoes': 0,
            'saldos_setor': 0,
        }

    com_saldo = produtos.filter(
        Q(quantidade_estoque__gt=0) | Q(quantidade_estoque_contabil__gt=0),
    ).count()

    reqs = (
        RequisicaoEstoque.objects.filter(empresa_id=empresa_id)
        .exclude(itens__produto__natureza=NaturezaEstoque.IMOBILIZADO)
        .distinct()
    )

    saldos_setor = SaldoEstoqueSetor.objects.filter(produto_id__in=pks).exclude(quantidade=0).count()

    return {
        'produtos': len(pks),
        'com_saldo': com_saldo,
        'movimentos': MovimentoEstoque.objects.filter(
            empresa_id=empresa_id,
            produto_id__in=pks,
        ).count(),
        'entradas_nf': EntradaEstoqueNota.objects.filter(produto_id__in=pks).count(),
        'requisicoes': reqs.count(),
        'saldos_setor': saldos_setor,
    }


@transaction.atomic
def executar_zeragem_farmacia(empresa_id: int, *, limpar_inventarios: bool) -> dict[str, int]:
    produtos = _escopo_consumivel(empresa_id)
    pks = list(produtos.values_list('pk', flat=True))
    if not pks:
        return {'produtos_zerados': 0}

    reqs = (
        RequisicaoEstoque.objects.filter(empresa_id=empresa_id)
        .exclude(itens__produto__natureza=NaturezaEstoque.IMOBILIZADO)
        .distinct()
    )
    n_req = reqs.count()
    reqs.delete()

    n_ent = EntradaEstoqueNota.objects.filter(produto_id__in=pks).count()
    EntradaEstoqueNota.objects.filter(produto_id__in=pks).delete()

    n_mov = MovimentoEstoque.objects.filter(empresa_id=empresa_id, produto_id__in=pks).count()
    MovimentoEstoque.objects.filter(empresa_id=empresa_id, produto_id__in=pks).delete()

    n_saldos = SaldoEstoqueSetor.objects.filter(produto_id__in=pks).update(quantidade=Decimal('0'))

    n_prod = produtos.update(
        quantidade_estoque=Decimal('0'),
        quantidade_estoque_contabil=Decimal('0'),
    )

    n_inv = 0
    if limpar_inventarios:
        from inventario.models import Inventario

        inv_qs = Inventario.objects.filter(empresa_id=empresa_id)
        n_inv = inv_qs.count()
        inv_qs.delete()

    return {
        'requisicoes_apagadas': n_req,
        'entradas_nf_apagadas': n_ent,
        'movimentos_apagados': n_mov,
        'saldos_setor_zerados': n_saldos,
        'produtos_zerados': n_prod,
        'inventarios_apagados': n_inv,
    }


class Command(BaseCommand):
    help = (
        'Apaga movimentos, requisições e vínculos NF→estoque dos consumíveis (farmácia) '
        'e zera quantidades. Cadastro de produtos permanece. Imobilizado não é alterado. '
        'Use --dry-run e depois --confirm ZERAR_FARMACIA. No Render: Shell → python manage.py ...'
    )

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, required=True, help='ID da empresa.')
        parser.add_argument(
            '--limpar-inventarios',
            action='store_true',
            help='Remove inventários (contagens/backups) desta empresa.',
        )
        parser.add_argument('--dry-run', action='store_true', help='Mostra contagens sem alterar.')
        parser.add_argument(
            '--confirm',
            type=str,
            help=f'Texto exato "{CONFIRM_TOKEN}" para executar.',
        )

    def handle(self, *args, **options):
        empresa_id = options['empresa_id']
        if not Empresa.objects.filter(pk=empresa_id).exists():
            raise CommandError(f'Empresa {empresa_id} não encontrada.')

        empresa = Empresa.objects.get(pk=empresa_id)
        stats = _contagens(empresa_id)

        self.stdout.write(f'Empresa: {empresa} (id={empresa_id})')
        self.stdout.write(f'  Produtos consumíveis: {stats["produtos"]}')
        self.stdout.write(f'  Com saldo > 0: {stats["com_saldo"]}')
        self.stdout.write(f'  Movimentos: {stats["movimentos"]}')
        self.stdout.write(f'  Entradas NF (estoque): {stats["entradas_nf"]}')
        self.stdout.write(f'  Requisições (sem imobilizado): {stats["requisicoes"]}')
        self.stdout.write(f'  Saldos em setor ≠ 0: {stats["saldos_setor"]}')
        if options['limpar_inventarios']:
            from inventario.models import Inventario

            n = Inventario.objects.filter(empresa_id=empresa_id).count()
            self.stdout.write(f'  Inventários a apagar: {n}')

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry-run — nada foi alterado.'))
            return

        if options.get('confirm') != CONFIRM_TOKEN:
            raise CommandError(
                f'Confirmação obrigatória: --confirm {CONFIRM_TOKEN} '
                f'(recomendado rodar --dry-run antes).',
            )

        resultado = executar_zeragem_farmacia(
            empresa_id,
            limpar_inventarios=options['limpar_inventarios'],
        )
        self.stdout.write(self.style.SUCCESS('Concluído:'))
        for chave, val in resultado.items():
            self.stdout.write(f'  {chave}: {val}')
