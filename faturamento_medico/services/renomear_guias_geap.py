"""Renomeia PDFs de guias: {data} - {convênio} - {nome}.pdf"""
from __future__ import annotations

import io
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

import pdfplumber

from SaudeFinanceira.google_grpc_env import silenciar_logs_grpc_google

silenciar_logs_grpc_google()

try:
    import google.generativeai as genai

    GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    GEMINI_AVAILABLE = False

try:
    import pypdfium2 as pdfium
except ImportError:
    pdfium = None

try:
    import pytesseract
    from PIL import Image

    OCR_AVAILABLE = True
except ImportError:
    pytesseract = None
    Image = None
    OCR_AVAILABLE = False

logger = logging.getLogger(__name__)

_OCR_ENGINE_OK: bool | None = None


def _configurar_tesseract() -> bool:
    """Define caminho do Tesseract no Windows e valida se o executável responde."""
    global _OCR_ENGINE_OK
    if _OCR_ENGINE_OK is not None:
        return _OCR_ENGINE_OK
    if not OCR_AVAILABLE or pytesseract is None:
        _OCR_ENGINE_OK = False
        return False

    candidatos = []
    try:
        from django.conf import settings

        cmd_env = getattr(settings, 'TESSERACT_CMD', None) or os.environ.get('TESSERACT_CMD', '')
        if cmd_env:
            candidatos.append(cmd_env.strip())
    except Exception:
        cmd_env = os.environ.get('TESSERACT_CMD', '')
        if cmd_env:
            candidatos.append(cmd_env.strip())

    candidatos.extend([
        r'C:\Program Files\Tesseract-OCR\tesseract.exe',
        r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
    ])

    for cmd in candidatos:
        if cmd and os.path.isfile(cmd):
            pytesseract.pytesseract.tesseract_cmd = cmd
            break

    try:
        pytesseract.get_tesseract_version()
        _OCR_ENGINE_OK = True
    except Exception as exc:
        logger.info('OCR indisponível (Tesseract): %s', exc)
        _OCR_ENGINE_OK = False
    return _OCR_ENGINE_OK

_RE_DATA_AUTORIZACAO = re.compile(
    r'4\s*[-–]?\s*Data\s+da\s+Autoriza[cç][ãa]o\s*(\d{2}[/.-]\d{2}[/.-]\d{2,4})',
    re.IGNORECASE,
)
_RE_DATA_AUTORIZACAO_FALLBACK = re.compile(
    r'4\s*[-–]?\s*Data\s+da\s+Autoriz[^\d]{0,30}(\d{2}/\d{2}/\d{2,4})',
    re.IGNORECASE,
)
_RE_DATA_AUTORIZACAO_GENERICO = re.compile(
    r'(?:^|\n)\s*4\b[^\d\n]{0,40}(\d{2}/\d{2}/\d{2,4})',
    re.IGNORECASE,
)
_RE_NOME_BENEFICIARIO = re.compile(
    r'10\s*[-–]?\s*Nome\s*(.+?)(?=\s+\d+\s*[-–]?\s|\n\d+\b|\n\n|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_RE_NOME_BENEFICIARIO_LABEL = re.compile(
    r'(?:10\s*[-–.]?\s*Nome|Nome\s+do\s+Benefici[aá]rio|Benefici[aá]rio)\s*[:\-]?\s*'
    r'(.+?)'
    r'(?=\s*(?:\d+\s*[-–.]|\n\s*\d+\s|Matr[ií]cula|CPF|Cart|N[ºo°]|Sexo|Data\s+de|\Z))',
    re.IGNORECASE | re.DOTALL,
)
_RE_NOME_PACIENTE = re.compile(
    r'Paciente\s*[:\-]?\s*(.+?)(?=\n|Conv[eê]nio|Proced|$)',
    re.IGNORECASE,
)
_RE_NOME_BENEFICIARIO_OCR = re.compile(
    r'[1lI][0oO]\s*[-–]?\s*Nome\s*(.+?)(?=\s+\d+\s*[-–]?\s|\n\d+\b|\n\n|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_RE_DATA_EMISSAO = re.compile(
    r'Data\s+de\s+Emiss[aã]o\s*[:\-]?\s*(\d{2}[/.-]\d{2}[/.-]\d{2,4})',
    re.IGNORECASE,
)
_RE_FUSEX_DATA = re.compile(
    r'(?:^|\n)\s*Data\s*[:\-]?\s*(\d{2}[/.-]\d{2}[/.-]\d{2,4})',
    re.IGNORECASE,
)
_RE_FUSEX_PACIENTE = re.compile(
    r'PACIENTE\s*[:\-]?\s*(.+?)(?=\n|Grupo|Benefici|$)',
    re.IGNORECASE | re.DOTALL,
)
_RE_PM_NOME = re.compile(
    r'(?:1\s*[-–.]?\s*)?Nome\s+do\s+Benefici[aá]rio\s*[:\-]?\s*'
    r'(.+?)'
    r'(?=\s*Sexo\b|\s*Nome\s+do\s+Associado\b|\s*Matr[ií]cula\b|\s*Parentesco\b|\n\s*\d+\s*[-–.]|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_RE_PM_DATA_LOCAL = re.compile(
    r'Local\s+e\s+Data\s*[:\-]?\s*.+?(\d{1,2})\s+de\s+([A-Za-zçÇáéíóúãõâêô]+)\s+de\s+(\d{4})',
    re.IGNORECASE,
)
_RE_PM_STOP_SEXO = re.compile(r'\bSexo\b', re.IGNORECASE)
_RE_BOMBEIRO_TITULAR = re.compile(
    r'Titular\s*[:\-]?\s*(.+?)(?=\n|Dependente|$)',
    re.IGNORECASE,
)
_RE_BOMBEIRO_DEPENDENTE = re.compile(
    r'Dependente\s*[:\-]?\s*(.+?)(?=\n|$)',
    re.IGNORECASE,
)
_RE_CAMPOS_INVALIDOS_ARQUIVO = re.compile(r'[\\/:*?"<>|]')
_RE_DEPENDENTE_MESMO_TITULAR = re.compile(
    r'^(?:O\s+MESMO(?:\s+TITULAR)?|TITULAR)\.?$',
    re.IGNORECASE,
)

