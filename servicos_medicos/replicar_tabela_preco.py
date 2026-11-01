"""Copia linhas de TabelaPreco de um cabeçalho para outro (mesma empresa)."""
from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.db.models import Q

from servicos_medicos.models import Cabecalho, TabelaPreco


@dataclass
class ResultadoReplicacao:
    criados: int = 0
    atualizados: int = 0
    pulados: int = 0
    total_origem: int = 0


def _ids_cabecalhos_equivalentes(origem: Cabecalho) -> list[int]:
    """Mesmo convênio + nome de tabela (evita cabeçalho duplicado sem preços no id escolhido)."""
    return list(
        Cabecalho.objects.filter(
            empresa_id=origem.empresa_id,
            convenio_id=origem.convenio_id,
            nome_tabela__iexact=origem.nome_tabela,
        ).values_list("pk", flat=True)
    )


def queryset_linhas_origem(origem: Cabecalho):
    """Preços da tabela origem (id exato, depois outros ids com mesmo convênio/nome)."""
    qs = TabelaPreco.objects.filter(cabecalho_id=origem.pk).select_related("codigo_servico")
    if qs.exists():
        return qs
    equiv = _ids_cabecalhos_equivalentes(origem)
    if equiv:
        qs = TabelaPreco.objects.filter(cabecalho_id__in=equiv).select_related("codigo_servico")
        if qs.exists():
            return qs
    return TabelaPreco.objects.filter(
        empresa_id=origem.empresa_id,
        convenio_id=origem.convenio_id,
    ).filter(Q(cabecalho__isnull=True)).select_related("codigo_servico")


def contagem_linhas_origem(origem: Cabecalho) -> int:
    return queryset_linhas_origem(origem).count()


def _linhas_origem_valores(origem: Cabecalho) -> list[dict]:
    """Cada item: codigo TUSS, preços e FK do serviço (nunca usa id de TabelaPreco)."""
    qs = (
        queryset_linhas_origem(origem)
        .values(
            "codigo_servico_id",
            "preco_apartamento",
            "preco_enfermaria",
            "codigo_servico__codigo",
        )
        .order_by("codigo_servico__codigo")
    )
    por_codigo: dict[str, dict] = {}
    for row in qs:
        codigo = (row.get("codigo_servico__codigo") or "").strip()
        if not codigo:
            continue
        por_codigo[codigo] = row
    return list(por_codigo.values())


def replicar_tabela_preco(
    origem: Cabecalho,
    destino: Cabecalho,
    *,
    atualizar_existentes: bool = True,
) -> ResultadoReplicacao:
    if origem.pk == destino.pk:
        raise ValueError("Origem e destino devem ser cabeçalhos diferentes.")
    if origem.empresa_id != destino.empresa_id:
        raise ValueError("Origem e destino devem ser da mesma empresa.")

    resultado = ResultadoReplicacao()
    linhas = _linhas_origem_valores(origem)
    resultado.total_origem = len(linhas)
    if not linhas:
        return resultado

    try:
        with transaction.atomic():
            for row in linhas:
                servico_id = row["codigo_servico_id"]
                preco_sem = row["preco_apartamento"]
                preco_com = row["preco_enfermaria"]

                existente = TabelaPreco.objects.filter(
                    empresa_id=destino.empresa_id,
                    convenio_id=destino.convenio_id,
                    cabecalho_id=destino.pk,
                    codigo_servico_id=servico_id,
                ).first()

                if existente:
                    if atualizar_existentes:
                        mudou = (
                            existente.preco_apartamento != preco_sem
                            or existente.preco_enfermaria != preco_com
                        )
                        if mudou:
                            existente.preco_apartamento = preco_sem
                            existente.preco_enfermaria = preco_com
                            existente.save(
                                update_fields=["preco_apartamento", "preco_enfermaria"]
                            )
                            resultado.atualizados += 1
                        else:
                            resultado.pulados += 1
                    else:
                        resultado.pulados += 1
                    continue

                TabelaPreco.objects.create(
                    empresa_id=destino.empresa_id,
                    convenio_id=destino.convenio_id,
                    cabecalho_id=destino.pk,
                    codigo_servico_id=servico_id,
                    preco_apartamento=preco_sem,
                    preco_enfermaria=preco_com,
                )
                resultado.criados += 1
    except IntegrityError as exc:
        raise ValueError(
            "Não foi possível gravar todos os preços (conflito de duplicidade). "
            "Confira se já existem linhas para este cabeçalho."
        ) from exc

    return resultado
