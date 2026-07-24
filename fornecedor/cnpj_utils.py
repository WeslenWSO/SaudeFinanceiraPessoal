import re


def limpar_cnpj(cnpj_str):
    """Retorna apenas os 14 dígitos do CNPJ."""
    if not cnpj_str:
        return ""
    return re.sub(r"\D", "", str(cnpj_str).strip())


def somente_digitos(valor, max_len=None):
    """Remove não numéricos; opcionalmente limita o tamanho."""
    d = re.sub(r"\D", "", str(valor or "").strip())
    if max_len is not None:
        return d[:max_len]
    return d


def limpar_cep(cep_str):
    """Até 8 dígitos (CEP Brasil)."""
    return somente_digitos(cep_str, 8)


def limpar_telefone_br(telefone_str):
    """DDD + número: até 11 dígitos."""
    return somente_digitos(telefone_str, 11)
