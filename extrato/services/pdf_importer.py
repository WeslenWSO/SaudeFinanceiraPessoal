import hashlib
from decimal import Decimal
from datetime import datetime
from django.db import IntegrityError

from ..models import Lancamento, ContaBancaria

try:
    import pdfplumber
except Exception:
    pdfplumber = None

def hash_lancamento(conta_id, data, valor, historico, documento):
    base = f"{conta_id}|{data.isoformat()}|{valor}|{(historico or '').strip()}|{(documento or '').strip()}"
    import hashlib as _h
    return _h.sha256(base.encode("utf-8")).hexdigest()

def import_pdf(conta: ContaBancaria, file_obj, extrato_arquivo=None, colmap=None):
    """
    Extrai tabelas de um PDF de extrato.
    extrato_arquivo: opcional, vincula lançamentos à prévia do arquivo (status P).
    colmap: dict opcional para mapear colunas -> ['data','documento','historico','valor']
    Ex: {'date': 'data', 'desc': 'historico', 'doc': 'documento', 'amount': 'valor'}
    """
    if pdfplumber is None:
        raise RuntimeError("pdfplumber não disponível. Converta o PDF para CSV ou ative pdfplumber.")

    status_imp = "P" if extrato_arquivo else "I"
    created, skipped = 0, 0
    with pdfplumber.open(file_obj) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for tbl in tables or []:
                # heurística simples: pula cabeçalho
                for row in tbl[1:]:
                    # Ajuste aqui conforme layout do seu banco:
                    try:
                        dt_raw, doc_raw, hist_raw, val_raw = row[0], row[1], row[2], row[3]
                        data = datetime.strptime(str(dt_raw).strip(), "%d/%m/%Y").date()
                        documento = (str(doc_raw) or "").strip() or None
                        historico = (str(hist_raw) or "").strip()
                        valor = Decimal(str(val_raw).replace(".", "").replace(",", "."))
                    except Exception:
                        continue

                    h = hash_lancamento(conta.id, data, valor, historico, documento)
                    if Lancamento.objects.filter(hash_unico=h, conta=conta).exists():
                        skipped += 1
                        continue

                    try:
                        Lancamento.objects.create(
                            empresa=conta.empresa,
                            conta=conta,
                            banco=conta.banco,
                            data=data,
                            documento=documento,
                            historico=historico,
                            valor=valor,
                            conciliado=False,
                            origem="PDF",
                            hash_unico=h,
                            extrato_arquivo=extrato_arquivo,
                            status_importacao=status_imp,
                        )
                        created += 1
                    except IntegrityError:
                        # Violação de constraint único (ex: uniq_lancamento_basico)
                        skipped += 1
    return created, skipped