_MESES_PT = {
    'janeiro': '01',
    'fevereiro': '02',
    'marco': '03',
    'março': '03',
    'abril': '04',
    'maio': '05',
    'junho': '06',
    'julho': '07',
    'agosto': '08',
    'setembro': '09',
    'outubro': '10',
    'novembro': '11',
    'dezembro': '12',
}

_PALAVRAS_INVALIDAS_NOME = frozenset({
    'SEXO', 'MASC', 'FEM', 'MASCULINO', 'FEMININO', 'TITULAR', 'DEPENDENTE',
    'MATRICULA', 'ASSOCIADO', 'BENEFICIARIO', 'MUC', 'ENCAMINHAMOS', 'NOME',
    'LOCAL', 'DATA', 'GOVERNO', 'ACRE', 'PMAC', 'FUNDO', 'SAUDE', 'POLICIA',
    'MILITAR', 'ENCAMINHAMENTO', 'GUIA', 'PRESTACAO', 'SERVICOS', 'PROFISSIONAIS',
    'INSTITUICAO', 'INSTITUIÇÃO', 'RIO', 'BRANCO',
})

_TISS_CONVENIOS = (
    ('POSTAL', ('POSTAL SAÚDE', 'POSTAL SAUDE', 'POSTAL SAU')),
    ('BRADESCO', ('BRADESCO SAÚDE', 'BRADESCO SAUDE', 'BRADESCO')),
    ('CASSI', ('CASSI', 'CAIXA DE ASSISTÊNCIA', 'CAIXA DE ASSISTENCIA')),
    ('GEAP', ('GEAP SAÚDE', 'GEAP SAUDE', 'GEAP')),
)


@dataclass
class ResultadoRenomearGuiaGeap:
    arquivo_original: str
    arquivo_novo: str = ''
    data_autorizacao: str = ''
    nome_beneficiario: str = ''
    convenio: str = ''
    tipo_guia: str = ''
    ok: bool = False
    erro: str = ''
    pdf_bytes: bytes = field(default_factory=bytes, repr=False)
    faturamento_id: int | None = None
    anexo_ok: bool = False
    anexo_tentado: bool = False
    anexo_mensagem: str = ''
    anexo_erro: str = ''
    anexo_sugestoes: list = field(default_factory=list)


def _normalizar_texto(texto: str) -> str:
    return re.sub(r'\r\n?', '\n', texto or '')


def _normalizar_data(valor: str) -> str:
    valor = (valor or '').strip().replace('.', '/').replace('-', '/')
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', valor)
    if m:
        return _data_valida(f'{m.group(1)}/{m.group(2)}/{m.group(3)}')
    m = re.match(r'(\d{2})/(\d{2})/(\d{2})', valor)
    if m:
        ano = int(m.group(3))
        ano_full = 2000 + ano if ano < 100 else ano
        return _data_valida(f'{m.group(1)}/{m.group(2)}/{ano_full}')
    return ''


