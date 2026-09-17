"""Gera JSONs de catálogos fiscais NFS-e (Anexo VII/VIII) a partir do pacote nfse-nacional."""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand

TABELAS_URL = 'https://cdn.jsdelivr.net/npm/nfse-nacional@0.3.0/dist/tabelas.js'
OUT_DIR = Path(__file__).resolve().parents[2] / 'conta_azul' / 'dados'

INDICADOR_DESCRICOES = {
    '010100': 'Bem móvel material | Local da entrega ou disponibilização',
    '010101': 'Bem móvel material | Presencial com retirada no estabelecimento do fornecedor',
    '030101': 'Serviço prestado fisicamente | Estabelecimento do fornecedor',
    '030102': 'Serviço prestado fisicamente | Endereço do adquirente',
    '050101': 'Serviço não oneroso | Estabelecimento do fornecedor',
    '050102': 'Serviço não oneroso | Endereço do adquirente',
    '050103': 'Serviço não oneroso | Local da prestação',
    '050104': 'Serviço não oneroso | Outros',
    '100301': 'Demais serviços onerosos | Domicílio do adquirente no País',
    '100501': 'Serviços por meio de plataforma digital | Domicílio do adquirente',
}


def _format_nbs(raw: str) -> str:
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) >= 9:
        return f'{digits[0]}.{digits[1:5]}.{digits[5:7]}.{digits[7:9]}'
    return raw


def _decode_js_string_escapes(raw: str) -> str:
    def _repl(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 16))

    return re.sub(r'\\x([0-9a-fA-F]{2})', _repl, raw)


def _extract_js_array(text: str, var_name: str) -> list:
    marker = f'var {var_name} = '
    start = text.find(marker)
    if start < 0:
        return []
    start = text.find('[', start)
    depth = 0
    for idx in range(start, len(text)):
        ch = text[idx]
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                bloco = _decode_js_string_escapes(text[start : idx + 1])
                return json.loads(bloco)
    return []


class Command(BaseCommand):
    help = 'Baixa tabelas IBS/CBS (Anexo VIII) e grava JSONs em dashboard/conta_azul/dados/.'

    def handle(self, *args, **options):
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        self.stdout.write(f'Baixando {TABELAS_URL}...')
        with urllib.request.urlopen(TABELAS_URL, timeout=120) as resp:
            text = resp.read().decode('utf-8')

        cst_table = _extract_js_array(text, 'IBS_CBS_CST_TABLE')
        anexo = _extract_js_array(text, 'IBS_CBS_ANEXO_VIII')

        c_class: list[dict] = []
        for cst in cst_table:
            cst_cod = cst.get('cst', '')
            cst_desc = cst.get('descricao', '')
            for cls in cst.get('classes') or []:
                codigo = cls.get('codigo', '')
                desc = cls.get('descricao', '')
                c_class.append({
                    'codigo': codigo,
                    'descricao': desc,
                    'cst': cst_cod,
                    'cst_descricao': cst_desc,
                    'label': f'{codigo} - {cst_desc} | {desc}'[:500],
                })

        ind_ops: dict[str, dict] = {}
        nbs_map: dict[str, dict] = {}
        itens_lc116: dict[str, dict] = {}
        correlacoes: list[dict] = []

        for row in anexo:
            item = str(row.get('item') or '').strip()
            nbs_raw = str(row.get('nbs') or '').strip()
            c_ind = str(row.get('cIndOp') or '').strip()
            c_class_trib = str(row.get('cClassTrib') or '').strip()
            if item:
                cod_mun = item.zfill(6) if len(item) <= 6 else item
                itens_lc116.setdefault(item, {
                    'codigo': cod_mun,
                    'item_lc116': item,
                    'label': f'{cod_mun} | Item LC 116 {item[:2]}.{item[2:]}',
                })
            if c_ind and c_ind not in ind_ops:
                desc = INDICADOR_DESCRICOES.get(c_ind, f'Indicador de operação {c_ind}')
                ind_ops[c_ind] = {
                    'codigo': c_ind,
                    'descricao': desc,
                    'label': f'{c_ind} - {desc}',
                }
            if nbs_raw:
                codigo = _format_nbs(nbs_raw)
                nbs_map.setdefault(codigo, {
                    'codigo': codigo,
                    'nbs_raw': nbs_raw,
                    'label': codigo,
                })
            if item and nbs_raw and c_ind and c_class_trib:
                correlacoes.append({
                    'item_lc116': item,
                    'codigo_nbs': _format_nbs(nbs_raw),
                    'indicador_operacao': c_ind,
                    'c_class_trib': c_class_trib,
                    'onerosa': bool(row.get('onerosa', True)),
                })

        natureza = [
            {'codigo': '1', 'label': 'Operação tributável', 'descricao': 'Operação tributável'},
            {'codigo': '2', 'label': 'Imunidade', 'descricao': 'Imunidade'},
            {'codigo': '3', 'label': 'Exportação de serviço', 'descricao': 'Exportação de serviço'},
            {'codigo': '4', 'label': 'Não Incidência', 'descricao': 'Não Incidência'},
        ]

        payloads = {
            'natureza_operacao.json': natureza,
            'c_class_trib.json': c_class,
            'indicador_operacao.json': sorted(ind_ops.values(), key=lambda x: x['codigo']),
            'nbs.json': sorted(nbs_map.values(), key=lambda x: x['codigo']),
            'codigo_servico_lc116.json': sorted(itens_lc116.values(), key=lambda x: x['codigo']),
            'correlacao_lc116_ibscbs.json': correlacoes,
        }

        for nome, dados in payloads.items():
            path = OUT_DIR / nome
            path.write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(f'{nome}: {len(dados)} registro(s)'))
