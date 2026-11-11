"""Importação de Serviços Médicos e Tabela de Preço via Excel (.xlsx)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from io import BytesIO

from django.db import transaction
from openpyxl import Workbook, load_workbook

from servicos_medicos.models import Cabecalho, Convenio, ServicosMedicos, TabelaPreco

MAX_CODIGO = 20
MAX_SERVICO = 200

COLUNAS_SERVICOS = (
    'Código',
    'Serviços',
    'Porte anestésico',
)

COLUNAS_TABELA_PRECO = (
    'Convênio',
    'Nome da tabela',
    'Código do serviço',
    'Serviço (opcional)',
    'Preço sem contraste',
    'Preço com contraste',
)

COLUNAS_TABELA_PRECO_CABECALHO_FIXO = (
    'Código do serviço',
    'Serviço (opcional)',
    'Preço sem contraste',
    'Preço com contraste',
)


def _norm_header(val) -> str:
    if val is None:
        return ''
    s = str(val).strip().lower()
    for old, new in (
        ('á', 'a'), ('à', 'a'), ('ã', 'a'), ('â', 'a'),
        ('é', 'e'), ('ê', 'e'), ('í', 'i'),
        ('ó', 'o'), ('ô', 'o'), ('õ', 'o'), ('ú', 'u'), ('ç', 'c'),
    ):
        s = s.replace(old, new)
    s = ' '.join(s.split())
    return s


def _parse_decimal_preco(val) -> Decimal | None:
    if val is None or val == '':
        return None
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val)).quantize(Decimal('0.01'))
    s = str(val).strip().replace('R$', '').replace(' ', '')
    if not s:
        return None
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return Decimal(s).quantize(Decimal('0.01'))
    except InvalidOperation:
        return None


def _parse_porte(val) -> int | None:
    if val is None or val == '':
        return None
    if isinstance(val, (int, float)):
        n = int(val)
        return n if 0 <= n <= 6 else None
    s = str(val).strip()
    if not s:
        return None
    try:
        n = int(s)
        return n if 0 <= n <= 6 else None
    except ValueError:
        return None


def _primeira_linha_dados(ws) -> tuple[list, int]:
    for idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if row and any(c is not None and str(c).strip() for c in row):
            return list(row), idx
    return [], 0


def _map_colunas_servicos(headers: list) -> dict[str, int | None]:
    norm = [_norm_header(h) for h in headers]
    out: dict[str, int | None] = {k: None for k in ('codigo', 'servicos', 'porte')}
    for i, h in enumerate(norm):
        if h in ('codigo', 'cod', 'codigo servico', 'codigo do servico'):
            out['codigo'] = i
        elif h in ('servicos', 'servico', 'descricao', 'nome', 'servicos medicos'):
            out['servicos'] = i
        elif h in ('porte anestesico', 'porte', 'porte anest'):
            out['porte'] = i
    return out


def _map_colunas_tabela(headers: list, *, cabecalho_fixo: bool) -> dict[str, int | None]:
    norm = [_norm_header(h) for h in headers]
    chaves = (
        ('convenio', ('convenio',)),
        ('nome_tabela', ('nome da tabela', 'cabecalho', 'tabela', 'nome tabela')),
        ('codigo', ('codigo do servico', 'codigo servico', 'codigo', 'cod')),
        ('servico_opcional', ('servico (opcional)', 'servico opcional', 'servico', 'descricao')),
        ('preco_sem', (
            'preco sem contraste',
            'preco apartamento',
            'sem contraste',
            'valor sem contraste',
        )),
        ('preco_com', (
            'preco com contraste',
            'preco enfermaria',
            'com contraste',
            'valor com contraste',
        )),
    )
    if cabecalho_fixo:
        chaves = chaves[2:]
    out: dict[str, int | None] = {k: None for k, _ in chaves}
    for i, h in enumerate(norm):
        for chave, aliases in chaves:
            if h in aliases or h == chave.replace('_', ' '):
                out[chave] = i
    return out


def _cel(row: tuple, idx: int | None) -> str:
    if idx is None or idx >= len(row):
        return ''
    val = row[idx]
    if val is None:
        return ''
    return str(val).strip()


def parse_planilha_servicos(content: bytes) -> tuple[list[dict], list[str]]:
    avisos: list[str] = []
    try:
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        return [], [f'Arquivo Excel inválido: {exc}']
    ws = wb.active
    headers, start = _primeira_linha_dados(ws)
    if not headers:
        return [], ['Planilha vazia.']
    col = _map_colunas_servicos(headers)
    if col['codigo'] is None or col['servicos'] is None:
        return [], [
            'Cabeçalho não reconhecido. Use o modelo com colunas: Código, Serviços, Porte anestésico.',
        ]
    linhas: list[dict] = []
    vistos: set[str] = set()
    for row_num, row in enumerate(ws.iter_rows(min_row=start + 1, values_only=True), start=start + 1):
        if not row or not any(c is not None and str(c).strip() for c in row):
            continue
        codigo = _cel(row, col['codigo'])[:MAX_CODIGO]
        servicos = _cel(row, col['servicos'])[:MAX_SERVICO]
        if not codigo and not servicos:
            continue
        if not codigo:
            avisos.append(f'Linha {row_num}: código vazio — ignorada.')
            continue
        if not servicos:
            avisos.append(f'Linha {row_num}: descrição vazia para código {codigo} — ignorada.')
            continue
        if codigo in vistos:
            avisos.append(f'Linha {row_num}: código {codigo} duplicado na planilha — última linha prevalece.')
        vistos.add(codigo)
        linhas.append({
            'codigo': codigo,
            'servicos': servicos,
            'porte_anestesico': _parse_porte(row[col['porte']] if col['porte'] is not None else None),
            '_linha': row_num,
        })
    wb.close()
    return linhas, avisos


def importar_servicos_medicos(
    linhas: list[dict],
    *,
    atualizar_existentes: bool = True,
) -> dict[str, int]:
    stats = {'criados': 0, 'atualizados': 0, 'ignorados': 0}
    if not linhas:
        return stats
    codigos = [ln['codigo'] for ln in linhas]
    existentes = {s.codigo: s for s in ServicosMedicos.objects.filter(codigo__in=codigos)}
    with transaction.atomic():
        for ln in linhas:
            cod = ln['codigo']
            obj = existentes.get(cod)
            if obj is None:
                ServicosMedicos.objects.create(
                    codigo=cod,
                    servicos=ln['servicos'],
                    porte_anestesico=ln['porte_anestesico'],
                )
                stats['criados'] += 1
            elif atualizar_existentes:
                mudou = False
                if obj.servicos != ln['servicos']:
                    obj.servicos = ln['servicos']
                    mudou = True
                if obj.porte_anestesico != ln['porte_anestesico']:
                    obj.porte_anestesico = ln['porte_anestesico']
                    mudou = True
                if mudou:
                    obj.save(update_fields=['servicos', 'porte_anestesico'])
                    stats['atualizados'] += 1
                else:
                    stats['ignorados'] += 1
            else:
                stats['ignorados'] += 1
    return stats


def parse_planilha_tabela_preco(
    content: bytes,
    *,
    cabecalho_fixo: bool,
) -> tuple[list[dict], list[str]]:
    avisos: list[str] = []
    try:
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        return [], [f'Arquivo Excel inválido: {exc}']
    ws = wb.active
    headers, start = _primeira_linha_dados(ws)
    if not headers:
        return [], ['Planilha vazia.']
    col = _map_colunas_tabela(headers, cabecalho_fixo=cabecalho_fixo)
    if col['codigo'] is None or col['preco_sem'] is None or col['preco_com'] is None:
        return [], [
            'Cabeçalho não reconhecido. Baixe o modelo Excel e mantenha a primeira linha de títulos.',
        ]
    if not cabecalho_fixo and (col['convenio'] is None or col['nome_tabela'] is None):
        return [], [
            'Faltam colunas Convênio e Nome da tabela — ou selecione um cabeçalho na tela de importação.',
        ]
    linhas: list[dict] = []
    for row_num, row in enumerate(ws.iter_rows(min_row=start + 1, values_only=True), start=start + 1):
        if not row or not any(c is not None and str(c).strip() for c in row):
            continue
        codigo = _cel(row, col['codigo'])[:MAX_CODIGO]
        if not codigo:
            avisos.append(f'Linha {row_num}: código vazio — ignorada.')
            continue
        preco_sem = _parse_decimal_preco(row[col['preco_sem']])
        preco_com = _parse_decimal_preco(row[col['preco_com']])
        if preco_sem is None or preco_com is None:
            avisos.append(f'Linha {row_num}: preços inválidos para código {codigo} — ignorada.')
            continue
        ln = {
            'codigo': codigo,
            'preco_apartamento': preco_sem,
            'preco_enfermaria': preco_com,
            'servico_opcional': _cel(row, col.get('servico_opcional')),
            '_linha': row_num,
        }
        if not cabecalho_fixo:
            ln['convenio'] = _cel(row, col['convenio'])
            ln['nome_tabela'] = _cel(row, col['nome_tabela'])
            if not ln['convenio'] or not ln['nome_tabela']:
                avisos.append(f'Linha {row_num}: convênio/cabeçalho vazio — ignorada.')
                continue
        linhas.append(ln)
    wb.close()
    return linhas, avisos


def _convenio_por_nome(empresa_id: int, nome: str) -> Convenio | None:
    n = (nome or '').strip()
    if not n:
        return None
    return (
        Convenio.objects.filter(empresa_id=empresa_id, nome__iexact=n).first()
        or Convenio.objects.filter(empresa_id=empresa_id, nome__icontains=n).first()
    )


def _cabecalho_por_nome(empresa_id: int, convenio: Convenio, nome_tabela: str) -> Cabecalho | None:
    nt = (nome_tabela or '').strip()
    if not nt:
        return None
    return (
        Cabecalho.objects.filter(
            empresa_id=empresa_id,
            convenio=convenio,
            nome_tabela__iexact=nt,
        ).first()
        or Cabecalho.objects.filter(
            empresa_id=empresa_id,
            convenio=convenio,
            nome_tabela__icontains=nt,
        ).first()
    )


def importar_tabela_preco(
    empresa_id: int,
    linhas: list[dict],
    *,
    cabecalho_fixo: Cabecalho | None = None,
    atualizar_existentes: bool = True,
) -> tuple[dict[str, int], list[str]]:
    stats = {'criados': 0, 'atualizados': 0, 'ignorados': 0, 'erros': 0}
    avisos: list[str] = []
    if not linhas:
        return stats, avisos

    codigos = {ln['codigo'] for ln in linhas}
    servicos = {s.codigo: s for s in ServicosMedicos.objects.filter(codigo__in=codigos)}

    cache_cab: dict[tuple[str, str], Cabecalho | None] = {}
    if cabecalho_fixo:
        convenio = cabecalho_fixo.convenio
        if convenio is None:
            avisos.append('Cabeçalho selecionado sem convênio.')
            return stats, avisos

    with transaction.atomic():
        for ln in linhas:
            cod = ln['codigo']
            servico = servicos.get(cod)
            if servico is None:
                stats['erros'] += 1
                avisos.append(
                    f"Linha {ln.get('_linha', '?')}: código {cod} não existe em Serviços Médicos — "
                    'cadastre ou importe o serviço antes.',
                )
                continue

            if cabecalho_fixo:
                cab = cabecalho_fixo
            else:
                chave = (ln['convenio'].upper(), ln['nome_tabela'].upper())
                if chave not in cache_cab:
                    conv = _convenio_por_nome(empresa_id, ln['convenio'])
                    if conv is None:
                        cache_cab[chave] = None
                    else:
                        cache_cab[chave] = _cabecalho_por_nome(empresa_id, conv, ln['nome_tabela'])
                cab = cache_cab[chave]
                if cab is None:
                    stats['erros'] += 1
                    avisos.append(
                        f"Linha {ln.get('_linha', '?')}: convênio/cabeçalho "
                        f'«{ln.get("convenio")} — {ln.get("nome_tabela")}» não encontrado.',
                    )
                    continue

            obj = TabelaPreco.objects.filter(
                empresa_id=empresa_id,
                convenio_id=cab.convenio_id,
                cabecalho_id=cab.pk,
                codigo_servico=servico,
            ).first()
            if obj is None:
                TabelaPreco.objects.create(
                    empresa_id=empresa_id,
                    convenio_id=cab.convenio_id,
                    cabecalho_id=cab.pk,
                    codigo_servico=servico,
                    preco_apartamento=ln['preco_apartamento'],
                    preco_enfermaria=ln['preco_enfermaria'],
                )
                stats['criados'] += 1
            elif atualizar_existentes:
                mudou = (
                    obj.preco_apartamento != ln['preco_apartamento']
                    or obj.preco_enfermaria != ln['preco_enfermaria']
                )
                if mudou:
                    obj.preco_apartamento = ln['preco_apartamento']
                    obj.preco_enfermaria = ln['preco_enfermaria']
                    obj.save(update_fields=['preco_apartamento', 'preco_enfermaria'])
                    stats['atualizados'] += 1
                else:
                    stats['ignorados'] += 1
            else:
                stats['ignorados'] += 1

    return stats, avisos


def _workbook_bytes(headers: tuple[str, ...], exemplo: tuple) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = 'Importar'
    ws.append(list(headers))
    ws.append(list(exemplo))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def modelo_servicos_medicos_xlsx() -> bytes:
    return _workbook_bytes(
        COLUNAS_SERVICOS,
        ('41001001', 'RM - CRÂNIO', 2),
    )


def modelo_tabela_preco_xlsx(*, cabecalho_fixo: bool = False) -> bytes:
    if cabecalho_fixo:
        return _workbook_bytes(
            COLUNAS_TABELA_PRECO_CABECALHO_FIXO,
            ('41001001', 'RM - CRÂNIO', 350.00, 420.00),
        )
    return _workbook_bytes(
        COLUNAS_TABELA_PRECO,
        ('PARTICULAR', 'TABELA PARTICULAR', '41001001', 'RM - CRÂNIO', 350.00, 420.00),
    )
