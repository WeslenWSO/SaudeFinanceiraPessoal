import hashlib
from datetime import datetime

from django.conf import settings
from decimal import Decimal
from pathlib import Path
import re

from ..models import Lancamento, Banco, Empresa, ContaBancaria

DATE_PAT = re.compile(r"<DTPOSTED>(\d{8})(?:\d{6})?(?:\[-?\d+:[A-Z]+\])?")
AMT_PAT = re.compile(r"<TRNAMT>([-+]?\d+[\.,]?\d{0,4})")
MEMO_PAT = re.compile(r"<MEMO>(.*?)(?=<|$)", re.DOTALL)
NAME_PAT = re.compile(r"<NAME>(.*?)(?=<|$)", re.DOTALL)
FITID_PAT = re.compile(r"<FITID>(.*?)(?=<|$)", re.DOTALL)
CHECKNUM_PAT = re.compile(r"<CHECKNUM>(.*?)(?=<|$)", re.DOTALL)
REFNUM_PAT = re.compile(r"<REFNUM>(.*?)(?=<|$)", re.DOTALL)
STMT_BLOCK = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.DOTALL)
BANKID_PAT = re.compile(r"<BANKID>(.*?)</BANKID>")
BRANCHID_PAT = re.compile(r"<BRANCHID>(.*?)</BRANCHID>")
ACCTID_PAT = re.compile(r"<ACCTID>(.*?)</ACCTID>")
ACCTTYPE_PAT = re.compile(r"<ACCTTYPE>(.*?)</ACCTTYPE>")

def parse_ofx_text(text: str):
    print("=== DEBUG parse_ofx_text ===")
    print(f"Texto OFX (primeiros 500 chars): {text[:500]}...")

    blocks_found = STMT_BLOCK.findall(text)
    print(f"Total de blocos STMTTRN encontrados: {len(blocks_found)}")

    for i, block in enumerate(blocks_found):
        print(f"\n--- Processando bloco {i+1} ---")
        print(f"Bloco completo: {repr(block)}")
        print(f"Bloco preview: {block[:200]}...")

        date_m = DATE_PAT.search(block)
        amt_m = AMT_PAT.search(block)
        memo_m = MEMO_PAT.search(block)
        name_m = NAME_PAT.search(block)
        fitid_m = FITID_PAT.search(block)
        checknum_m = CHECKNUM_PAT.search(block)
        refnum_m = REFNUM_PAT.search(block)

        print(f"DATE match: {date_m.group(1) if date_m else 'NÃO'}")
        print(f"AMT match: {amt_m.group(1) if amt_m else 'NÃO'}")
        print(f"MEMO match: {repr(memo_m.group(1)) if memo_m else 'NÃO'}")
        print(f"NAME match: {repr(name_m.group(1)) if name_m else 'NÃO'}")
        print(f"FITID match: {repr(fitid_m.group(1)) if fitid_m else 'NÃO'}")
        print(f"CHECKNUM match: {repr(checknum_m.group(1)) if checknum_m else 'NÃO'}")
        print(f"REFNUM match: {repr(refnum_m.group(1)) if refnum_m else 'NÃO'}")

        if not (date_m and amt_m):
            print("Bloco ignorado: data ou valor nao encontrados")
            continue

        try:
            # Extrair apenas a data (YYYYMMDD) do campo DTPOSTED
            date_str = date_m.group(1)
            print(f"String de data extraida: '{date_str}'")
            d = datetime.strptime(date_str, "%Y%m%d").date()
            print(f"Data convertida: {d}")
        except Exception as e:
            print(f"Erro ao converter data '{date_str}': {e}")
            continue

        try:
            # Substituir vírgula por ponto para conversão decimal
            valor_str = amt_m.group(1).replace(',', '.')
            v = Decimal(valor_str)
            print(f"Valor convertido: {v}")
        except Exception as e:
            print(f"Erro ao converter valor '{amt_m.group(1)}': {e}")
            continue

        # Historico: MEMO - NAME
        historico = ""
        if memo_m:
            historico = memo_m.group(1).strip()
            print(f"Histórico (MEMO): '{historico}'")
        if name_m:
            if historico:
                historico += " - " + name_m.group(1).strip()
            else:
                historico = name_m.group(1).strip()
            print(f"Histórico (NAME): '{historico}'")

        # Documento: CHECKNUM + REFNUM
        documento = ""
        if checknum_m:
            documento = checknum_m.group(1).strip()
            print(f"Documento (CHECKNUM): '{documento}'")
        if refnum_m:
            if documento:
                documento += " " + refnum_m.group(1).strip()
            else:
                documento = refnum_m.group(1).strip()
            print(f"Documento (REFNUM): '{documento}'")

        # FITID
        fitid = fitid_m.group(1).strip() if fitid_m else None
        print(f"FITID: '{fitid}'")

        print(f"Lancamento processado: data={d}, valor={v}, historico='{historico}', documento='{documento}', fitid='{fitid}'")
        yield d, v, historico, documento, fitid

def hash_lancamento(conta_id, fitid, data, valor, historico, documento):
    base = f"{conta_id}|{(fitid or '').strip()}|{data.isoformat()}|{valor}|{(historico or '').strip()}|{(documento or '').strip()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()

