#!/usr/bin/env python
"""Compara SQLite local x PostgreSQL (DATABASE_URL) — foco em lançamentos."""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQLITE = ROOT / "db.sqlite3"
OUT = ROOT / "scripts" / "comparacao_sqlite_postgres.json"

sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "SaudeFinanceira.settings")

EMPRESA_ID = 16


def _sqlite_counts() -> Counter:
    c: Counter = Counter()
    if not SQLITE.is_file():
        return c
    conn = sqlite3.connect(SQLITE)
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        for table in tables:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
                if n:
                    c[table] = n
            except sqlite3.Error:
                pass
    finally:
        conn.close()
    return c


def _sqlite_scalar(sql: str, params=()) -> float | int:
    conn = sqlite3.connect(SQLITE)
    try:
        row = conn.execute(sql, params).fetchone()
        return row[0] if row and row[0] is not None else 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def main() -> int:
    if not os.environ.get("DATABASE_URL"):
        url_file = ROOT / "render_db.url"
        if url_file.is_file():
            os.environ["DATABASE_URL"] = url_file.read_text(encoding="utf-8").strip()

    import django
    from django.apps import apps
    from django.db.models import Sum

    django.setup()

    from contasapagar.models import ContasaPagar
    from contasareceber.models import ContaAReceber
    from empresa.models import Empresa
    from extrato.models import Lancamento
    from faturamento_medico.models import FaturamentoMedico, ItemServico
    from planejamento_orcamentario.models import LancamentoOrcamento
    from regrarateio.models import LancamentoRateio

    sq = _sqlite_counts()
    pg: Counter = Counter()
    for model in apps.get_models():
        if model._meta.app_label in {"contenttypes", "admin"}:
            continue
        try:
            n = model.objects.count()
            if n:
                pg[model._meta.db_table] = n
        except Exception:
            pass

    empresa = Empresa.objects.filter(pk=EMPRESA_ID).first()
    empresa_nome = (empresa.nome_fantasia or empresa.razao) if empresa else "Medicinarte"

    def demo(tipo: str, sq_qtd, pg_qtd, sq_valor, pg_valor) -> dict:
        sq_q = int(sq_qtd or 0)
        pg_q = int(pg_qtd or 0)
        sq_v = float(sq_valor or 0)
        pg_v = float(pg_valor or 0)
        return {
            "tipo": tipo,
            "sqlite_qtd": sq_q,
            "postgres_qtd": pg_q,
            "diff_qtd": pg_q - sq_q,
            "sqlite_valor": round(sq_v, 2),
            "postgres_valor": round(pg_v, 2),
            "diff_valor": round(pg_v - sq_v, 2),
            "status": "IGUAL" if sq_q == pg_q and abs(sq_v - pg_v) < 0.01 else "DIFERENTE",
        }

    lanc_demo = [
        demo(
            "Extrato bancário (Lancamento)",
            _sqlite_scalar(
                "SELECT COUNT(*) FROM extrato_lancamento WHERE empresa_id=?", (EMPRESA_ID,)
            ),
            Lancamento.objects.filter(empresa_id=EMPRESA_ID).count(),
            _sqlite_scalar(
                "SELECT COALESCE(SUM(valor),0) FROM extrato_lancamento WHERE empresa_id=?",
                (EMPRESA_ID,),
            ),
            Lancamento.objects.filter(empresa_id=EMPRESA_ID).aggregate(s=Sum("valor"))["s"],
        ),
        demo(
            "Rateio (LancamentoRateio)",
            _sqlite_scalar("SELECT COUNT(*) FROM regrarateio_lancamentorateio"),
            LancamentoRateio.objects.count(),
            _sqlite_scalar("SELECT COALESCE(SUM(valor),0) FROM regrarateio_lancamentorateio"),
            LancamentoRateio.objects.aggregate(s=Sum("valor"))["s"],
        ),
        demo(
            "Orçamento (LancamentoOrcamento)",
            _sqlite_scalar(
                "SELECT COUNT(*) FROM planejamento_orcamentario_lancamentoorcamento WHERE empresa_id=?",
                (EMPRESA_ID,),
            ),
            LancamentoOrcamento.objects.filter(empresa_id=EMPRESA_ID).count(),
            _sqlite_scalar(
                "SELECT COALESCE(SUM(valor),0) FROM planejamento_orcamentario_lancamentoorcamento WHERE empresa_id=?",
                (EMPRESA_ID,),
            ),
            LancamentoOrcamento.objects.filter(empresa_id=EMPRESA_ID).aggregate(s=Sum("valor"))["s"],
        ),
        demo(
            "Contas a receber",
            _sqlite_scalar(
                "SELECT COUNT(*) FROM contasareceber_contaareceber WHERE empresa_id=?",
                (EMPRESA_ID,),
            ),
            ContaAReceber.objects.filter(empresa_id=EMPRESA_ID).count(),
            _sqlite_scalar(
                "SELECT COALESCE(SUM(valor_a_receber),0) FROM contasareceber_contaareceber WHERE empresa_id=?",
                (EMPRESA_ID,),
            ),
            ContaAReceber.objects.filter(empresa_id=EMPRESA_ID).aggregate(s=Sum("valor_a_receber"))["s"],
        ),
        demo(
            "Contas a pagar",
            _sqlite_scalar(
                "SELECT COUNT(*) FROM contasapagar_contasapagar WHERE empresa_id=?",
                (EMPRESA_ID,),
            ),
            ContasaPagar.objects.filter(empresa_id=EMPRESA_ID).count(),
            _sqlite_scalar(
                "SELECT COALESCE(SUM(valorDoc),0) FROM contasapagar_contasapagar WHERE empresa_id=?",
                (EMPRESA_ID,),
            ),
            ContasaPagar.objects.filter(empresa_id=EMPRESA_ID).aggregate(s=Sum("valorDoc"))["s"],
        ),
        demo(
            "Faturamento médico (guias)",
            _sqlite_scalar(
                "SELECT COUNT(*) FROM faturamento_medico_faturamentomedico WHERE empresa_id=?",
                (EMPRESA_ID,),
            ),
            FaturamentoMedico.objects.filter(empresa_id=EMPRESA_ID).count(),
            _sqlite_scalar(
                "SELECT COALESCE(SUM(total),0) FROM faturamento_medico_faturamentomedico WHERE empresa_id=?",
                (EMPRESA_ID,),
            ),
            FaturamentoMedico.objects.filter(empresa_id=EMPRESA_ID).aggregate(s=Sum("total"))["s"],
        ),
        demo(
            "Item serviço (procedimentos)",
            _sqlite_scalar(
                """
                SELECT COUNT(*) FROM faturamento_medico_itemservico i
                JOIN faturamento_medico_faturamentomedico f ON i.faturamento_id = f.id
                WHERE f.empresa_id=?
                """,
                (EMPRESA_ID,),
            ),
            ItemServico.objects.filter(faturamento__empresa_id=EMPRESA_ID).count(),
            _sqlite_scalar(
                """
                SELECT COALESCE(SUM(i.total),0) FROM faturamento_medico_itemservico i
                JOIN faturamento_medico_faturamentomedico f ON i.faturamento_id = f.id
                WHERE f.empresa_id=?
                """,
                (EMPRESA_ID,),
            ),
            ItemServico.objects.filter(faturamento__empresa_id=EMPRESA_ID).aggregate(s=Sum("total"))["s"],
        ),
    ]

    keywords = (
        "lancamento",
        "contas",
        "faturamento",
        "extrato",
        "regrarateio",
        "notasfisc",
        "servicos",
        "fluxo",
        "emprestimo",
    )
    compare = []
    for table in sorted(set(sq) | set(pg), key=str.lower):
        s, p = sq.get(table, 0), pg.get(table, 0)
        if s == 0 and p == 0:
            continue
        if not any(k in table for k in keywords):
            continue
        if s == p:
            status = "IGUAL"
        elif s == 0:
            status = "SÓ PG"
        elif p == 0:
            status = "SÓ SQLITE"
        else:
            status = "DIFERENTE"
        compare.append({"tabela": table, "sqlite": s, "postgres": p, "diff": p - s, "status": status})

    samples = []
    conn = sqlite3.connect(SQLITE)
    try:
        rows = conn.execute(
            """
            SELECT data, historico, valor, documento
            FROM extrato_lancamento
            WHERE empresa_id=? AND data >= '2026-07-01' AND data <= '2026-07-31'
            ORDER BY data DESC, id DESC
            LIMIT 6
            """,
            (EMPRESA_ID,),
        ).fetchall()
        for data, historico, valor, documento in rows:
            samples.append(
                {
                    "origem": "SQLite",
                    "data": data,
                    "historico": (historico or "")[:70],
                    "valor": float(valor or 0),
                    "documento": documento or "",
                }
            )
    except sqlite3.Error:
        pass
    finally:
        conn.close()

    for lanc in Lancamento.objects.filter(
        empresa_id=EMPRESA_ID, data__gte="2026-07-01", data__lte="2026-07-31"
    ).order_by("-data", "-id")[:6]:
        samples.append(
            {
                "origem": "Postgres",
                "data": str(lanc.data),
                "historico": (lanc.historico or "")[:70],
                "valor": float(lanc.valor or 0),
                "documento": lanc.documento or "",
            }
        )

    payload = {
        "empresa": empresa_nome,
        "empresa_id": EMPRESA_ID,
        "sqlite_registros": sum(sq.values()),
        "postgres_registros": sum(pg.values()),
        "lanc_demo": lanc_demo,
        "compare_tables": compare,
        "samples_extrato_jul2026": samples,
        "gerado_em": "2026-07-30",
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