def _data_valida(data: str) -> str:
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})$', (data or '').strip())
    if not m:
        return ''
    dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if ano < 2000 or ano > 2100:
        return ''
    try:
        datetime(ano, mes, dia)
    except ValueError:
        return ''
    return f'{m.group(1)}/{m.group(2)}/{m.group(3)}'


def _data_para_arquivo(data: str) -> str:
    return _normalizar_data(data).replace('/', '-')


def _limpar_nome_beneficiario(valor: str) -> str:
    nome = re.sub(r'\s+', ' ', (valor or '').strip())
    nome = _RE_CAMPOS_INVALIDOS_ARQUIVO.sub('', nome)
    nome = re.sub(r'^[\s\)\(\[\]\{\}:;.,\-–_/\\|]+', '', nome)
    nome = re.sub(r'[\s\)\(\[\]\{\}:;.,\-–_/\\|]+$', '', nome)
    nome = re.sub(r'\s+', ' ', nome).strip(' .-')
    return nome.upper()


def _nome_parece_pessoa(nome: str) -> bool:
    nome = _limpar_nome_beneficiario(nome)
    if not nome or len(nome) < 6:
        return False
    if re.search(r'[\(\)\[\]\{\}]', nome):
        return False
    if re.search(r'\bSEXO\b', nome):
        return False
    palavras = [
        p for p in nome.split()
        if re.fullmatch(r'[A-ZÁÉÍÓÚÂÊÔÃÕÇ]{2,}', p)
    ]
    if len(palavras) < 2 or sum(len(p) for p in palavras) < 6:
        return False
    return not any(p in _PALAVRAS_INVALIDAS_NOME for p in palavras)


def _campos_completos(data: str, nome: str, convenio: str) -> bool:
    return bool(_data_valida(_normalizar_data(data)) and _nome_parece_pessoa(nome) and (convenio or '').strip())


def _candidato_nome_pm(valor: str) -> str:
    parte = _RE_PM_STOP_SEXO.split(valor, maxsplit=1)[0]
    return _limpar_nome_beneficiario(parte)


def _extrair_data_pm(texto: str) -> str:
    data = _extrair_data_emissao(texto)
    if data:
        return data
    m = _RE_PM_DATA_LOCAL.search(texto)
    if not m:
        return ''
    dia, mes_nome, ano = m.group(1), m.group(2), m.group(3)
    mes = _MESES_PT.get(mes_nome.lower().replace('ç', 'c'), '')
    if not mes:
        return ''
    return _data_valida(f'{int(dia):02d}/{mes}/{ano}')


def _extrair_data_emissao(texto: str) -> str:
    m = _RE_DATA_EMISSAO.search(texto)
    if m:
        return _normalizar_data(m.group(1))
    return ''


def _extrair_convenio_tiss(texto: str, convenio_padrao: str = '') -> str:
    t = (texto or '').upper()
    for label, patterns in _TISS_CONVENIOS:
        for pattern in patterns:
            if pattern.upper() in t:
                return label
    padrao = (convenio_padrao or '').strip().upper()
    return padrao or 'GEAP'


def _extrair_metadados_nome_arquivo(nome_arquivo: str) -> tuple[str, str]:
    """Convênio e data a partir do nome do PDF (ex.: CASSI 25-07 paciente.pdf)."""
    base = os.path.splitext(nome_arquivo or '')[0]
    convenio = ''
    for label, patterns in _TISS_CONVENIOS:
        if label in base.upper() or any(p.upper() in base.upper() for p in patterns):
            convenio = label
            break
    data = ''
    m = re.search(r'(?:^|[\s_\-])(\d{2})[-/](\d{2})(?:[-/](\d{2,4}))?(?:[\s_\-]|$)', base)
    if m:
        dia, mes = m.group(1), m.group(2)
        ano = m.group(3) or str(datetime.now().year)
        if len(ano) == 2:
            ano = f'20{ano}'
        data = _data_valida(f'{int(dia):02d}/{int(mes):02d}/{int(ano):04d}')
    return data, convenio


