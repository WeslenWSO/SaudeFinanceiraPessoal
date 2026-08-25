"""Extração do relatório UNIMED Produção (PDF) via Google Gemini — fallback após OCR."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any

from SaudeFinanceira.google_grpc_env import silenciar_logs_grpc_google

silenciar_logs_grpc_google()

logger = logging.getLogger(__name__)

try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    genai = None  # type: ignore[assignment]
    GEMINI_AVAILABLE = False


def _strip_json_fence(text: str) -> str:
    t = (text or '').strip()
    if t.startswith('```json'):
        t = t[7:]
    elif t.startswith('```'):
        t = t[3:]
    if t.endswith('```'):
        t = t[:-3]
    return t.strip()


def _timeout_segundos(nome: str, padrao: float) -> float:
    raw = os.environ.get(nome, '')
    try:
        return max(5.0, float(raw))
    except ValueError:
        return padrao


def _defaults_gemini_timeout() -> tuple[float, float]:
    """Render: limites baixos para evitar 502 no gateway (~30s)."""
    on_render = os.environ.get('RENDER', '').strip().lower() in ('true', '1', 'yes')
    if on_render:
        return 12.0, 15.0
    return 90.0, 120.0


def _executar_com_timeout(fn, timeout_sec: float, descricao: str):
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(fn)
        try:
            return future.result(timeout=timeout_sec)
        except FuturesTimeoutError as exc:
            raise TimeoutError(f'{descricao} excedeu {int(timeout_sec)}s.') from exc


def extract_unimed_linhas_gemini(pdf_bytes: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Envia PDF ao Gemini e retorna lista de linhas do relatório Produção UNIMED.
    Campos ignorados: Plano, Tp. Grau, Participação %, Valor Ref.
    """
    warnings: list[str] = []
    if not GEMINI_AVAILABLE:
        warnings.append('Pacote google-generativeai não instalado.')
        return [], warnings

    from relatoriorecebiveis.infinitepay_gemini import format_gemini_error
    from SaudeFinanceira.gemini_config import get_gemini_api_key, get_gemini_model

    api_key = get_gemini_api_key()
    if not api_key:
        warnings.append('GEMINI_API_KEY não configurada.')
        return [], warnings

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(get_gemini_model())
    generation_config = genai.GenerationConfig(
        response_mime_type='application/json',
        temperature=0.1,
        max_output_tokens=65536,
    )

    tmp_path = None
    uploaded = None
    upload_default, generate_default = _defaults_gemini_timeout()
    upload_timeout = _timeout_segundos('GEMINI_UPLOAD_TIMEOUT', upload_default)
    generate_timeout = _timeout_segundos('GEMINI_GENERATE_TIMEOUT', generate_default)
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        uploaded = genai.upload_file(tmp_path, mime_type='application/pdf')
        deadline = time.time() + upload_timeout
        while uploaded.state.name != 'ACTIVE':
            if uploaded.state.name == 'FAILED':
                warnings.append('Falha no processamento do PDF no Gemini.')
                return [], warnings
            if time.time() > deadline:
                warnings.append(
                    f'Tempo esgotado aguardando o Gemini processar o PDF ({int(upload_timeout)}s).'
                )
                return [], warnings
            time.sleep(0.7)
            uploaded = genai.get_file(uploaded.name)

        prompt = """
Analise o PDF do relatório UNIMED «Produção» (tabela com colunas Lote, Guia, Cód. Usuário, Nome Usuário, etc.).

Extraia TODAS as linhas de serviço de TODAS as páginas.
Ignore cabeçalhos repetidos, totais «Vl. Total Pago» e seções «Tipo de Guia».

NÃO inclua estes campos (ignore no PDF): Plano, Tp. Grau, Participação %, Valor Ref.

Para cada linha de serviço, retorne um objeto JSON com estas chaves (strings):
- "lote"
- "guia"
- "cod_usuario"
- "nome_usuario"
- "cod_servico"
- "desc_servico"
- "guia_prest" (se existir; senão "")
- "data" (DD/MM/AAAA)
- "qtde"
- "valor_unit" (número ou texto BR, ex. 500,00)
- "valor_total" (número ou texto BR)

Agrupe mentalmente por lote+guia, mas na resposta use apenas a lista "linhas" (uma entrada por serviço).

Responda com UM objeto JSON:
{"linhas":[{"lote":"...","guia":"...","cod_usuario":"...","nome_usuario":"...","cod_servico":"...","desc_servico":"...","guia_prest":"","data":"01/04/2026","qtde":"1","valor_unit":"0,00","valor_total":"0,00"}]}

Se não houver tabela legível, retorne {"linhas":[]}.
Não invente linhas.
"""
        def _gerar():
            return model.generate_content(
                [uploaded, prompt],
                generation_config=generation_config,
            )

        try:
            response = _executar_com_timeout(
                _gerar,
                generate_timeout,
                'Chamada à API Gemini',
            )
        except TimeoutError as exc:
            warnings.append(str(exc))
            return [], warnings

        texto = _strip_json_fence(response.text or '')
        data = json.loads(texto)
        linhas = data.get('linhas') or data.get('rows') or []
        if not isinstance(linhas, list):
            warnings.append('Resposta Gemini em formato inesperado.')
            return [], warnings

        out: list[dict[str, Any]] = []
        for raw in linhas:
            if isinstance(raw, dict):
                out.append(raw)

        if out:
            warnings.append(f'Dados extraídos com Google Gemini ({len(out)} linha(s)); revise a listagem.')
        else:
            warnings.append('Gemini não retornou linhas do PDF.')
        return out, warnings

    except json.JSONDecodeError as exc:
        logger.exception('Gemini UNIMED JSON inválido')
        warnings.append(f'Resposta Gemini não é JSON válido: {exc}')
        return [], warnings
    except Exception as exc:
        logger.exception('Erro Gemini UNIMED')
        warnings.append(format_gemini_error(exc))
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
