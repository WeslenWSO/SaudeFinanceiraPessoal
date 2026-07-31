#!/usr/bin/env python
"""Gera tabela_preco_bombeiro.tsv a partir do OCR do PDF CB Saúde (Bombeiro)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

OCR_DEFAULT = Path(__file__).resolve().parent / "dados" / "cbsaude_ocr_raw.txt"
TSV_DEFAULT = Path(__file__).resolve().parent / "dados" / "tabela_preco_bombeiro.tsv"

CODE_RE = re.compile(r"^(\d{8})$")
VALOR_LINE_RE = re.compile(
    r"^(?:R\$|RS|Rs|F\$)\s*([\d.,]+)|^R\$\s*([\d.,]+)",
    re.I,
)
SKIP_RE = re.compile(
    r"^(=== PAGE|SAUDE|Cooperativa|CNPJ|CNPJ\.|CNP109|CNP J|TABELA|SEM|COM|"
    r"CONTRASTE|ConTrAsTe|PROCEDIMENTO|VALOR|PROPOSTO|ANEXO|MEDICINARTE|"
    r"CONTRATADO|CONTRATANTE|DIRETOR|MARCIO|IVONALDO|ANTONIO|CPF|LTDA|"
    r"CORRESPONDENTE|COLUNA\)|ANEURISMA|DISSECCAO|EXAME\(|EXAME EM|"
    r"Rrimgot|5ocad|\d{2}$)",
    re.I,
)

# Nomes oficiais RX (Anexo 2) para códigos cujo OCR perdeu descrição/preço
RX_NOMES: dict[str, str] = {
    "40801047": "RX - ORELHA, MASTOIDES OU ROCHEDOS - BILATERAL",
    "40801063": "RX - SEIOS DA FACE",
    "40801101": "RX - ARCOS ZIGOMATICOS OU MALAR OU APOFISES ESTILOIDES",
    "40802094": "RX - COLUNA TOTAL PARA ESCOLIOSE (TELESPONDILOGRAFIA)",
    "40804020": "RX - ARTICULACOES SACROILIACAS",
    "40804070": "RX - PERNA",
}

TC_NOMES: dict[str, str] = {
    "41001010": "TC - CRANIO OU SELA TURCICA OU ORBITAS",
    "41001028": "TC - MASTOIDES OU ORELHAS",
    "41001036": "TC - FACE OU SEIOS DA FACE",
    "41001044": "TC - ARTICULACOES TEMPOROMANDIBULARES",
    "41001052": "TC - DENTAL (DENTASCAN)",
    "41001060": "TC - PESCOCO (PARTES MOLES, LARINGE, TIREOIDE E FARINGE)",
    "41001079": "TC - TORAX",
    "41001087": "TC - CORACAO - ESCORE DE CALCIO",
    "41001095": "TC - ABDOME TOTAL (ABDOME SUPERIOR, PELVE E RETROPERITONIO)",
    "41001109": "TC - ABDOME SUPERIOR",
    "41001117": "TC - PELVE OU BACIA",
    "41001125": "TC - COLUNA CERVICAL OU DORSAL OU LOMBO-SACRA",
    "41001141": "TC - ARTICULACAO (UNILATERAL)",
    "41001150": "TC - SEGMENTO APENDICULAR (UNILATERAL)",
    "41001362": "TC - VIAS URINARIAS (UROTC)",
    "41001168": "ANGIO-TC CRANIO",
    "41001370": "ANGIOTOMOGRAFIA ARTERIAL DE CRANIO",
    "41001389": "ANGIOTOMOGRAFIA VENOSA DE CRANIO",
    "41001397": "ANGIOTOMOGRAFIA ARTERIAL DE PESCOCO",
    "41001400": "ANGIOTOMOGRAFIA VENOSA DE PESCOCO",
    "41001419": "ANGIOTOMOGRAFIA ARTERIAL DE TORAX",
    "41001435": "ANGIOTOMOGRAFIA ARTERIAL DE ABDOME SUPERIOR",
    "41001443": "ANGIOTOMOGRAFIA VENOSA DE ABDOME SUPERIOR",
}

# Preços TC (sem/com contraste) conforme tabela OCR página 1
TC_PRECOS: dict[str, tuple[str, str]] = {
    "41001010": ("350.00", "520.00"),
    "41001028": ("350.00", "520.00"),
    "41001036": ("350.00", "520.00"),
    "41001044": ("350.00", "520.00"),
    "41001060": ("350.00", "520.00"),
    "41001079": ("450.00", "600.00"),
    "41001095": ("450.00", "600.00"),
    "41001109": ("450.00", "600.00"),
    "41001117": ("450.00", "600.00"),
    "41001125": ("350.00", "520.00"),
    "41001141": ("350.00", "520.00"),
    "41001150": ("350.00", "520.00"),
    "41001362": ("450.00", "600.00"),
    "41001168": ("500.00", "500.00"),
    "41001370": ("500.00", "500.00"),
    "41001389": ("500.00", "500.00"),
    "41001397": ("500.00", "500.00"),
    "41001400": ("500.00", "500.00"),
    "41001419": ("500.00", "500.00"),
    "41001435": ("700.00", "700.00"),
    "41001443": ("500.00", "500.00"),
}


def _parse_valor_str(raw: str) -> str:
    s = re.sub(r"[^\d.,]", "", raw.strip())
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    return s


def _extract_valor(line: str) -> str | None:
    line = line.strip()
    m = VALOR_LINE_RE.match(line)
    if m:
        raw = next(g for g in m.groups() if g)
        return _parse_valor_str(raw)
    if line.upper().startswith("R$") or line.startswith("RS ") or line.startswith("Rs "):
        raw = re.sub(r"^R?\$?\s*", "", line, flags=re.I)
        raw = re.sub(r"[^\d.,]", "", raw)
        if raw:
            return _parse_valor_str(raw)
    return None


def _is_desc(line: str) -> bool:
    s = line.strip()
    if not s or SKIP_RE.match(s) or CODE_RE.match(s):
        return False
    if _extract_valor(s) and len(s) < 25:
        return False
    return True


def _pair_prices(vals: list[str]) -> tuple[str, str]:
    if not vals:
        return "", ""
    if len(vals) == 1:
        return vals[0], vals[0]
    d = [float(v) for v in vals[:2]]
    return str(min(d)), str(max(d))


def _parse_section(lines: list[str], tc_mode: bool) -> list[tuple[str, str, str, str]]:
    n = len(lines)
    code_hits: list[tuple[int, str]] = []
    valor_by_line: dict[int, str] = {}
    desc_by_line: dict[int, str] = {}

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or line.startswith("=== PAGE"):
            continue
        m = CODE_RE.match(line)
        if m:
            code_hits.append((i, m.group(1)))
            continue
        val = _extract_valor(line)
        if val:
            valor_by_line[i] = val
        elif _is_desc(line):
            desc_by_line[i] = line

    used_valor: set[int] = set()
    records: dict[str, dict[str, str]] = {}
    order: list[str] = []

    for idx, (line_no, code) in enumerate(code_hits):
        prev_line = code_hits[idx - 1][0] if idx else -1
        next_line = code_hits[idx + 1][0] if idx + 1 < len(code_hits) else n

        desc_parts: list[str] = []
        for d_line in range(prev_line + 1, line_no):
            if d_line in desc_by_line:
                desc_parts.append(desc_by_line[d_line])
        for d_line in range(line_no + 1, min(next_line, line_no + 3)):
            if d_line in desc_by_line:
                desc_parts.append(desc_by_line[d_line])

        vals: list[str] = []
        for v_line in range(max(0, line_no - 2), min(n, next_line)):
            if v_line in valor_by_line and v_line not in used_valor:
                vals.append((v_line, valor_by_line[v_line]))
        vals.sort(key=lambda x: x[0])
        val_strs = [v for _, v in vals[:2]]
        for v_line, _ in vals[:2]:
            used_valor.add(v_line)

        sem, com = _pair_prices(val_strs)
        nome = " ".join(desc_parts).strip()[:200]
        ref = TC_NOMES if tc_mode else RX_NOMES
        if code in ref:
            nome = ref[code]

        if code in records:
            rec = records[code]
            if nome and (not rec["nome"] or rec["nome"].startswith("Servico")):
                rec["nome"] = nome
            if sem and not rec["sem"]:
                rec["sem"], rec["com"] = sem, com
        else:
            records[code] = {"nome": nome, "sem": sem, "com": com}
            order.append(code)

    out: list[tuple[str, str, str, str]] = []
    for code in order:
        rec = records[code]
        if not rec["sem"]:
            if code in RX_NOMES:
                rec["sem"] = rec["com"] = "40.00"
            else:
                continue
        nome = rec["nome"] or RX_NOMES.get(code) or TC_NOMES.get(code) or f"Servico {code}"
        out.append((code, nome[:200], rec["sem"], rec["com"]))
    return out


def parse_ocr(text: str) -> list[tuple[str, str, str, str]]:
    all_lines = text.splitlines()
    page1_end = next(
        (i for i, l in enumerate(all_lines) if "=== PAGE 2 ===" in l),
        len(all_lines),
    )
    page5_start = next(
        (i for i, l in enumerate(all_lines) if "=== PAGE 5 ===" in l),
        len(all_lines),
    )

    tc_rows = _parse_section(all_lines[:page1_end], tc_mode=True)
    rx_rows = _parse_section(all_lines[page5_start:], tc_mode=False)

    merged: dict[str, tuple[str, str, str, str]] = {}
    order: list[str] = []
    for row in tc_rows + rx_rows:
        code = row[0]
        if code not in merged:
            merged[code] = row
            order.append(code)
        else:
            old = merged[code]
            nome = row[1] if len(row[1]) > len(old[1]) else old[1]
            if row[1] in TC_NOMES.values() or row[1] in RX_NOMES.values():
                nome = row[1]
            merged[code] = (code, nome, row[2] or old[2], row[3] or old[3])

    # TC TORAX: preços fixos da tabela
    for code, (sem, com) in TC_PRECOS.items():
        if code in merged:
            nome = TC_NOMES.get(code, merged[code][1])
            merged[code] = (code, nome, sem, com)
        elif code.startswith("410"):
            merged[code] = (code, TC_NOMES.get(code, f"Servico {code}"), sem, com)
            if code not in order:
                order.insert(0, code)

    return [merged[c] for c in order if merged[c][2]]


def main() -> int:
    ocr_path = Path(sys.argv[1]) if len(sys.argv) > 1 else OCR_DEFAULT
    tsv_path = Path(sys.argv[2]) if len(sys.argv) > 2 else TSV_DEFAULT

    if not ocr_path.is_file():
        print(f"OCR não encontrado: {ocr_path}", file=sys.stderr)
        return 1

    rows = parse_ocr(ocr_path.read_text(encoding="utf-8"))
    lines = ["codigo\tnome\tvalor_sem_contraste\tvalor_com_contraste"]
    for codigo, nome, sem, com in rows:
        lines.append(f"{codigo}\t{nome.replace(chr(9), ' ')}\t{sem}\t{com}")

    tsv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Registros: {len(rows)} -> {tsv_path}")
    tc = sum(1 for c, _, _, _ in rows if c.startswith("410"))
    rx = sum(1 for c, _, _, _ in rows if c.startswith("408"))
    print(f"TC: {tc} | RX: {rx} | outros: {len(rows) - tc - rx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