def _extrair_nome_tiss_linhas(texto_norm: str) -> str:
    linhas = texto_norm.split('\n')
    for i, linha in enumerate(linhas):
        for regex in (_RE_NOME_BENEFICIARIO_LABEL, _RE_NOME_BENEFICIARIO, _RE_NOME_BENEFICIARIO_OCR):
            m = regex.search(linha)
            if m:
                candidato = _limpar_nome_beneficiario(m.group(1))
                if _nome_parece_pessoa(candidato):
                    return candidato
        if re.search(r'10\s*[-–.]?\s*Nome', linha, re.IGNORECASE):
            parte = re.split(r'10\s*[-–.]?\s*Nome', linha, maxsplit=1, flags=re.IGNORECASE)
            if len(parte) > 1 and parte[1].strip():
                candidato = _limpar_nome_beneficiario(parte[1])
                if _nome_parece_pessoa(candidato):
                    return candidato
            for j in range(i + 1, min(i + 4, len(linhas))):
                linha_c = linhas[j].strip()
                if not linha_c or re.search(r'^\d+\s*[-–.]', linha_c):
                    continue
                candidato = _limpar_nome_beneficiario(linha_c)
                if _nome_parece_pessoa(candidato):
                    return candidato
        m_pac = _RE_NOME_PACIENTE.search(linha)
        if m_pac:
            candidato = _limpar_nome_beneficiario(m_pac.group(1))
            if _nome_parece_pessoa(candidato):
                return candidato
    return ''


def extrair_campos_tiss(texto: str) -> tuple[str, str]:
    """Retorna (data_autorizacao, nome_beneficiario) da guia TISS SP/SADT."""
    if not texto or len(texto.strip()) < 20:
        return '', ''

    texto_norm = _normalizar_texto(texto)

    data = ''
    for regex in (_RE_DATA_AUTORIZACAO, _RE_DATA_AUTORIZACAO_FALLBACK, _RE_DATA_AUTORIZACAO_GENERICO):
        m = regex.search(texto_norm)
        if m:
            data = _normalizar_data(m.group(1))
            break
    if not data:
        data = _extrair_data_emissao(texto_norm)

    nome = _extrair_nome_tiss_linhas(texto_norm)
    if not nome:
        m_pac = _RE_NOME_PACIENTE.search(texto_norm)
        if m_pac:
            candidato = _limpar_nome_beneficiario(m_pac.group(1))
            if _nome_parece_pessoa(candidato):
                nome = candidato

    return data, nome


def extrair_campos_geap(texto: str) -> tuple[str, str]:
    """Alias retrocompatível."""
    return extrair_campos_tiss(texto)


def _resolver_nome_bombeiro(titular: str, dependente: str) -> str:
    titular_limpo = _limpar_nome_beneficiario(titular)
    dependente_limpo = (dependente or '').strip()
    if not dependente_limpo or _RE_DEPENDENTE_MESMO_TITULAR.match(dependente_limpo):
        return titular_limpo
    return _limpar_nome_beneficiario(dependente_limpo)


def extrair_campos_fusex(texto: str) -> tuple[str, str]:
    if not texto or len(texto.strip()) < 20:
        return '', ''
    texto_norm = _normalizar_texto(texto)
    data = ''
    m_data = _RE_FUSEX_DATA.search(texto_norm)
    if m_data:
        data = _normalizar_data(m_data.group(1))
    nome = ''
    m_nome = _RE_FUSEX_PACIENTE.search(texto_norm)
    if m_nome:
        nome = _limpar_nome_beneficiario(m_nome.group(1))
    return data, nome


def extrair_campos_pm(texto: str) -> tuple[str, str]:
    if not texto or len(texto.strip()) < 20:
        return '', ''
    texto_norm = _normalizar_texto(texto)
    data = _extrair_data_pm(texto_norm)
    nome = ''

    m_nome = _RE_PM_NOME.search(texto_norm)
    if m_nome:
        candidato = _candidato_nome_pm(m_nome.group(1))
        if _nome_parece_pessoa(candidato):
            nome = candidato

    if not nome:
        linhas = texto_norm.split('\n')
        for i, linha in enumerate(linhas):
            if not re.search(r'Benefici[aá]rio', linha, re.IGNORECASE):
                continue
            if re.search(r'Nome\s+do\s+Benefici', linha, re.IGNORECASE):
                partes = re.split(
                    r'(?:1\s*[-–.]?\s*)?Nome\s+do\s+Benefici[aá]rio\s*[:\-]?\s*',
                    linha,
                    maxsplit=1,
                    flags=re.IGNORECASE,
                )
                if len(partes) > 1:
                    candidato = _candidato_nome_pm(partes[1])
                    if _nome_parece_pessoa(candidato):
                        nome = candidato
                        break
            for j in range(i + 1, min(i + 4, len(linhas))):
                linha_c = linhas[j].strip()
                if not linha_c or re.search(
                    r'^(Sexo|Nome\s+do\s+Associado|Matr|Parentesco|Presta)',
                    linha_c,
                    re.IGNORECASE,
                ):
                    continue
                candidato = _limpar_nome_beneficiario(linha_c)
                if _nome_parece_pessoa(candidato):
                    nome = candidato
                    break
            if nome:
                break

    return data, nome


