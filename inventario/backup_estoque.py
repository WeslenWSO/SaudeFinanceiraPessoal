"""Backup e restauração lógica do estoque ligados ao inventário."""
from __future__ import annotations

from io import BytesIO

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from openpyxl import Workbook

from estoque.models import ProdutoEstoque
from inventario.models import EstoqueBackup, EstoqueBackupLinha, Inventario, InventarioItem


def criar_backup_estoque(
    inventario: Inventario,
    usuario: User | None = None,
    *,
    descricao: str = '',
) -> EstoqueBackup:
    produtos = ProdutoEstoque.objects.filter(empresa_id=inventario.empresa_id).order_by(
        'codigo_produto',
    )
    backup = EstoqueBackup.objects.create(
        inventario=inventario,
        empresa_id=inventario.empresa_id,
        descricao=descricao or f'Backup — {inventario.descricao}',
        criado_por=usuario,
    )
    linhas = [
        EstoqueBackupLinha(
            backup=backup,
            produto=p,
            codigo_produto=p.codigo_produto,
            descricao=p.descricao,
            marca=p.marca,
            quantidade_estoque=p.quantidade_estoque,
            quantidade_estoque_contabil=p.quantidade_estoque_contabil,
            valor_ultima_compra=p.valor_ultima_compra,
            valor_custo_medio=p.valor_custo_medio,
            valor_custo_contabil=p.valor_custo_contabil,
        )
        for p in produtos
    ]
    if linhas:
        EstoqueBackupLinha.objects.bulk_create(linhas)
    return backup


def backup_para_excel(backup: EstoqueBackup) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Estoque backup'
    ws.append(
        [
            'Código',
            'Descrição',
            'Marca',
            'Qtd. estoque',
            'Est. contábil',
            'Últ. compra',
            'Custo médio',
            'Custo contábil',
        ],
    )
    for ln in backup.linhas.all():
        ws.append(
            [
                ln.codigo_produto,
                ln.descricao,
                ln.marca,
                float(ln.quantidade_estoque),
                float(ln.quantidade_estoque_contabil),
                float(ln.valor_ultima_compra),
                float(ln.valor_custo_medio),
                float(ln.valor_custo_contabil),
            ],
        )
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@transaction.atomic
def aplicar_contagem_ao_estoque(inventario: Inventario, usuario: User) -> dict[str, int]:
    rodada = inventario.rodada_atualiza_estoque
    if rodada not in (1, 2, 3):
        raise ValueError('Selecione qual contagem (1ª, 2ª ou 3ª) atualizará o estoque.')

    stats = {'atualizados': 0, 'ignorados': 0}
    campo = f'contagem_{rodada}'
    produtos_por_codigo = {
        p.codigo_produto: p
        for p in ProdutoEstoque.objects.filter(empresa_id=inventario.empresa_id)
    }
    atualizar: list[ProdutoEstoque] = []

    for item in inventario.itens.select_related('produto'):
        qtd = getattr(item, campo, None)
        if qtd is None:
            stats['ignorados'] += 1
            continue
        produto = item.produto
        if produto is None or produto.pk is None:
            produto = produtos_por_codigo.get(item.codigo_produto)
        if produto is None:
            stats['ignorados'] += 1
            continue
        produto.quantidade_estoque = qtd
        atualizar.append(produto)
        stats['atualizados'] += 1

    if atualizar:
        ProdutoEstoque.objects.bulk_update(atualizar, ['quantidade_estoque'])

    inventario.estoque_aplicado_em = timezone.now()
    inventario.estoque_aplicado_por = usuario
    inventario.save(update_fields=['estoque_aplicado_em', 'estoque_aplicado_por'])
    return stats
