#!/usr/bin/env python
"""Gera tabela_preco_postal.tsv a partir do OCR do PDF Postal Saúde."""
from __future__ import annotations

import re
import sys
from pathlib import Path

OCR_DEFAULT = Path(__file__).resolve().parent / "dados" / "postal_ocr_raw.txt"
TSV_DEFAULT = Path(__file__).resolve().parent / "dados" / "tabela_preco_postal.tsv"

CBHPM_RE = re.compile(
    r"(\d)\.(\d{1,2})\.(\d{1,2})\.(\d{2,3}[a-zA-Z\[\]]?)"
)
SKIP_RE = re.compile(
    r"^(=== PAGE|Convenio|CNPJ|MEDICINARTE|Valor|Descricao|Evento|\d{2}\.\d{3}\.\d{3}/)",
    re.I,
)


def _fix_ocr_code(match: re.Match[str]) -> str:
    g1, g2, g3, g4 = match.groups()
    g2 = g2.zfill(2)
    g3 = g3.zfill(2)
    g4 = re.sub(r"[^0-9]", "", g4.replace("o", "0").replace("O", "0"))
    if len(g4) == 3:
        digits = f"{g1}{g2}{g3}{g4}"
        return digits[:8].zfill(8)
    return f"{g1}{g2}{g3}{g4.zfill(2)}"


def _normalize_line(line: str) -> str:
    return line.replace("4.0.01.", "4.10.01.").replace("4.09.1.", "4.09.01.")


def _extract_codes(line: str) -> list[tuple[str, str]]:
    line = _normalize_line(line)
    out: list[tuple[str, str]] = []
    for m in CBHPM_RE.finditer(line):
        code = _fix_ocr_code(m)
        rest = line[m.end() :].strip()
        if len(code) == 8 and code.isdigit():
            out.append((code, rest))
    return out


def _is_valor(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 14 or CBHPM_RE.search(_normalize_line(s)):
        return False
    cleaned = re.sub(r"[^\d.,]", "", s)
    if not cleaned or not re.fullmatch(r"[\d.,]+", cleaned):
        return False
    return bool(re.search(r"[,.]", cleaned))


def _parse_valor(line: str) -> str:
    s = re.sub(r"[^\d.,]", "", line.strip())
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        parts = s.split(".")
        s = "".join(parts[:-1]) + "." + parts[-1]
    return s


def _is_desc(line: str) -> bool:
    s = line.strip()
    if not s or SKIP_RE.match(s):
        return False
    if _is_valor(s):
        return False
    if _extract_codes(s):
        return False
    return True


def parse_ocr(text: str) -> list[tuple[str, str, str]]:
    lines = text.splitlines()
    n = len(lines)

    code_hits: list[tuple[int, str, str]] = []
    valor_hits: list[tuple[int, str]] = []
    desc_by_line: dict[int, str] = {}

    for i, raw in enumerate(lines):
        line = raw.strip()
        if not line or SKIP_RE.match(line):
            continue
        for code, rest in _extract_codes(line):
            code_hits.append((i, code, rest))
        if _is_valor(line):
            valor_hits.append((i, _parse_valor(line)))
        elif _is_desc(line):
            desc_by_line[i] = line

    used_valor: set[int] = set()
    records: dict[str, dict[str, str]] = {}
    order: list[str] = []

    for idx, (line_no, code, inline_desc) in enumerate(code_hits):
        prev_line = code_hits[idx - 1][0] if idx else -1
        next_line = code_hits[idx + 1][0] if idx + 1 < len(code_hits) else n

        desc_parts: list[str] = []
        if inline_desc and len(inline_desc) > 2:
            desc_parts.append(inline_desc)
        for d_line in range(prev_line + 1, line_no):
            if d_line in desc_by_line:
                desc_parts.append(desc_by_line[d_line])

        # valor mais próximo dentro da janela do registro
        win_start = max(0, line_no - 3)
        win_end = min(n, next_line)
        best_val: tuple[int, str] | None = None
        for v_line, v_str in valor_hits:
            if v_line in used_valor:
                continue
            if win_start <= v_line <= win_end:
                dist = abs(v_line - line_no)
                if best_val is None or dist < best_val[0]:
                    best_val = (dist, v_str, v_line)

        if best_val is None:
            for v_line, v_str in valor_hits:
                if v_line in used_valor:
                    continue
                if prev_line < v_line < next_line:
                    dist = abs(v_line - line_no)
                    if best_val is None or dist < best_val[0]:
                        best_val = (dist, v_str, v_line)

        nome = " ".join(desc_parts).strip()[:200]
        valor = best_val[1] if best_val else ""
        if best_val:
            used_valor.add(best_val[2])

        if code in records:
            if valor and not records[code]["valor"]:
                records[code]["valor"] = valor
            if nome and len(nome) > len(records[code]["nome"]):
                records[code]["nome"] = nome
        else:
            records[code] = {"nome": nome, "valor": valor}
            order.append(code)

    out: list[tuple[str, str, str]] = []
    for code in order:
        rec = records[code]
        if not rec["valor"]:
            continue
        nome = rec["nome"] or f"Servico {code}"
        out.append((code, nome, rec["valor"]))
    return out


def main() -> int:
    ocr_path = Path(sys.argv[1]) if len(sys.argv) > 1 else OCR_DEFAULT
    tsv_path = Path(sys.argv[2]) if len(sys.argv) > 2 else TSV_DEFAULT

    if not ocr_path.is_file():
        print(f"OCR não encontrado: {ocr_path}", file=sys.stderr)
        return 1

    rows = parse_ocr(ocr_path.read_text(encoding="utf-8"))
    lines = ["codigo\tnome\tvalor"]
    for codigo, nome, valor in rows:
        nome = nome.replace("\t", " ")
        lines.append(f"{codigo}\t{nome}\t{valor}")

    tsv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Registros: {len(rows)} -> {tsv_path}")
    sem_nome = sum(1 for _, n, _ in rows if n.startswith("Servico "))
    sem_valor_skip = len(rows)
    print(f"Sem descrição OCR: {sem_nome}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
