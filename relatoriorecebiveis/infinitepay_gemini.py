"""
Extração do relatório Infinite Pay (PDF) via Google Gemini — alternativa ao pdfplumber local.
Requer GEMINI_API_KEY em settings e pacote google-generativeai.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

from SaudeFinanceira.google_grpc_env import silenciar_logs_grpc_google

silenciar_logs_grpc_google()

try:
    import google.generativeai as genai
    from google.api_core import exceptions as google_api_exceptions

    GEMINI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore[assignment]
    google_api_exceptions = None  # type: ignore[assignment]
    GEMINI_AVAILABLE = False

# Chaves alinhadas ao fluxo INFINTY / infinitepay_pdf.parse_infinitepay_pdf_bytes
_ROW_KEYS = (
    'Data Pagamento',
    'Forma Pagamento',
    'Bandeira',
    'Valor Bruto',
    'Valor Taxa',
    'Valor Líquido',
    'Autorização',
    'Data Venda',
    'Parcela',
    'Parcelas',
    'Total de Parcelas',
)

def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith('```json'):
        t = t[7:]
    elif t.startswith('```'):
        t = t[3:]
    if t.endswith('```'):
        t = t[:-3]
    return t.strip()


def format_gemini_error(exc: Exception) -> str:
    """
    Converte exceções da API Google em mensagem legível (inclui detalhe retornado pela API quando houver).
    """
    detail = str(exc).strip()
    if not detail:
        detail = exc.__class__.__name__

    if not GEMINI_AVAILABLE or google_api_exceptions is None:
        return f'Erro na API Gemini: {detail}'

    if isinstance(exc, google_api_exceptions.Unauthenticated):
        return (
            'Chave de API Gemini inválida, revogada ou não reconhecida pela Google. '
            f'Detalhe da API: {detail}'
        )
    if isinstance(exc, google_api_exceptions.PermissionDenied):
        return f'Acesso negado pela API Gemini. Detalhe: {detail}'
    if isinstance(exc, google_api_exceptions.ResourceExhausted):
        return f'Cota ou limite de uso da API Gemini excedido. Detalhe: {detail}'
    if isinstance(exc, google_api_exceptions.InvalidArgument):
        return f'Requisição inválida para a API Gemini. Detalhe: {detail}'
    if isinstance(exc, google_api_exceptions.NotFound):
        return f'Recurso ou modelo não encontrado na API Gemini. Detalhe: {detail}'
    if isinstance(exc, google_api_exceptions.DeadlineExceeded):
        return f'Tempo esgotado ao falar com a API Gemini. Detalhe: {detail}'
    if isinstance(exc, google_api_exceptions.GoogleAPICallError):
        return f'Erro na chamada à API Gemini: {detail}'

    return f'Erro ao usar Gemini: {detail}'


def validate_gemini_api_key(api_key: str | None = None) -> tuple[bool, str]:
    """
    Testa a chave com uma geração mínima (sem PDF).
    Retorna (True, '') se a chave funciona, ou (False, mensagem com detalhe do erro).
    """
    if not GEMINI_AVAILABLE:
        return False, 'Pacote google-generativeai não instalado; não é possível usar Gemini.'

    key = (api_key if api_key is not None else getattr(settings, 'GEMINI_API_KEY', None)) or ''
    key = str(key).strip()
    if not key:
        return False, 'GEMINI_API_KEY não está configurada em settings (ou está vazia).'

    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        resp = model.generate_content(
            'Responda apenas com a palavra: OK',
            generation_config=genai.GenerationConfig(max_output_tokens=32, temperature=0),
        )
        feedback = getattr(resp, 'prompt_feedback', None)
        if feedback is not None:
            br = getattr(feedback, 'block_reason', None)
            if br is not None and str(br).strip() not in ('', 'BLOCK_REASON_UNSPECIFIED', '0'):
                return False, f'A API bloqueou o teste de chave (motivo: {br}).'
        if not getattr(resp, 'candidates', None):
            return False, 'A API Gemini não retornou candidatos (verifique a chave, faturamento e restrições do projeto).'
        return True, ''
    except Exception as e:
        logger.warning('validate_gemini_api_key falhou: %s', e, exc_info=True)
        return False, format_gemini_error(e)


def _normalize_row(raw: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k in _ROW_KEYS:
        v = raw.get(k)
        out[k] = '' if v is None else str(v).strip()
    return out


def parse_infinitepay_pdf_with_gemini(
    pdf_bytes: bytes,
    filename: str = 'relatorio.pdf',
) -> tuple[list[dict[str, str]], list[str]]:
    """
    Envia o PDF ao Gemini e pede uma lista de linhas do relatório de recebimentos.
    Retorna o mesmo formato de dicts que parse_infinitepay_pdf_bytes (chaves INFINTY).
    """
    warnings: list[str] = []
    if not GEMINI_AVAILABLE:
        warnings.append('Pacote google-generativeai não instalado; não é possível usar Gemini.')
        return [], warnings

    api_key = getattr(settings, 'GEMINI_API_KEY', None)
    if not api_key:
        warnings.append('GEMINI_API_KEY não configurada em settings.')
        return [], warnings

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash')

    # response_mime_type JSON: a API garante JSON sintaticamente válido (evita o erro típico de aspas simples / texto extra).
    # max_output_tokens alto: PDFs com muitas linhas geram JSON grande; truncar no meio quebra o parse.
    generation_config = genai.GenerationConfig(
        response_mime_type='application/json',
        temperature=0.15,
        max_output_tokens=65536,
    )

    tmp_path = None
    uploaded = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        uploaded = genai.upload_file(tmp_path, mime_type='application/pdf')
        while uploaded.state.name != 'ACTIVE':
            if uploaded.state.name == 'FAILED':
                warnings.append('Falha no processamento do arquivo no Gemini.')
                return [], warnings
            time.sleep(0.7)
            uploaded = genai.get_file(uploaded.name)

        prompt = """
