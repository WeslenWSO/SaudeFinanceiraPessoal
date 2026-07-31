#!/usr/bin/env python
"""Gera tabela_preco_pp.tsv a partir do OCR do PDF PP Saúde."""
from __future__ import annotations

import re
import sys
from pathlib import Path

OCR_DEFAULT = Path(__file__).resolve().parent / "dados" / "pp_ocr_raw.txt"
TSV_DEFAULT = Path(__file__).resolve().parent / "dados" / "tabela_preco_pp.tsv"

CODE_RE = re.compile(r"^(\d{8})$")
VALOR_LINE_RE = re.compile(
    r"(?:R\$|RS|Rs)\s*([\d.,]+)|^([\d]{1,3}[,.]\d{2})$",
    re.I,
)
SKIP_RE = re.compile(
    r"^(=== PAGE|PP SAUDE|COCPERATIVA|SCRWIDONES|Sua Satide|Alameda|CEP:|Acre|"
    r"CNPJ|CODIGO|PROCEDIMENTO|CONTRASTE|C/|S/|VALOR|PREPARO|Trazer|anteriores|"
    r"gestacao|Jejum|Bexiga|Obs\.|EXAME|UNITARIA|CONJUNTO|N\"|EXAMES DE|"
    r"s/ preparo|Terceiro|inicio da|semamas|horarios|Ate I ano|ANTES|BIOPSIA|"
    r"Obs\.:|mapeamento|SUPERIORES|INFERIORES|VASCULAR|lesoes|orientar|"
    r"^\d{2}$|^RX$|^MG$|^RS$|^R\$$)",
    re.I,
)

TC_NOMES: dict[str, str] = {
    "41001010": "TC - CRANIO OU SELA TURCICA OU ORBITAS",
    "41001028": "TC - MASTOIDES OU ORELHAS",
    "41001036": "TC - FACE OU SEIOS DA FACE",
    "41001044": "TC - ARTICULACOES TEMPOROMANDIBULARES",
    "41001060": "TC - PESCOCO (PARTES MOLES, LARINGE, TIREOIDE E FARINGE)",
    "41001079": "TC - TORAX",
    "41001095": "TC - ABDOME TOTAL (RETROPERITONIO)",
    "41001109": "TC - ABDOME SUPERIOR",
    "41001117": "TC - PELVE OU BACIA",
    "41001125": "TC - COLUNA CERVICAL OU DORSAL OU LOMBO-SACRA",
    "41001141": "TC - ARTICULACAO (UNILATERAL)",
    "41001150": "TC - SEGMENTO APENDICULAR (UNILATERAL)",
    "41001362": "TC - VIAS URINARIAS (APARELHO URINARIO)",
    "41001168": "ANGIO-TC CRANIO",
    "41001370": "ANGIOTOMOGRAFIA ARTERIAL DE CRANIO",
    "41001389": "ANGIOTOMOGRAFIA VENOSA DE CRANIO",
    "41001397": "ANGIOTOMOGRAFIA ARTERIAL DE PESCOCO",
    "41001400": "ANGIOTOMOGRAFIA VENOSA DE PESCOCO",
    "41001419": "ANGIOTOMOGRAFIA ARTERIAL DE TORAX",
    "41001435": "ANGIOTOMOGRAFIA ARTERIAL DE ABDOME SUPERIOR",
    "41001443": "ANGIOTOMOGRAFIA VENOSA DE ABDOME SUPERIOR",
}

TC_PRECOS: dict[str, tuple[str, str]] = {
    "41001010": ("350.00", "520.00"),
    "41001028": ("350.00", "520.00"),
    "41001036": ("350.00", "520.00"),
    "41001044": ("350.00", "520.00"),
    "41001060": ("350.00", "520.00"),
    "41001079": ("350.00", "520.00"),
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
    "41001443": ("700.00", "700.00"),
}


def _parse_valor_str(raw: str) -> str:
    s = re.sub(r"[^\d.,]", "", raw.strip())
    s = s.replace(",.", ".").replace(".,", ".")
    if not s:
        return ""
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    return s


