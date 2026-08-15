"""Atualiza faturamento médico a partir de planilha (paciente, associado, valor, conferência)."""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path

from django.db.models import Q

from faturamento_medico.models import FaturamentoMedico, ItemServico


@dataclass
class LinhaPlanilha:
    data: date
    paciente: str
    nome_associado: str
    procedimento: str
    modalidade: str
    valor: Decimal
    guia: str = ''


def _normalizar_texto(valor: str) -> str:
    txt = (valor or '').strip().upper()
    txt = unicodedata.normalize('NFKD', txt)
    txt = ''.join(c for c in txt if not unicodedata.combining(c))
    txt = re.sub(r'\s+', ' ', txt)
    return txt


def _parse_data(raw: str) -> date:
    raw = (raw or '').strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f'Data inválida: {raw!r}')


def _parse_valor(raw: str) -> Decimal:
    s = (raw or '').strip().replace('R$', '').strip()
    if not s:
        raise ValueError('Valor vazio')
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    elif s.count('.') > 1:
        parts = s.split('.')
        s = ''.join(parts[:-1]) + '.' + parts[-1]
    return Decimal(s)


def _associado_final(paciente: str, associado: str) -> str:
    assoc = (associado or '').strip()
    if not assoc or _normalizar_texto(assoc) == 'TITULAR':
        return paciente.strip()
    return assoc


def _similaridade(a: str, b: str) -> float:
    na = _normalizar_texto(a)
    nb = _normalizar_texto(b)
    if not na or not nb:
        return 0.0
    if na in nb or nb in na:
        return 0.95
    return SequenceMatcher(None, na, nb).ratio()


def _detectar_delimitador(amostra: str) -> str:
    if '\t' in amostra:
        return '\t'
    if ';' in amostra and amostra.count(';') >= amostra.count(','):
        return ';'
    return ','


def _mapear_colunas(fieldnames: list[str] | None) -> dict[str, str]:
    if not fieldnames:
        raise ValueError('Arquivo sem cabeçalho.')
    mapa: dict[str, str] = {}
    for col in fieldnames:
        chave = _normalizar_texto(col).replace(' ', '_')
        mapa[chave] = col
    aliases = {
        'data': ('DATA',),
        'paciente': ('PACIENTE',),
        'nome_associado': ('NOME_ASSOCIADO', 'ASSOCIADO', 'NOME_DO_ASSOCIADO'),
        'procedimento': ('PROCEDIMENTO', 'EXAME', 'SERVICO'),
        'modalidade': ('MODALIDADE', 'MOD', 'MODALID'),
        'valor': ('VALOR', 'VALOR_TOTAL'),
        'guia': ('GUIA', 'NUMERO_DA_GUIA', 'NUMERO GUIA', 'N_DA_GUIA'),
    }
    obrigatorias = ('data', 'paciente', 'procedimento', 'modalidade', 'valor')
    resultado: dict[str, str] = {}
    for destino, opcoes in aliases.items():
        for op in opcoes:
            if op in mapa:
                resultado[destino] = mapa[op]
                break
        else:
            if destino in obrigatorias:
                raise ValueError(f'Coluna obrigatória ausente: {destino}')
    return resultado


def carregar_planilha(caminho: Path) -> list[LinhaPlanilha]:
    texto = caminho.read_text(encoding='utf-8-sig')
    delim = _detectar_delimitador(texto[:4096])
    reader = csv.DictReader(texto.splitlines(), delimiter=delim)
    colunas = _mapear_colunas(reader.fieldnames)
    linhas: list[LinhaPlanilha] = []
    for idx, row in enumerate(reader, start=2):
        paciente = (row.get(colunas['paciente']) or '').strip()
        if not paciente:
            continue
        try:
            linhas.append(
                LinhaPlanilha(
                    data=_parse_data(row.get(colunas['data'], '')),
                    paciente=paciente,
                    nome_associado=(row.get(colunas.get('nome_associado', ''), '') or '').strip(),
                    procedimento=(row.get(colunas['procedimento']) or '').strip(),
                    modalidade=(row.get(colunas['modalidade']) or '').strip().upper(),
                    valor=_parse_valor(row.get(colunas['valor'], '')),
                    guia=(row.get(colunas.get('guia', ''), '') or '').strip(),
                )
            )
        except ValueError as exc:
            raise ValueError(f'Linha {idx}: {exc}') from exc
    return linhas


