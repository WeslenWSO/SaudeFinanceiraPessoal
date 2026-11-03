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
    faltantes_no_destino: int = 0
    ja_no_destino: int = 0


MODO_SOMENTE_FALTANTES = "faltantes"
MODO_COMPLETO = "completo"


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
            "codigo_servico__servicos",
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


def _ids_servico_no_destino(destino: Cabecalho) -> set[int]:
    return set(
        TabelaPreco.objects.filter(
            empresa_id=destino.empresa_id,
            convenio_id=destino.convenio_id,
            cabecalho_id=destino.pk,
        ).values_list("codigo_servico_id", flat=True)
    )


def contagem_faltantes_no_destino(origem: Cabecalho, destino: Cabecalho) -> tuple[int, int]:
    """Retorna (quantidade que falta copiar, quantidade já presente no destino)."""
    linhas = _linhas_origem_valores(origem)
    if not linhas:
        return 0, 0
    no_destino = _ids_servico_no_destino(destino)
    faltantes = 0
    ja = 0
    for row in linhas:
        sid = row["codigo_servico_id"]
        if sid in no_destino:
            ja += 1
        else:
            faltantes += 1
    return faltantes, ja


def linhas_origem_para_selecao(
    origem: Cabecalho,
    destino: Cabecalho | None = None,
) -> list[dict]:
    """Lista exames da origem com preços que serão copiados (sem alteração)."""
    no_destino = _ids_servico_no_destino(destino) if destino else set()
    out: list[dict] = []
    for row in _linhas_origem_valores(origem):
        sid = row["codigo_servico_id"]
        out.append(
            {
                "servico_id": sid,
                "codigo": (row.get("codigo_servico__codigo") or "").strip(),
                "nome": (row.get("codigo_servico__servicos") or "").strip()[:200],
                "sem_contraste": row["preco_apartamento"],
                "com_contraste": row["preco_enfermaria"],
                "ja_no_destino": sid in no_destino,
            }
        )
    out.sort(key=lambda x: x["codigo"])
    return out


def replicar_tabela_preco(
    origem: Cabecalho,
    destino: Cabecalho,
    *,
    atualizar_existentes: bool = True,
    servico_ids: frozenset[int] | None = None,
) -> ResultadoReplicacao:
    if origem.pk == destino.pk:
        raise ValueError("Origem e destino devem ser cabeçalhos diferentes.")
    if origem.empresa_id != destino.empresa_id:
        raise ValueError("Origem e destino devem ser da mesma empresa.")

    resultado = ResultadoReplicacao()
    linhas = _linhas_origem_valores(origem)
    if servico_ids is not None:
        linhas = [r for r in linhas if r["codigo_servico_id"] in servico_ids]
    resultado.total_origem = len(linhas)
    falt, ja = contagem_faltantes_no_destino(origem, destino)
    resultado.faltantes_no_destino = falt
    resultado.ja_no_destino = ja
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