def extrair_campos_bombeiro(texto: str) -> tuple[str, str]:
    if not texto or len(texto.strip()) < 20:
        return '', ''
    texto_norm = _normalizar_texto(texto)
    data = _extrair_data_emissao(texto_norm)
    titular = ''
    dependente = ''
    m_tit = _RE_BOMBEIRO_TITULAR.search(texto_norm)
    if m_tit:
        titular = m_tit.group(1).strip()
    m_dep = _RE_BOMBEIRO_DEPENDENTE.search(texto_norm)
    if m_dep:
        dependente = m_dep.group(1).strip()
    nome = _resolver_nome_bombeiro(titular, dependente) if (titular or dependente) else ''
    return data, nome


def detectar_tipo_guia(texto: str) -> str:
    if not texto or len(texto.strip()) < 15:
        return ''
    t = (texto or '').upper()
    t_ascii = t.replace('Ú', 'U').replace('Á', 'A').replace('É', 'E').replace('Í', 'I').replace('Ó', 'O')
    if 'FUSEX' in t and ('GUIA DE ENCAMINHAMENTO' in t or 'ENCAMINHAMENTO' in t):
        return 'fusex'
    if 'FUNDO DE SAUDE DA PM' in t_ascii or 'PMAC' in t:
        return 'pm'
    if any(m in t_ascii for m in ('CBSAUDE', 'CORPO DE BOMBEIRO')) or (
        'BOMBEIRO' in t and 'ENCAMINHAMENTO' in t
    ):
        return 'bombeiro'
    for regex in (_RE_DATA_AUTORIZACAO, _RE_DATA_AUTORIZACAO_FALLBACK, _RE_DATA_AUTORIZACAO_GENERICO):
        if regex.search(texto):
            return 'tiss'
    return ''


def _extrair_por_tipo(texto: str, tipo: str, convenio_padrao: str = '') -> tuple[str, str, str]:
    if tipo == 'fusex':
        data, nome = extrair_campos_fusex(texto)
        return data, nome, 'FUSEX'
    if tipo == 'pm':
        data, nome = extrair_campos_pm(texto)
        return data, nome, 'PM'
    if tipo == 'bombeiro':
        data, nome = extrair_campos_bombeiro(texto)
        return data, nome, 'BOMBEIRO'
    if tipo == 'tiss':
        data, nome = extrair_campos_tiss(texto)
        return data, nome, _extrair_convenio_tiss(texto, convenio_padrao)
    return '', '', ''


def _parse_resposta_gemini(texto: str) -> tuple[str, str, str, str]:
    texto = (texto or '').strip()
    if texto.startswith('```'):
        texto = re.sub(r'^```(?:json)?\s*|\s*```$', '', texto, flags=re.IGNORECASE | re.DOTALL).strip()
    dados = json.loads(texto)
    if isinstance(dados, dict):
        if dados.get('data_autorizacao') or dados.get('nome_beneficiario'):
            data = _normalizar_data(str(dados.get('data_autorizacao') or ''))
            nome = _limpar_nome_beneficiario(str(dados.get('nome_beneficiario') or ''))
            convenio = str(dados.get('convenio') or '').strip().upper()
            tipo = str(dados.get('tipo_guia') or '').strip().lower()
            return data, nome, convenio, tipo
        guia = dados.get('guia') or {}
        paciente = dados.get('paciente') or {}
        data = _normalizar_data(str(guia.get('data_autorizacao') or guia.get('data_emissao') or ''))
        nome = _limpar_nome_beneficiario(str(paciente.get('nome') or ''))
        convenio = str(dados.get('convenio') or '').strip().upper()
        tipo = str(dados.get('tipo_guia') or '').strip().lower()
        return data, nome, convenio, tipo
    return '', '', '', ''