def _extract_valor(line: str) -> str | None:
    line = line.strip()
    if SKIP_RE.match(line) or line in ("RX", "MG", "RS", "R$"):
        return None
    m = VALOR_LINE_RE.search(line)
    if m:
        raw = next(g for g in m.groups() if g)
        v = _parse_valor_str(raw)
        return v or None
    cleaned = re.sub(r"[^\d.,]", "", line)
    cleaned = cleaned.replace(",.", ".").replace(".,", ".")
    if re.fullmatch(r"\d+[.,]\d{2}", cleaned) or re.fullmatch(r"\d+\.\d{2}", cleaned):
        return _parse_valor_str(cleaned)
    return None


def _is_desc(line: str) -> bool:
    s = line.strip()
    if not s or SKIP_RE.match(s) or CODE_RE.match(s):
        return False
    if s in ("RX", "MG", "RS", "R$"):
        return False
    if _extract_valor(s) and len(s) < 20:
        return False
    return True


def _pair_prices(vals: list[str]) -> tuple[str, str]:
    if not vals:
        return "", ""
    if len(vals) == 1:
        return vals[0], vals[0]
    d = [float(v) for v in vals[:2]]
    return str(min(d)), str(max(d))


def _parse_tc_section(lines: list[str]) -> list[tuple[str, str, str, str]]:
    out: list[tuple[str, str, str, str]] = []
    for code, (sem, com) in TC_PRECOS.items():
        nome = TC_NOMES.get(code, f"Servico {code}")
        out.append((code, nome, sem, com))
    return out


def _parse_rx_section(lines: list[str]) -> list[tuple[str, str, str, str]]:
    n = len(lines)
    code_hits: list[tuple[int, str]] = []
    for i, raw in enumerate(lines):
        m = CODE_RE.match(raw.strip())
        if m and m.group(1).startswith("408"):
            code_hits.append((i, m.group(1)))

    used_price_lines: set[int] = set()
    records: dict[str, dict[str, str]] = {}
    order: list[str] = []

    for idx, (line_no, code) in enumerate(code_hits):
        prev_line = code_hits[idx - 1][0] if idx else -1
        next_line = code_hits[idx + 1][0] if idx + 1 < len(code_hits) else n

        desc_parts: list[str] = []
        price: str | None = None
        price_line: int | None = None

        for j in range(max(0, line_no - 4), min(n, next_line)):
            if j == line_no:
                continue
            line = lines[j].strip()
            if not price and j not in used_price_lines:
                v = _extract_valor(line)
                if v:
                    price = v
                    price_line = j
            if _is_desc(line):
                desc_parts.append(line)

        if price_line is not None:
            used_price_lines.add(price_line)

        nome = " ".join(desc_parts).strip()
        if nome.upper().startswith("RX"):
            nome = nome
        elif nome and not nome.startswith("RX"):
            nome = f"RX - {nome}" if not nome.startswith("RX") else nome

        if code in records:
            rec = records[code]
            if nome and len(nome) > len(rec.get("nome", "")):
                rec["nome"] = nome[:200]
            if price and not rec.get("sem"):
                rec["sem"] = rec["com"] = price
        else:
            records[code] = {"nome": nome[:200], "sem": price or "", "com": price or ""}
            order.append(code)

    out: list[tuple[str, str, str, str]] = []
    for code in order:
        rec = records[code]
        if not rec["sem"]:
            continue
        nome = rec["nome"] or f"RX - Servico {code}"
        out.append((code, nome, rec["sem"], rec["com"]))
    return out


def parse_ocr(text: str) -> list[tuple[str, str, str, str]]:
    all_lines = text.splitlines()
    page2 = next((i for i, l in enumerate(all_lines) if "=== PAGE 2 ===" in l), len(all_lines))
    page4 = next((i for i, l in enumerate(all_lines) if "=== PAGE 4 ===" in l), len(all_lines))

    tc_rows = _parse_tc_section(all_lines[:page2])
    rx_rows = _parse_rx_section(all_lines[page2:page4])

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
            merged[code] = (code, nome, row[2] or old[2], row[3] or old[3])

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
    print(f"TC: {tc} | RX/MG: {rx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