def validate_ofx_account(text: str, conta: ContaBancaria):
    """Valida se os dados da conta no OFX correspondem à conta selecionada"""
    print("=== DEBUG validate_ofx_account ===")

    bankid_m = BANKID_PAT.search(text)
    branchid_m = BRANCHID_PAT.search(text)
    acctid_m = ACCTID_PAT.search(text)
    accttype_m = ACCTTYPE_PAT.search(text)

    print(f"BANKID encontrado: {repr(bankid_m.group(1).strip()) if bankid_m else 'NÃO'}")
    print(f"BRANCHID encontrado: {repr(branchid_m.group(1).strip()) if branchid_m else 'NÃO'}")
    print(f"ACCTID encontrado: {repr(acctid_m.group(1).strip()) if acctid_m else 'NÃO'}")
    print(f"ACCTTYPE encontrado: {repr(accttype_m.group(1).strip()) if accttype_m else 'NÃO'}")

    if bankid_m and acctid_m:
        ofx_bankid = bankid_m.group(1).strip()
        ofx_branchid = branchid_m.group(1).strip() if branchid_m else ""
        ofx_acctid = acctid_m.group(1).strip()
        ofx_accttype = accttype_m.group(1).strip() if accttype_m else ""

        print(f"Dados do OFX - Banco: {ofx_bankid}, Agencia: {ofx_branchid}, Conta: {ofx_acctid}, Tipo: {ofx_accttype}")
        print(f"Dados da conta - Banco: {conta.banco.codigo or conta.banco.id}, Agencia: {conta.agencia}, Conta: {conta.conta}")

        # Normalizar para comparação (remover caracteres não numéricos)
        def normalize(value):
            return ''.join(c for c in str(value or "") if c.isdigit())

        ofx_bankid_norm = normalize(ofx_bankid)
        conta_banco_norm = normalize(conta.banco.codigo or str(conta.banco.id))
        ofx_branchid_norm = normalize(ofx_branchid)
        conta_agencia_norm = normalize(conta.agencia)
        ofx_acctid_norm = normalize(ofx_acctid)
        conta_conta_norm = normalize(conta.conta)

        print(f"Apos normalizacao - OFX: {ofx_bankid_norm}/{ofx_branchid_norm}/{ofx_acctid_norm}")
        print(f"Apos normalizacao - Conta: {conta_banco_norm}/{conta_agencia_norm}/{conta_conta_norm}")

        # Comparar com os dados da conta selecionada
        banco_ok = ofx_bankid_norm == conta_banco_norm
        agencia_ok = ofx_branchid_norm == conta_agencia_norm or not ofx_branchid_norm  # Permite agencia vazia no OFX
        conta_ok = ofx_acctid_norm == conta_conta_norm

        print(f"Comparacoes - Banco: {banco_ok}, Agencia: {agencia_ok}, Conta: {conta_ok}")

        if not (banco_ok and conta_ok):
            msg = f"Conta do OFX ({ofx_bankid}/{ofx_branchid}/{ofx_acctid}) nao corresponde a conta selecionada ({conta.banco.codigo or conta.banco.id}/{conta.agencia or ''}/{conta.conta or ''})"
            print(f"VALIDACAO FALHOU: {msg}")
            return False, msg

    print("VALIDACAO PASSOU")
    return True, None

def import_ofx(conta: ContaBancaria, file_obj, extrato_arquivo=None, origem_nome="OFX"):
    from django.db import IntegrityError

    print("=== DEBUG import_ofx ===")
    print(f"Conta: {conta}, Arquivo: {file_obj.name}, extrato_arquivo: {extrato_arquivo}")

    # file_obj: InMemoryUploadedFile / File
    try:
        raw = file_obj.read().decode("cp1252", errors="replace")
        print(f"Arquivo decodificado com sucesso. Tamanho: {len(raw)} caracteres")
    except Exception as e:
        print(f"Erro ao decodificar arquivo: {e}")
        raise ValueError(f"Erro ao processar arquivo OFX: {e}")

    # Validar conta
    print("Validando conta...")
    valid, error_msg = validate_ofx_account(raw, conta)
    if not valid:
        print(f"Validacao de conta falhou: {error_msg}")
        raise ValueError(error_msg)
    print("Validacao de conta passou")

    created, skipped = 0, 0
    lancamentos_processados = 0

    print("Iniciando processamento dos lançamentos...")
    for data, valor, historico, documento, fitid in parse_ofx_text(raw):
        lancamentos_processados += 1
        print(f"\n--- Processando lançamento {lancamentos_processados} ---")
        print(f"Data: {data}, Valor: {valor}, Histórico: '{historico}', Documento: '{documento}', FITID: '{fitid}'")

        h = hash_lancamento(conta.id, fitid, data, valor, historico, documento)

        # Duplicata: SOMENTE quando FITID já existe NA CONTA SELECIONADA (a que o usuário escolheu para importar)
        if fitid and Lancamento.objects.filter(conta_id=conta.id, fitid=fitid).exists():
            if settings.DEBUG:
                print("Lancamento pulado: FITID+BANCO+CONTA ja existe")
            skipped += 1
            continue

        status_imp = "P" if extrato_arquivo else "I"
        try:
            print("Criando lancamento no banco...")
            lancamento = Lancamento.objects.create(
                empresa=conta.empresa,
                conta=conta,
                banco=conta.banco,
                fitid=fitid,
                data=data,
                documento=documento,
                historico=historico,
                valor=valor,
                conciliado=False,
                idconciliacao=None,
                origem=origem_nome,
                hash_unico=h,
                extrato_arquivo=extrato_arquivo,
                status_importacao=status_imp,
            )
            print(f"Lancamento criado com ID: {lancamento.id}")
            created += 1
        except IntegrityError as ie:
            print(f"IntegrityError ao criar lancamento: {ie}")
            skipped += 1
        except Exception as e:
            print(f"Erro geral ao criar lancamento: {e}")
            skipped += 1

    print("\n=== RESULTADO FINAL ===")
    print(f"Total de lançamentos processados: {lancamentos_processados}")
    print(f"Lançamentos criados: {created}")
    print(f"Lançamentos pulados: {skipped}")

    return created, skipped