def _filtro_convenio(convenio: str) -> Q:
    nome = (convenio or '').strip().upper()
    if not nome:
        return Q(faturamento__convenio__icontains='BOMBEIRO')
    if nome == 'FUSEX':
        return Q(faturamento__convenio__iexact='FUSEX')
    return Q(faturamento__convenio__icontains=nome)


def _normalizar_guia(guia: str) -> str:
    return re.sub(r'\D', '', (guia or '').strip())


def _modalidades_equivalentes(a: str, b: str) -> bool:
    na = _normalizar_texto(a)
    nb = _normalizar_texto(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    par = {('MR', 'RM'), ('CR', 'RX')}
    return (na, nb) in par or (nb, na) in par


def _modalidade_filter(modalidade: str) -> Q:
    mod = (modalidade or '').strip().upper()
    if not mod:
        return Q()
    if mod in ('MR', 'RM'):
        return Q(modalidade__iexact='MR') | Q(modalidade__iexact='RM')
    return Q(modalidade__iexact=mod)


def _paciente_compativel(linha: LinhaPlanilha, fat: FaturamentoMedico) -> bool:
    guia_csv = _normalizar_guia(linha.guia)
    guia_fat = _normalizar_guia(fat.guia or '')
    if guia_csv and guia_fat and (guia_csv == guia_fat or guia_csv in guia_fat or guia_fat in guia_csv):
        return True

    paciente_norm = _normalizar_texto(linha.paciente)
    fat_nome = _normalizar_texto(fat.nome or '')
    fat_assoc = _normalizar_texto(fat.nome_associado or '')
    if not paciente_norm:
        return False
    for candidato in (fat_nome, fat_assoc):
        if not candidato:
            continue
        if candidato == paciente_norm:
            return True
        if _similaridade(linha.paciente, candidato) >= 0.82:
            return True
    return False


def _score_item(linha: LinhaPlanilha, item: ItemServico) -> float:
    fat = item.faturamento
    score = 0.0
    paciente_norm = _normalizar_texto(linha.paciente)
    assoc_csv = _normalizar_texto(linha.nome_associado or '')
    fat_nome = _normalizar_texto(fat.nome or '')
    fat_assoc = _normalizar_texto(fat.nome_associado or '')

    if fat_nome == paciente_norm or fat_assoc == paciente_norm:
        score += 4.0
    elif paciente_norm in fat_nome or fat_nome in paciente_norm:
        score += 2.5
    elif paciente_norm in fat_assoc or fat_assoc in paciente_norm:
        score += 2.0

    if assoc_csv and assoc_csv != 'TITULAR':
        if fat_assoc == assoc_csv:
            score += 2.5
        elif _similaridade(assoc_csv, fat_assoc) >= 0.82:
            score += 1.5

    score += _similaridade(linha.procedimento, item.servico or '') * 3.5

    if linha.modalidade and _modalidades_equivalentes(item.modalidade or '', linha.modalidade):
        score += 1.0

    guia_csv = _normalizar_guia(linha.guia)
    guia_fat = _normalizar_guia(fat.guia or '')
    if guia_csv and guia_fat:
        if guia_csv == guia_fat or guia_csv in guia_fat or guia_fat in guia_csv:
            score += 5.0
        else:
            score -= 4.0

    valor_item = item.total if item.total is not None else item.valor
    if valor_item is not None:
        diff = abs(Decimal(valor_item) - linha.valor)
        if diff <= Decimal('0.01'):
            score += 4.0
        elif diff <= Decimal('50'):
            score += 1.0
        else:
            score -= 1.5

    return score


def _candidatos_query(linha: LinhaPlanilha, *, empresa_id: int, convenio: str, apenas_pendentes: bool):
    qs = (
        ItemServico.objects
        .select_related('faturamento')
        .filter(
            faturamento__empresa_id=empresa_id,
            faturamento__data=linha.data,
        )
        .filter(_filtro_convenio(convenio))
    )
    guia_norm = _normalizar_guia(linha.guia)
    if guia_norm:
        qs_guia = qs.filter(faturamento__guia__icontains=guia_norm)
        if qs_guia.exists():
            qs = qs_guia
    if apenas_pendentes:
        qs = qs.exclude(status_conferencia='CONFERIDO').exclude(conferido=True)
    qs = qs.filter(_modalidade_filter(linha.modalidade))
    return qs


def _buscar_item(
    linha: LinhaPlanilha,
    *,
    empresa_id: int,
    convenio: str,
    ids_usados: set[int],
) -> ItemServico | None:
    melhor: ItemServico | None = None
    melhor_score = 0.0

    for item in _candidatos_query(linha, empresa_id=empresa_id, convenio=convenio, apenas_pendentes=True):
        if item.id in ids_usados:
            continue
        if not _paciente_compativel(linha, item.faturamento):
            continue
        score = _score_item(linha, item)
        if score > melhor_score:
            melhor_score = score
            melhor = item

    if melhor is None or melhor_score < 5.0:
        return None
    return melhor


def _ja_conferido_no_banco(linha: LinhaPlanilha, *, empresa_id: int, convenio: str) -> bool:
    melhor_score = 0.0
    for item in _candidatos_query(linha, empresa_id=empresa_id, convenio=convenio, apenas_pendentes=False):
        if not (item.conferido or item.status_conferencia == 'CONFERIDO'):
            continue
        if not _paciente_compativel(linha, item.faturamento):
            continue
        score = _score_item(linha, item)
        if score > melhor_score:
            melhor_score = score
    return melhor_score >= 5.0


def aplicar_atualizacoes(
    linhas: list[LinhaPlanilha],
    *,
    empresa_id: int,
    convenio: str = 'CORPO DE BOMBEIRO',
    dry_run: bool = False,
) -> dict:
    stats = {
        'linhas': len(linhas),
        'atualizados': 0,
        'ignorados_conferidos': 0,
        'ja_conferidos_banco': 0,
        'nao_encontrados': 0,
        'erros': 0,
        'detalhes': [],
    }
    ids_usados: set[int] = set()

    for linha in linhas:
        item = _buscar_item(linha, empresa_id=empresa_id, convenio=convenio, ids_usados=ids_usados)
        if item is None:
            if _ja_conferido_no_banco(linha, empresa_id=empresa_id, convenio=convenio):
                stats['ja_conferidos_banco'] += 1
                stats['detalhes'].append(
                    f"JÁ CONFERIDO: {linha.data:%d/%m/%Y} | {linha.paciente} | {linha.modalidade} | R$ {linha.valor}"
                )
            else:
                stats['nao_encontrados'] += 1
                stats['detalhes'].append(
                    f"NÃO ENCONTRADO: {linha.data:%d/%m/%Y} | {linha.paciente} | {linha.modalidade} | R$ {linha.valor}"
                )
            continue

        if item.status_conferencia == 'CONFERIDO' or item.conferido:
            stats['ignorados_conferidos'] += 1
            continue

        fat: FaturamentoMedico = item.faturamento
        assoc = _associado_final(linha.paciente, linha.nome_associado)

        if dry_run:
            stats['atualizados'] += 1
            stats['detalhes'].append(
                f"DRY-RUN item #{item.id} fat #{fat.id}: "
                f"{fat.nome!r} -> {linha.paciente!r}, "
                f"assoc {fat.nome_associado!r} -> {assoc!r}, "
                f"valor {item.valor} -> {linha.valor}, CONFERIDO"
            )
            ids_usados.add(item.id)
            continue

        try:
            fat.nome = linha.paciente[:200]
            fat.nome_associado = assoc[:200]
            update_fat = ['nome', 'nome_associado']
            if linha.guia and not (fat.guia or '').strip():
                fat.guia = linha.guia[:80]
                update_fat.append('guia')
            fat.save(update_fields=update_fat)

            item.valor = linha.valor
            if linha.procedimento:
                item.servico = linha.procedimento[:200]
            item.conferido = True
            item.status_conferencia = 'CONFERIDO'
            item.save()

            fat.atualizar_total()
            stats['atualizados'] += 1
            ids_usados.add(item.id)
            stats['detalhes'].append(
                f"OK item #{item.id} fat #{fat.id}: {linha.paciente} | {linha.modalidade} | R$ {linha.valor}"
            )
        except Exception as exc:
            stats['erros'] += 1
            stats['detalhes'].append(f"ERRO {linha.paciente}: {exc}")

    return stats
