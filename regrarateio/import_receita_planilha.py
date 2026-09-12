"""Importação de receitas (exames) via planilha Excel → contas a receber + rateio."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path

from django.http import HttpResponse
from openpyxl import Workbook, load_workbook

from cobranca.models import Cobranca
from contasareceber.models import ContaAReceber
from notasfiscais.models import NotaFiscalServico
from regrarateio.models import LancamentoRateio, RegraRateio, RegraRateioItem
from regrarateio.services import (
    _gerar_linhas_rateio_conta_receber,
    _regra_usa_valor_manual,
    preview_linhas_rateio_por_regra,
)

MODELO_PLANILHA_PATH = (
    Path(__file__).resolve().parent / 'static' / 'modelos' / 'importar_receita_modelo.xlsx'
)

# Lotes pequenos evitam timeout (ex.: Render ~30s por requisição).
IMPORTACAO_LOTE_TAMANHO = 35


def preparar_linhas_para_sessao(linhas: list[dict]) -> list[dict]:
    """Remove dados de prévia (grandes) antes de gravar na sessão."""
    out = []
    for ln in linhas:
        slim = {k: v for k, v in ln.items() if k != 'preview_rateio'}
        out.append(slim)
    return out


def linhas_validas_para_importacao(linhas: list[dict]) -> list[dict]:
    return [ln for ln in linhas if ln.get('valido', True)]

# Cabeçalhos oficiais do modelo «Importar Receita MM-AAAA.xlsx»
COLUNAS_MODELO = (
    'Data',
    'Paciente',
    'Procedimento',
    'Modalidade',
    'Viabilizacao',
    'Forma de Pagamento',
    'Valor',
    'REGRA DE RATEUIO',
    'VALOR DO RATEIO',
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
    return s


def _parse_data(val) -> date | None:
    if val is None or val == '':
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()
    if not s:
        return None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _parse_moeda(val) -> Decimal:
    if val is None or val == '':
        return Decimal('0')
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val)).quantize(Decimal('0.01'))
    s = str(val).strip().replace('R$', '').replace(' ', '')
    if not s:
        return Decimal('0')
    neg = s.startswith('-')
    s = s.lstrip('-')
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        n = Decimal(s)
    except InvalidOperation:
        return Decimal('0')
    return (-n if neg else n).quantize(Decimal('0.01'))


def _map_colunas(headers: list) -> dict[str, int | None]:
    """Mapeia cabeçalhos; prioriza nomes exatos do modelo oficial."""
    norm = [_norm_header(h) for h in headers]
    col: dict[str, int | None] = {
        'data': None,
        'paciente': None,
        'procedimento': None,
        'modalidade': None,
        'viabilidade': None,
        'forma_pagamento': None,
        'valor': None,
        'valor_rateio': None,
        'regra': None,
    }

    for i, h in enumerate(norm):
        if h == 'data':
            col['data'] = i
        elif h == 'paciente':
            col['paciente'] = i
        elif h == 'procedimento':
            col['procedimento'] = i
        elif h == 'modalidade' or h.startswith('moda'):
            col['modalidade'] = col['modalidade'] if col['modalidade'] is not None else i
        elif h in ('viabilizacao', 'viabilidade'):
            col['viabilidade'] = i
        elif 'forma' in h and 'pag' in h:
            col['forma_pagamento'] = i
        elif h == 'valor do rateio' or h == 'valor rateio':
            col['valor_rateio'] = i
        elif h == 'valor':
            col['valor'] = i
        elif 'regra' in h and ('rateio' in h or 'rateuio' in h):
            col['regra'] = i

    # Fallbacks parciais (planilhas antigas)
    if col['valor'] is None:
        for i, h in enumerate(norm):
            if h == 'valor' or (h.startswith('valor') and 'rateio' not in h):
                col['valor'] = i
                break
    if col['regra'] is None:
        for i, h in enumerate(norm):
            if 'regra' in h:
                col['regra'] = i
                break

    return col


def _cel(row, col_map, key):
    i = col_map.get(key)
    if i is None or i >= len(row):
        return None
    return row[i]


def _extrair_nf_forma_pagamento(texto: str) -> str:
    m = re.search(r'\bNF\s*(\d+)\b', texto or '', re.I)
    return m.group(1) if m else ''


def _a_faturar(texto: str) -> bool:
    t = (texto or '').strip().upper()
    return 'A FATURAR' in t or t == 'AFATURAR'


def _montar_observacao(paciente: str, procedimento: str, modalidade: str, viabilidade: str) -> str:
    partes = []
    if paciente:
        partes.append(f'Pac:{paciente[:120]}')
    if procedimento:
        partes.append(f'Proc:{procedimento[:160]}')
    if modalidade:
        partes.append(f'Mod:{modalidade}')
    if viabilidade:
        partes.append(f'Viab:{viabilidade}')
    return '|'.join(partes)


def _resolver_regra(empresa_id: int, texto: str, cache: dict) -> RegraRateio | None:
    key = (texto or '').strip().upper()
    if not key:
        return None
    if key in cache:
        return cache[key]
    qs = RegraRateio.objects.filter(empresa_id=empresa_id, rateio='S')
    regra = None
    if key.isdigit():
        regra = qs.filter(pk=int(texto.strip())).first()
    if not regra:
        regra = qs.filter(codigo__iexact=texto.strip()).first()
    if not regra:
        regra = qs.filter(nomedaregra__iexact=texto.strip()).first()
    if not regra:
        # «100% USG» → regra «003 — 100% USG»
        for r in qs:
            rotulo = str(r).upper()
            if key == rotulo or key in rotulo or rotulo in key:
                regra = r
                break
    if not regra:
        token = key.replace('%', '').strip()
        for r in qs:
            rotulo = str(r).upper()
            if token and token in rotulo:
                regra = r
                break
    cache[key] = regra
    return regra


def _resolver_cobranca(texto: str, cache: dict) -> Cobranca | None:
    key = (texto or '').strip().upper()
    if not key or _a_faturar(texto):
        return None
    if key in cache:
        return cache[key]
    t = texto.strip()
    c = Cobranca.objects.filter(descricao__iexact=t).first()
    if not c:
        c = Cobranca.objects.filter(descricao__icontains=t[:25]).first()
    if not c:
        aliases = {
            'DH': 'DINHEIRO',
            'PIX': 'PIX',
            'CARTAO CREDITO': 'CARTAO',
            'CARTAO DEBITO': 'CARTAO',
            'CARTAO': 'CARTAO',
        }
        for frag, busca in aliases.items():
            if frag in key:
                c = Cobranca.objects.filter(descricao__icontains=busca).first()
                if c:
                    break
    cache[key] = c
    return c


def _nota_por_numero(empresa_id: int, nf: str, cache: dict):
    nf = (nf or '').strip()
    if not nf:
        return None
    if nf in cache:
        return cache[nf]
    nota = (
        NotaFiscalServico.objects.filter(empresa_id=empresa_id, numero_nota=nf)
        .order_by('-data_emissao')
        .first()
    )
    cache[nf] = nota
    return nota


def parse_receita_planilha_xlsx(
    file_bytes: bytes,
    *,
    regra_padrao_id: int | None = None,
    empresa_id: int | None = None,
) -> tuple[list[dict], list[str]]:
    wb = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        header_row = next(rows_iter)
    except StopIteration:
        return [], ['Planilha vazia.']

    col_map = _map_colunas(list(header_row))
    if col_map.get('data') is None:
        return [], ['Coluna «Data» não encontrada.']
    if col_map.get('valor') is None:
        return [], ['Coluna «Valor» não encontrada.']
    if col_map.get('regra') is None and not regra_padrao_id:
        return [], [
            'Coluna «REGRA DE RATEUIO» não encontrada. '
            'Use o modelo oficial ou selecione uma regra padrão no formulário.'
        ]

    regra_cache: dict = {}
    linhas = []
    avisos = []

    for num, row in enumerate(rows_iter, start=2):
        if not row or not any(row):
            continue

        data = _parse_data(_cel(row, col_map, 'data'))
        valor = _parse_moeda(_cel(row, col_map, 'valor'))
        valor_rateio_raw = _cel(row, col_map, 'valor_rateio')
        valor_rateio = _parse_moeda(valor_rateio_raw) if valor_rateio_raw not in (None, '') else valor

        paciente = str(_cel(row, col_map, 'paciente') or '').strip()
        procedimento = str(_cel(row, col_map, 'procedimento') or '').strip()
        if not paciente and not procedimento:
            avisos.append(f'Linha {num}: paciente/procedimento vazio — ignorada.')
            continue
        if not data:
            avisos.append(f'Linha {num}: data inválida — ignorada.')
            continue
        if valor <= 0:
            avisos.append(f'Linha {num}: valor zero ou inválido — ignorada.')
            continue

        modalidade = str(_cel(row, col_map, 'modalidade') or '').strip()
        viabilidade = str(_cel(row, col_map, 'viabilidade') or '').strip()
        forma_pg = str(_cel(row, col_map, 'forma_pagamento') or '').strip()
        regra_txt = str(_cel(row, col_map, 'regra') or '').strip()

        regra_id = regra_padrao_id
        regra_nome = ''
        if regra_txt and empresa_id:
            regra = _resolver_regra(empresa_id, regra_txt, regra_cache)
            if regra:
                regra_id = regra.id
                regra_nome = str(regra)
            else:
                avisos.append(f'Linha {num}: regra «{regra_txt}» não encontrada — ignorada.')
                continue
        elif regra_padrao_id and empresa_id:
            regra = _resolver_regra(empresa_id, str(regra_padrao_id), regra_cache)
            if regra:
                regra_nome = str(regra)

        if not regra_id:
            avisos.append(f'Linha {num}: sem regra de rateio — ignorada.')
            continue

        nf = _extrair_nf_forma_pagamento(forma_pg)
        a_faturar = _a_faturar(forma_pg)

        linhas.append(
            {
                'linha': num,
                'data': data.isoformat(),
                'paciente': paciente,
                'procedimento': procedimento,
                'modalidade': modalidade,
                'viabilidade': viabilidade,
                'forma_pagamento': forma_pg,
                'nf': nf,
                'valor': str(valor),
                'valor_rateio': str(valor_rateio),
                'regra_id': regra_id,
                'regra_txt': regra_txt,
                'regra_nome': regra_nome,
                'a_faturar': a_faturar,
            }
        )

    if not linhas:
        avisos.append('Nenhuma linha válida encontrada.')
    return linhas, avisos


def validar_linhas_importacao(empresa_id: int, linhas: list[dict]) -> tuple[list[dict], list[str]]:
    erros = []
    regra_cache: dict = {}
    itens_cache: dict = {}
    preview_cache: dict = {}
    for ln in linhas:
        ln['valido'] = True
        ln['preview_rateio'] = []
        ln['motivo_invalido'] = ''

        regra = _resolver_regra(empresa_id, str(ln['regra_id']), regra_cache)
        if not regra:
            ln['valido'] = False
            ln['motivo_invalido'] = 'Regra inválida'
            erros.append(f"Linha {ln['linha']}: regra de rateio inválida.")
            continue

        if regra.id not in itens_cache:
            itens_cache[regra.id] = list(
                RegraRateioItem.objects.filter(regrarateio=regra).select_related('socios')
            )
        itens = itens_cache[regra.id]
        if not itens:
            ln['valido'] = False
            ln['motivo_invalido'] = 'Regra sem sócios'
            erros.append(f"Linha {ln['linha']}: regra «{regra}» sem sócios cadastrados.")
            continue
        if _regra_usa_valor_manual(regra, itens):
            ln['valido'] = False
            ln['motivo_invalido'] = 'Regra exige valor manual'
            erros.append(
                f"Linha {ln['linha']}: regra «{regra}» usa valor na aplicação — "
                'use o modal «Contas a receber» para informar valores manuais.'
            )
            continue

        base = Decimal(ln['valor'])
        prev_key = (regra.id, str(base))
        if prev_key not in preview_cache:
            preview_cache[prev_key] = preview_linhas_rateio_por_regra(
                regra.id,
                base,
                LancamentoRateio.TIPO_RECEBIMENTO,
                empresa_id=empresa_id,
            )
        prev = preview_cache[prev_key]
        ln['preview_rateio'] = prev
        ln['regra_nome'] = str(regra)

        vr_plan = Decimal(ln.get('valor_rateio') or ln['valor'])
        soma_prev = sum(Decimal(p['valor']) for p in prev)
        if not prev:
            ln['valido'] = False
            ln['motivo_invalido'] = 'Rateio zerado'
            erros.append(f"Linha {ln['linha']}: preview do rateio vazio.")
        elif abs(soma_prev - vr_plan) > Decimal('0.05'):
            erros.append(
                f"Linha {ln['linha']}: VALOR DO RATEIO ({vr_plan}) difere da soma calculada ({soma_prev})."
            )

        if ln.get('a_faturar'):
            ln['motivo_invalido'] = 'A FATURAR'
            # Importa mesmo assim: título pendente + rateio na data do exame

    return linhas, erros


def _importar_linha_receita(
    empresa_id: int,
    ln: dict,
    *,
    regra_cache: dict,
    itens_cache: dict,
    cobranca_cache: dict,
    nota_cache: dict,
) -> tuple[int, int, int, list[str]]:
    """Importa uma linha. Retorna (car_criados, lr_criados, ignorados, erros)."""
    if not ln.get('valido', True):
        return 0, 0, 1, []

    data = date.fromisoformat(ln['data'])
    valor = Decimal(ln['valor'])
    paciente = ln.get('paciente') or ''
    procedimento = ln.get('procedimento') or ''
    modalidade = ln.get('modalidade') or ''
    viabilidade = ln.get('viabilidade') or ''
    forma_txt = ln.get('forma_pagamento') or ''
    nf = ln.get('nf') or ''
    a_faturar = ln.get('a_faturar', False)

    regra = _resolver_regra(empresa_id, str(ln['regra_id']), regra_cache)
    if not regra:
        return 0, 0, 1, []

    obs = _montar_observacao(paciente, procedimento, modalidade, viabilidade)
    dup_q = ContaAReceber.objects.filter(
        empresa_id=empresa_id,
        valor_a_receber=valor,
        observacao=obs,
    )
    if a_faturar:
        dup_q = dup_q.filter(data_emissao=data, status='pendente')
    else:
        dup_q = dup_q.filter(data_recebimento=data, status='pago')
    if dup_q.exists():
        return 0, 0, 1, []

    nota = _nota_por_numero(empresa_id, nf, nota_cache)
    cobranca = _resolver_cobranca(forma_txt, cobranca_cache)
    cliente = (viabilidade or paciente or 'Importação planilha')[:200]

    if a_faturar:
        status = 'pendente'
        data_receb = None
        valor_recebido = Decimal('0')
    else:
        status = 'pago'
        data_receb = data
        valor_recebido = valor

    if regra.id not in itens_cache:
        itens_cache[regra.id] = list(
            RegraRateioItem.objects.filter(regrarateio=regra).select_related('socios')
        )
    itens = itens_cache[regra.id]

    car = ContaAReceber.objects.create(
        empresa_id=empresa_id,
        nota=nota,
        socio=nota.socio if nota and nota.socio_id else None,
        cliente=cliente,
        data_emissao=data,
        data_vencimento=data,
        data_recebimento=data_receb,
        valor_a_receber=valor,
        valor_recebido=valor_recebido,
        status=status,
        doc=(nf or forma_txt)[:50] or None,
        observacao=obs,
        forma_pagamento=cobranca,
        regra_rateio=regra,
    )

    try:
        n = _gerar_linhas_rateio_conta_receber(car, regra, itens)
    except ValueError as exc:
        car.delete()
        return 0, 0, 0, [f"Linha {ln['linha']}: {exc}"]

    return 1, n, 0, []


def importar_receitas_planilha_lote(
    empresa_id: int,
    linhas: list[dict],
    offset: int = 0,
    batch_size: int = IMPORTACAO_LOTE_TAMANHO,
) -> dict:
    """Importa um lote de linhas válidas (para evitar timeout HTTP)."""
    valid = linhas_validas_para_importacao(linhas)
    batch = valid[offset : offset + batch_size]

    regra_cache: dict = {}
    itens_cache: dict = {}
    cobranca_cache: dict = {}
    nota_cache: dict = {}

    criados_car = 0
    criados_lr = 0
    ignorados = 0
    erros: list[str] = []

    for ln in batch:
        c_car, c_lr, ign, errs = _importar_linha_receita(
            empresa_id,
            ln,
            regra_cache=regra_cache,
            itens_cache=itens_cache,
            cobranca_cache=cobranca_cache,
            nota_cache=nota_cache,
        )
        criados_car += c_car
        criados_lr += c_lr
        ignorados += ign
        erros.extend(errs)

    next_offset = offset + batch_size if offset + batch_size < len(valid) else None
    return {
        'criados_car': criados_car,
        'criados_lr': criados_lr,
        'ignorados': ignorados,
        'erros': erros,
        'next_offset': next_offset,
        'total_validas': len(valid),
        'processadas_ate': min(offset + batch_size, len(valid)),
    }


def importar_receitas_planilha(empresa_id: int, linhas: list[dict]) -> dict:
    """Importa todas as linhas em lotes (uso local / testes)."""
    offset = 0
    totais = {'criados_car': 0, 'criados_lr': 0, 'ignorados': 0, 'erros': []}
    while True:
        lote = importar_receitas_planilha_lote(empresa_id, linhas, offset=offset)
        totais['criados_car'] += lote['criados_car']
        totais['criados_lr'] += lote['criados_lr']
        totais['ignorados'] += lote['ignorados']
        totais['erros'].extend(lote['erros'])
        if lote['next_offset'] is None:
            break
        offset = lote['next_offset']
    return totais


def gerar_modelo_receita_planilha_excel() -> HttpResponse:
    if MODELO_PLANILHA_PATH.is_file():
        content = MODELO_PLANILHA_PATH.read_bytes()
        filename = 'modelo_importar_receita.xlsx'
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = 'Planilha1'
        ws.append(list(COLUNAS_MODELO))
        ws.append([
            '01/07/2026',
            'LUZIA BARBOSA DE ASSIS GUEDES',
            'US - Abdome total',
            'US',
            'BRADESCO SAUDE S.A.',
            'A FATURAR',
            100,
            '100% USG',
            100,
        ])
        buf = BytesIO()
        wb.save(buf)
        content = buf.getvalue()
        filename = 'modelo_importar_receita.xlsx'

    response = HttpResponse(
        content,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
