# nfse_rio_branco/services/exporters.py
from __future__ import annotations
import json, csv
from pathlib import Path
from django.db.models import QuerySet
from SaudeFinanceira.nfse_rio_branco.models import Nfse

def export_json(qs: QuerySet[Nfse], outfile: Path) -> Path:
    data = []
    for n in qs:
        data.append({
             "numero": n.numero,
             "serie": n.serie,
             "codigo_verificacao": n.codigo_verificacao,
             "data_emissao": n.data_emissao.isoformat() if n.data_emissao else None,
             "competencia": n.competencia,
             "valor_servico": float(n.valor_servico),
             "iss_retido": n.iss_retido,
             "prestador_cnpj": n.prestador_cnpj,
             "tomador_cnpj_cpf": n.tomador_cnpj_cpf,
             "xml": n.xml,
        })
    outfile.parent.mkdir(parents=True, exist_ok=True)
    outfile.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return outfile


def export_csv(qs: QuerySet[Nfse], outfile: Path) -> Path:
     outfile.parent.mkdir(parents=True, exist_ok=True)
     with outfile.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(["numero","serie","codigo_verificacao","data_emissao","competencia","valor_servico","iss_retido","prestador_cnpj","tomador_cnpj_cpf"])
        for n in qs:
            w.writerow([
               n.numero, n.serie or "", n.codigo_verificacao or "",
               n.data_emissao.isoformat() if n.data_emissao else "",
               n.competencia or "", f"{n.valor_servico:.2f}",
               int(n.iss_retido), n.prestador_cnpj or "", n.tomador_cnpj_cpf or ""
            ])
     return outfile