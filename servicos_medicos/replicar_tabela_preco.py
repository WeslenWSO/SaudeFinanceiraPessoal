"""Copia linhas de TabelaPreco de um cabeçalho para outro (mesma empresa)."""
from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
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


def _linhas_origem(origem: Cabecalho):
    return list(queryset_linhas_origem(origem))


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
    linhas = list(_linhas_origem(origem))
    resultado.total_origem = len(linhas)
    if not linhas:
        return resultado

    with transaction.atomic():
        for tp in linhas:
            existente = TabelaPreco.objects.filter(
                empresa_id=destino.empresa_id,
                convenio_id=destino.convenio_id,
                cabecalho_id=destino.pk,
                codigo_servico_id=tp.codigo_servico_id,
            ).first()

            if existente:
                if atualizar_existentes:
                    mudou = (
                        existente.preco_apartamento != tp.preco_apartamento
                        or existente.preco_enfermaria != tp.preco_enfermaria
                    )
                    if mudou:
                        existente.preco_apartamento = tp.preco_apartamento
                        existente.preco_enfermaria = tp.preco_enfermaria
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
                codigo_servico_id=tp.codigo_servico_id,
                preco_apartamento=tp.preco_apartamento,
                preco_enfermaria=tp.preco_enfermaria,
            )
            resultado.criados += 1

    return resultado
