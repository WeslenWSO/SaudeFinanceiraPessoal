"""Copia linhas de TabelaPreco de um cabeçalho para outro (mesma empresa)."""
from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction

from servicos_medicos.models import Cabecalho, TabelaPreco


@dataclass
class ResultadoReplicacao:
    criados: int = 0
    atualizados: int = 0
    pulados: int = 0
    total_origem: int = 0


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
    linhas = list(
        TabelaPreco.objects.filter(
            empresa_id=origem.empresa_id,
            cabecalho=origem,
        ).select_related("codigo_servico")
    )
    resultado.total_origem = len(linhas)
    if not linhas:
        return resultado

    with transaction.atomic():
        for tp in linhas:
            existente = TabelaPreco.objects.filter(
                empresa_id=destino.empresa_id,
                convenio=destino.convenio,
                cabecalho=destino,
                codigo_servico=tp.codigo_servico,
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
                convenio=destino.convenio,
                cabecalho=destino,
                codigo_servico=tp.codigo_servico,
                preco_apartamento=tp.preco_apartamento,
                preco_enfermaria=tp.preco_enfermaria,
            )
            resultado.criados += 1

    return resultado
