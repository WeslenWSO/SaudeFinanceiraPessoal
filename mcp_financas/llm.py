"""Function calling (Gemini) reutilizando as mesmas tools do MCP."""

from __future__ import annotations

import json
from typing import Any

from mcp_financas.django_setup import setup_django
from mcp_financas.tools_impl import TOOL_REGISTRY, executar_tool


GEMINI_TOOL_DECLARATIONS = [
    {
        'name': 'listar_empresas',
        'description': 'Lista empresas cadastradas no sistema.',
        'parameters': {
            'type': 'object',
            'properties': {
                'apenas_ativas': {
                    'type': 'boolean',
                    'description': 'Se true, só empresas com status Ativa.',
                },
            },
        },
    },
    {
        'name': 'resumo_faturamento',
        'description': 'Resumo de faturamento médico por empresa e período.',
        'parameters': {
            'type': 'object',
            'properties': {
                'empresa_id': {'type': 'integer'},
                'data_inicio': {'type': 'string', 'description': 'AAAA-MM-DD'},
                'data_fim': {'type': 'string', 'description': 'AAAA-MM-DD'},
            },
            'required': ['empresa_id', 'data_inicio', 'data_fim'],
        },
    },
    {
        'name': 'resumo_fluxo_caixa',
        'description': 'Receitas, despesas e resultado por mês no ano.',
        'parameters': {
            'type': 'object',
            'properties': {
                'empresa_id': {'type': 'integer'},
                'ano': {'type': 'integer'},
            },
            'required': ['empresa_id', 'ano'],
        },
    },
    {
        'name': 'health_check',
        'description': 'Testa conexão com o banco de dados.',
        'parameters': {'type': 'object', 'properties': {}},
    },
]


def _get_model():
    setup_django()
    import google.generativeai as genai
    from SaudeFinanceira.gemini_config import get_gemini_api_key, get_gemini_model

    api_key = get_gemini_api_key()
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY não configurada (env ou GeminiConfig no admin).')
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(
        get_gemini_model(),
        tools=[{'function_declarations': GEMINI_TOOL_DECLARATIONS}],
    )


def perguntar_financas(
    mensagem: str,
    *,
    empresa_id: int | None = None,
    max_turnos: int = 6,
) -> str:
    """
    Envia uma pergunta ao Gemini; o modelo escolhe tools e devolve texto final.
    Se empresa_id for informado, inclui no contexto da pergunta.
    """
    model = _get_model()
    prefix = ''
    if empresa_id is not None:
        prefix = f'[Contexto: empresa_id={empresa_id}]\n'
    chat = model.start_chat(enable_automatic_function_calling=False)
    prompt = prefix + (mensagem or '').strip()
    if not prompt:
        raise ValueError('mensagem vazia')

    response = chat.send_message(prompt)
    for _ in range(max_turnos):
        parts = response.candidates[0].content.parts
        fn_calls = [p for p in parts if getattr(p, 'function_call', None)]
        if not fn_calls:
            text_parts = [getattr(p, 'text', '') or '' for p in parts]
            return ''.join(text_parts).strip() or '(sem resposta)'

        fn_responses: list[dict[str, Any]] = []
        for part in fn_calls:
            fc = part.function_call
            name = fc.name
            args = dict(fc.args) if fc.args else {}
            if empresa_id is not None and name in (
                'resumo_faturamento',
                'resumo_fluxo_caixa',
            ):
                args.setdefault('empresa_id', empresa_id)
            try:
                if name not in TOOL_REGISTRY:
                    payload = {'error': f'tool desconhecida: {name}'}
                else:
                    payload = json.loads(executar_tool(name, args))
            except Exception as exc:
                payload = {'error': str(exc)}
            fn_responses.append(
                {
                    'function_response': {
                        'name': name,
                        'response': payload,
                    }
                }
            )
        response = chat.send_message(fn_responses)
    return '(limite de turnos com function calling atingido)'
