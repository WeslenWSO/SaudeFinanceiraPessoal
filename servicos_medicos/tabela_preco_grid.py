"""Atualização inline da grid de Tabela de Preços."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.db import transaction

from servicos_medicos.models import ServicosMedicos, TabelaPreco


class ErroGridTabelaPreco(ValueError):
    pass


def _parse_decimal(valor, *, campo: str) -> Decimal:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        raise ErroGridTabelaPreco(f"{campo} é obrigatório.")
    try:
        d = Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, TypeError) as exc:
        raise ErroGridTabelaPreco(f"{campo} inválido.") from exc
    if d < 0:
        raise ErroGridTabelaPreco(f"{campo} não pode ser negativo.")
    return d.quantize(Decimal("0.01"))


@transaction.atomic
def atualizar_linha_grid(
    *,
    tabela_preco_id: int,
    empresa_id: int | None,
    servicos: str | None = None,
    preco_apartamento=None,
    preco_enfermaria=None,
) -> dict:
    try:
        tp = (
            TabelaPreco.objects.select_related("codigo_servico")
            .select_for_update()
            .get(pk=tabela_preco_id)
        )
    except TabelaPreco.DoesNotExist as exc:
        raise ErroGridTabelaPreco("Linha de preço não encontrada.") from exc

    if empresa_id is not None and tp.empresa_id != int(empresa_id):
        raise ErroGridTabelaPreco("Linha fora da empresa da sessão.")

    servico: ServicosMedicos = tp.codigo_servico
    campos_preco: list[str] = []

    if servicos is not None:
        nome = servicos.strip()
        if not nome:
            raise ErroGridTabelaPreco("Descrição do serviço não pode ficar vazia.")
        if len(nome) > 200:
            nome = nome[:200]
        if servico.servicos != nome:
            servico.servicos = nome
            servico.save(update_fields=["servicos"])

    if preco_apartamento is not None:
        tp.preco_apartamento = _parse_decimal(preco_apartamento, campo="Preço sem contraste")
        campos_preco.append("preco_apartamento")
    if preco_enfermaria is not None:
        tp.preco_enfermaria = _parse_decimal(preco_enfermaria, campo="Preço com contraste")
        campos_preco.append("preco_enfermaria")

    if campos_preco:
        tp.save(update_fields=campos_preco)

    return {
        "id": tp.pk,
        "servicos": servico.servicos,
        "codigo": servico.codigo,
        "preco_apartamento": str(tp.preco_apartamento),
        "preco_enfermaria": str(tp.preco_enfermaria),
    }