def _is_erro_cota_gemini(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return '429' in str(exc) or 'quota' in msg or 'rate limit' in msg or 'rate-limit' in msg


def _is_erro_modelo_gemini(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return '404' in str(exc) or 'not found' in msg or 'not supported' in msg


def _mensagem_erro_gemini(exc: BaseException) -> str:
    if _is_erro_cota_gemini(exc):
        return (
            'Cota do Gemini atingida (limite da chave gratuita: ~20 req/dia por modelo). '
            'Se você já comprou créditos, a chave antiga pode continuar no tier gratuito — '
            'gere uma nova API key em https://aistudio.google.com/apikey (projeto com faturamento), '
            'atualize GEMINI_API_KEY no .env e no Render, reinicie o servidor e teste de novo.'
        )
    msg = str(exc)
    if 'api key' in msg.lower() or 'invalid' in msg.lower() and 'key' in msg.lower():
        return (
            'GEMINI_API_KEY inválida ou revogada. '
            'Confira a chave no .env (e no Render) após comprar créditos.'
        )
    return msg


def _modelos_gemini() -> list[str]:
    try:
        from SaudeFinanceira.gemini_config import get_gemini_model

        principal = get_gemini_model()
    except Exception:
        principal = 'gemini-2.5-flash'
    modelos = [principal]
    for fallback in (
        'gemini-2.5-flash',
        'gemini-2.5-flash-lite',
        'gemini-flash-latest',
        'gemini-flash-lite-latest',
    ):
        if fallback not in modelos:
            modelos.append(fallback)
    return modelos


def _gerar_gemini_pdf(model, prompt: str, pdf_bytes: bytes):
    generation_config = genai.GenerationConfig(
        response_mime_type='application/json',
        temperature=0.1,
    )
    return model.generate_content(
        [
            {'mime_type': 'application/pdf', 'data': pdf_bytes},
            prompt,
        ],
        generation_config=generation_config,
    )


def _extrair_com_gemini(pdf_bytes: bytes) -> tuple[str, str, str, str, str]:
    """Extrai data, nome, convênio e tipo via Gemini. Retorna (data, nome, convenio, tipo, erro)."""
    if not GEMINI_AVAILABLE or genai is None:
        return '', '', '', '', 'Gemini não disponível no servidor.'
    try:
        from SaudeFinanceira.gemini_config import get_gemini_api_key

        api_key = get_gemini_api_key()
        if not api_key:
            return '', '', '', '', 'GEMINI_API_KEY não configurada.'

        genai.configure(api_key=api_key)
        prompt = (
            'Analise esta guia médica brasileira. Pode ser TISS SP/SADT (GEAP, Bradesco, Postal, CASSI), '
            'FUSEX, PM (Fundo de Saúde da PM) ou Bombeiro/CBSAÚDE (Guia de Encaminhamento). '
            'Extraia: data (autorização ou emissão), convênio (GEAP, BRADESCO, POSTAL, CASSI, FUSEX, PM ou BOMBEIRO), '
            'nome do paciente/beneficiário e tipo_guia (tiss, fusex, pm ou bombeiro). '
            'Para guia Bombeiro: se dependente for "O Mesmo" ou "Titular", use o nome do titular. '
            'Retorne JSON exatamente neste formato: '
            '{"data_autorizacao":"DD/MM/AAAA","convenio":"...","nome_beneficiario":"NOME COMPLETO","tipo_guia":"..."} '
            'Use string vazia se não encontrar. Não invente dados.'
        )

        ultimo_erro = ''
        for nome_modelo in _modelos_gemini():
            try:
                model = genai.GenerativeModel(nome_modelo)
                response = _gerar_gemini_pdf(model, prompt, pdf_bytes)
                data, nome, convenio, tipo = _parse_resposta_gemini(response.text or '')
                if data or nome:
                    return data, nome, convenio, tipo, ''
            except json.JSONDecodeError as exc:
                logger.warning('JSON inválido do Gemini (%s): %s', nome_modelo, exc)
                ultimo_erro = 'Resposta inválida do Gemini.'
            except Exception as exc:
                ultimo_erro = _mensagem_erro_gemini(exc)
                if _is_erro_cota_gemini(exc) or _is_erro_modelo_gemini(exc):
                    logger.warning('Modelo Gemini indisponível (%s): %s', nome_modelo, exc)
                    continue
                logger.warning('Falha Gemini (%s): %s', nome_modelo, exc)

        return '', '', '', '', ultimo_erro or 'Gemini não extraiu dados do PDF.'
    except Exception as exc:
        logger.warning('Falha Gemini: %s', exc)
        return '', '', '', '', _mensagem_erro_gemini(exc)


def _ler_texto_pdf(pdf_bytes: bytes) -> str:
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            partes = []
            for page in pdf.pages[:2]:
                partes.append(page.extract_text() or '')
            return '\n'.join(partes)
    except Exception as exc:
        logger.warning('Falha pdfplumber: %s', exc)
        return ''


def _ler_texto_pdf_ocr(pdf_bytes: bytes) -> str:
    if not OCR_AVAILABLE or pdfium is None or not _configurar_tesseract():
        return ''
    try:
        with pdfium.PdfDocument(pdf_bytes) as pdf:
            textos = []
            for idx in range(min(len(pdf), 2)):
                page = pdf[idx]
                bitmap = page.render(scale=300 / 72)
                pil_image = bitmap.to_pil()
                if not isinstance(pil_image, Image.Image):
                    pil_image = Image.frombytes(pil_image.mode, pil_image.size, pil_image.tobytes())
                try:
                    textos.append(
                        pytesseract.image_to_string(pil_image, lang='por+eng', config='--psm 6')
                    )
                except Exception:
                    textos.append(
                        pytesseract.image_to_string(pil_image, lang='por', config='--psm 6')
                    )
            return '\n'.join(textos)
    except Exception as exc:
        logger.warning('Falha OCR: %s', exc)
        return ''


def montar_nome_arquivo(data: str, convenio: str, nome: str) -> str:
    data_fmt = _data_para_arquivo(data)
    conv_fmt = (convenio or '').strip().upper()
    nome_fmt = _limpar_nome_beneficiario(nome)
    if not data_fmt or not conv_fmt or not nome_fmt:
        raise ValueError('Data, convênio ou nome não encontrados.')
    return f'{data_fmt} - {conv_fmt} - {nome_fmt}.pdf'


def montar_nome_arquivo_geap(data_autorizacao: str, nome_beneficiario: str) -> str:
    """Retrocompatível — assume convênio GEAP."""
    return montar_nome_arquivo(data_autorizacao, 'GEAP', nome_beneficiario)


def _nome_unico(nome: str, usados: set[str]) -> str:
    if nome not in usados:
        usados.add(nome)
        return nome
    stem, ext = os.path.splitext(nome)
    contador = 2
    while True:
        candidato = f'{stem} ({contador}){ext}'
        if candidato not in usados:
            usados.add(candidato)
            return candidato
        contador += 1


def processar_arquivo(
    arquivo_nome: str,
    pdf_bytes: bytes,
    convenio_padrao: str = '',
) -> ResultadoRenomearGuiaGeap:
    resultado = ResultadoRenomearGuiaGeap(arquivo_original=arquivo_nome)
    gemini_erro = ''
    data_arq, conv_arq = _extrair_metadados_nome_arquivo(arquivo_nome)

    texto = _ler_texto_pdf(pdf_bytes)
    texto_ocr = ''
    ocr_usado = False

    tipo = detectar_tipo_guia(texto)
    data, nome, convenio = _extrair_por_tipo(texto, tipo, convenio_padrao) if tipo else ('', '', '')
    data, nome = _normalizar_data(data), _limpar_nome_beneficiario(nome)
    if not _campos_completos(data, nome, convenio):
        data = data if _data_valida(data) else ''
        nome = nome if _nome_parece_pessoa(nome) else ''

    if not _campos_completos(data, nome, convenio):
        if _configurar_tesseract():
            texto_ocr = _ler_texto_pdf_ocr(pdf_bytes)
            ocr_usado = bool(texto_ocr.strip())
            if texto_ocr.strip():
                if not tipo:
                    tipo = detectar_tipo_guia(texto_ocr)
                d2, n2, c2 = _extrair_por_tipo(
                    texto_ocr, tipo or detectar_tipo_guia(texto_ocr), convenio_padrao
                )
                if not tipo:
                    tipo = detectar_tipo_guia(texto_ocr)
                d2, n2 = _normalizar_data(d2), _limpar_nome_beneficiario(n2)
                data = data or (d2 if _data_valida(d2) else '')
                nome = nome or (n2 if _nome_parece_pessoa(n2) else '')
                convenio = convenio or c2

    if not _campos_completos(data, nome, convenio):
        texto_merged = '\n'.join(p for p in (texto, texto_ocr) if p and p.strip())
        if texto_merged.strip():
            tipo_m = tipo or detectar_tipo_guia(texto_merged)
            d3, n3, c3 = _extrair_por_tipo(texto_merged, tipo_m, convenio_padrao)
            if not tipo and tipo_m:
                tipo = tipo_m
            d3, n3 = _normalizar_data(d3), _limpar_nome_beneficiario(n3)
            data = data or (d3 if _data_valida(d3) else '')
            nome = nome or (n3 if _nome_parece_pessoa(n3) else '')
            convenio = convenio or c3

    if not _campos_completos(data, nome, convenio):
        data_g, nome_g, conv_g, tipo_g, gemini_erro = _extrair_com_gemini(pdf_bytes)
        data_g, nome_g = _normalizar_data(data_g), _limpar_nome_beneficiario(nome_g)
        data = data or (data_g if _data_valida(data_g) else '')
        nome = nome or (nome_g if _nome_parece_pessoa(nome_g) else '')
        convenio = convenio or conv_g or (convenio_padrao or '').strip().upper()
        if not tipo and tipo_g:
            tipo = tipo_g

    if not convenio and convenio_padrao:
        convenio = convenio_padrao.strip().upper()
    if not convenio:
        convenio = conv_arq
    if not data:
        data = data_arq

    data = _normalizar_data(data)
    nome = _limpar_nome_beneficiario(nome)

    if not _campos_completos(data, nome, convenio):
        if not data:
            msg = 'Data não encontrada ou inválida.'
        elif not nome:
            msg = 'Nome do beneficiário não encontrado.'
            if 'TABELA DE INSUMO' in (arquivo_nome or '').upper() or 'FALTA TABELA' in (texto or '').upper():
                msg += ' Este PDF parece ser relatório de insumo, não guia TISS com paciente.'
        else:
            msg = 'Convênio não identificado.'
        if ocr_usado:
            msg += ' OCR não localizou;'
        if gemini_erro:
            msg += f' Gemini: {gemini_erro}'
        elif not GEMINI_AVAILABLE:
            msg += ' Configure GEMINI_API_KEY no Render para PDFs escaneados.'
        else:
            msg += ' Confira se o PDF é guia TISS (campo 10 - Nome) ou preencha Convênio padrão.'
        resultado.erro = msg
        return resultado

    try:
        novo_nome = montar_nome_arquivo(data, convenio, nome)
    except ValueError as exc:
        resultado.erro = str(exc)
        return resultado

    resultado.data_autorizacao = data
    resultado.nome_beneficiario = nome
    resultado.convenio = convenio
    resultado.tipo_guia = tipo or convenio.lower()
    resultado.arquivo_novo = novo_nome
    resultado.pdf_bytes = pdf_bytes
    resultado.ok = True
    return resultado


def processar_arquivo_geap(arquivo_nome: str, pdf_bytes: bytes) -> ResultadoRenomearGuiaGeap:
    """Retrocompatível."""
    return processar_arquivo(arquivo_nome, pdf_bytes)


def renomear_guias_geap_arquivos(
    arquivos,
    convenio_padrao: str = '',
    empresa_id: int | None = None,
    anexar_no_sistema: bool = True,
) -> list[ResultadoRenomearGuiaGeap]:
    """Processa vários PDFs e devolve resultados com bytes para salvar localmente."""
    from faturamento_medico.services.vincular_guia_anexo import (
        anexar_guia_ao_faturamento,
        sugestao_para_dict,
    )

    resultados: list[ResultadoRenomearGuiaGeap] = []
    nomes_usados: set[str] = set()

    for arquivo in arquivos:
        nome_original = getattr(arquivo, 'name', 'arquivo.pdf') or 'arquivo.pdf'
        if not nome_original.lower().endswith('.pdf'):
            resultados.append(
                ResultadoRenomearGuiaGeap(
                    arquivo_original=nome_original,
                    erro='Apenas arquivos PDF são aceitos.',
                )
            )
            continue

        pdf_bytes = arquivo.read()
        resultado = processar_arquivo(nome_original, pdf_bytes, convenio_padrao=convenio_padrao)
        if resultado.ok:
            nome_final = _nome_unico(resultado.arquivo_novo, nomes_usados)
            resultado.arquivo_novo = nome_final

            if anexar_no_sistema and empresa_id:
                resultado.anexo_tentado = True
                vinculo = anexar_guia_ao_faturamento(
                    empresa_id=empresa_id,
                    nome_paciente=resultado.nome_beneficiario,
                    convenio=resultado.convenio,
                    data_guia_str=resultado.data_autorizacao,
                    pdf_bytes=resultado.pdf_bytes,
                    nome_arquivo=resultado.arquivo_novo,
                )
                resultado.anexo_ok = vinculo.ok
                resultado.anexo_mensagem = vinculo.mensagem
                resultado.anexo_erro = vinculo.erro
                resultado.faturamento_id = vinculo.faturamento_id
                resultado.anexo_sugestoes = [sugestao_para_dict(s) for s in vinculo.sugestoes]

        resultados.append(resultado)

    return resultados