Você está analisando um PDF do Infinite Pay (Conta Web) — relatório de RECEBIMENTOS da maquininha de cartão.

INSTRUÇÃO OBRIGATÓRIA — PÁGINAS:
Percorra o PDF INTEIRO, da primeira à última página. Inclua TODAS as linhas de transação de TODAS as páginas.
Não pare após a primeira página; repetições de cabeçalho de tabela em páginas seguintes devem ser ignoradas como linha de dado, mas as LINHAS DE DADOS de cada página devem aparecer na lista "linhas".

Extraia TODAS as linhas da tabela principal de transações/recebimentos (uma linha por pagamento).
Ignore totais, cabeçalhos de página repetidos e linhas que não sejam dados de transação.

Para cada linha, preencha estes campos (use string vazia "" se não existir):
- "Data Pagamento": data do recebimento/pagamento (DD/MM/AAAA ou AAAA-MM-DD)
- "Forma Pagamento": ex.: o que estiver em "Tipo" (Crédito, Débito) ou forma; se houver só "Cartão" na forma e "Crédito" em Tipo, use o valor de Tipo para forma de pagamento quando fizer sentido
- "Bandeira": Visa, Mastercard, Elo, etc. (texto; se só houver logo, descreva a bandeira que reconhecer)
- "Valor Bruto", "Valor Taxa", "Valor Líquido": valores como no PDF (pode usar vírgula decimal)
- "Autorização": código/autorização se houver
- "Data Venda": data da venda se houver
- "Parcela": texto como "1 / 2" se a coluna existir assim
- "Parcelas": número da parcela atual (ex.: 1)
- "Total de Parcelas": total (ex.: 2)

Responda com UM objeto JSON com a chave "linhas" (array de objetos). Cada objeto deve ter exatamente estas chaves em texto (aspas duplas):
"Data Pagamento", "Forma Pagamento", "Bandeira", "Valor Bruto", "Valor Taxa", "Valor Líquido", "Autorização", "Data Venda", "Parcela", "Parcelas", "Total de Parcelas".

Exemplo de forma (valores ilustrativos):
{"linhas":[{"Data Pagamento":"01/01/2025","Forma Pagamento":"Crédito","Bandeira":"Visa","Valor Bruto":"10,00","Valor Taxa":"0,50","Valor Líquido":"9,50","Autorização":"","Data Venda":"","Parcela":"","Parcelas":"1","Total de Parcelas":"1"}]}

Se não houver tabela legível, retorne {"linhas":[]}.
Não invente linhas; só extraia o que estiver no documento.
"""
        response = model.generate_content(
            [uploaded, prompt],
            generation_config=generation_config,
        )
        texto = (response.text or '').strip()
        texto = _strip_json_fence(texto)

        try:
            data = json.loads(texto)
        except json.JSONDecodeError:
            logger.warning(
                'Gemini devolveu texto que não parseou como JSON (primeiros 400 chars): %r',
                texto[:400],
            )
            raise
        linhas = data.get('linhas') or data.get('rows') or []
        if not isinstance(linhas, list):
            warnings.append('Resposta Gemini em formato inesperado (linhas não é lista).')
            return [], warnings

        out: list[dict[str, str]] = []
        for raw in linhas:
            if not isinstance(raw, dict):
                continue
            out.append(_normalize_row(raw))

        if out:
            warnings.append('Dados extraídos com Google Gemini (revisar prévia).')
        else:
            warnings.append('Gemini não retornou linhas; verifique o PDF ou tente a extração local.')
        return out, warnings

    except json.JSONDecodeError as e:
        logger.exception('Gemini JSON inválido')
        warnings.append(f'Resposta Gemini não é JSON válido: {e}')
        return [], warnings
    except Exception as e:
        logger.exception('Erro Gemini Infinite Pay')
        warnings.append(format_gemini_error(e))
        return [], warnings
    finally:
        if uploaded is not None:
            try:
                genai.delete_file(uploaded.name)
            except Exception:
                pass
        if tmp_path and os.path.isfile(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
