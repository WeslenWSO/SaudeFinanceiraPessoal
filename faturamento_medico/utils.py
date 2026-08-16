import os
import json
import logging
import tempfile
import re
from typing import List, Dict, Any
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile

from SaudeFinanceira.google_grpc_env import silenciar_logs_grpc_google

silenciar_logs_grpc_google()

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

logger = logging.getLogger(__name__)

def processar_arquivos_com_gemini(arquivos: List[InMemoryUploadedFile], tipo_documento: str = 'faturamento') -> Dict[str, Any]:
    """
    Processa múltiplos arquivos usando Google Gemini para extrair dados de documentos médicos.

    Args:
        arquivos: Lista de arquivos InMemoryUploadedFile
        tipo_documento: Tipo do documento ('faturamento' ou 'consulta')

    Returns:
        Dict com dados extraídos dos arquivos
    """
    try:
        # Verificar se Gemini está disponível
        if not GEMINI_AVAILABLE:
            logger.error("Gemini AI não está disponível. google-generativeai não está instalado.")
            return {"error": "Gemini AI não está disponível. Instale google-generativeai."}

        # Configurar API do Gemini
        api_key = getattr(settings, 'GEMINI_API_KEY', None)
        if not api_key:
            logger.warning("GEMINI_API_KEY não configurada")
            return {}

        genai.configure(api_key=api_key)

        # Configurar modelo
        model = genai.GenerativeModel('gemini-2.5-flash')

        dados_consolidados = {
            'nome': '',
            'carteirinha': '',
            'guia': '',
            'numero_guia_lancada': '',
            'data_autorizacao': '',
            'data_internacao_cirurgia': '',
            'local': '',
            'medico': '',
            'anestesista': '',
            'convenio': '',
            'apartamento_enfermaria': '',
            'urgencia': '',
            'servicos': [],
            'observacoes': ''
        }

        for arquivo in arquivos:
            try:
                logger.info(f"Processando arquivo: {arquivo.name}")

                # Salvar arquivo temporariamente para upload
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(arquivo.name)[1]) as temp_file:
                    for chunk in arquivo.chunks():
                        temp_file.write(chunk)
                    temp_file_path = temp_file.name

                try:
                    # Fazer upload do arquivo para Gemini
                    uploaded_file = genai.upload_file(temp_file_path, mime_type=arquivo.content_type)

                    # Preparar prompt baseado no tipo de documento
                    if tipo_documento == 'faturamento':
                        prompt = """
                         Analise este documento médico (guia, fatura, relatório, etc.) e extraia informações estruturadas.

                         INSTRUÇÕES IMPORTANTES:
                         1. Procure por dados do PACIENTE: nome completo, carteirinha/plano
                         2. Procure por dados da GUIA: número da guia, número da guia lançada, data de autorização, data de internação/cirurgia
                         3. Procure por SERVIÇOS REALIZADOS: códigos TUSS/CBHPM, descrições, quantidades, valores unitários
                         4. Procure por PROFISSIONAIS: médico, anestesista
                         5. Procure por LOCALIZAÇÃO: local (hospital, clínica), apartamento/enfermaria
                         6. Procure por CONVÊNIO e URGÊNCIA
                         7. Procure por VALORES: valores unitários, totais, taxas

                         IMPORTANTE: Responda APENAS com o JSON puro, sem qualquer texto adicional, sem markdown, sem explicações. RETORNE um objeto JSON válido com esta estrutura exata:
                         {
                             "paciente": {
                                 "nome": "string ou vazio",
                                 "carteirinha": "string ou vazio"
                             },
                             "guia": {
                                 "numero": "string ou vazio",
                                 "numero_guia_lancada": "string ou vazio",
                                 "data_autorizacao": "string ou vazio",
                                 "data_internacao_cirurgia": "string ou vazio"
                             },
                             "servicos": [
                                 {
                                     "codigo": "string",
                                     "descricao": "string",
                                     "quantidade": "number",
                                     "valor_unitario": "number"
                                 }
                             ],
                             "profissionais": {
                                 "medico": "string ou vazio",
                                 "anestesista": "string ou vazio"
                             },
                             "localizacao": {
                                 "local": "string ou vazio",
                                 "apartamento_enfermaria": "string ou vazio"
                             },
                             "convenio": "string ou vazio",
                             "urgencia": "string ou vazio",
                             "valores": {
                                 "total_geral": "number",
                                 "observacoes": "string"
                             }
                         }

                         REGRAS:
                         - Se não encontrar uma informação, use string vazia "" ou 0 para números
                         - Para valores monetários, use formato numérico (ex: 150.50)
                         - Liste todos os serviços encontrados em um array
                         - Seja preciso e não invente dados
                         - Para apartamento_enfermaria, use "apartamento" ou "enfermaria" ou deixe vazio
                         - Para urgencia, use "sim" ou "não" ou deixe vazio
                         """
                    elif tipo_documento == 'consulta':
                        prompt = """
                         Analise este documento médico de consulta ou atendimento e extraia informações estruturadas.

                         INSTRUÇÕES IMPORTANTES:
                         1. Procure por dados do PACIENTE: nome completo, data de nascimento, idade, convênio, carteirinha/plano
                         2. Procure por dados do MÉDICO: nome completo, especialidade, CRM
                         3. Procure por DATA DO ATENDIMENTO
                         4. Procure por OBSERVAÇÃO ou descrição do atendimento

                         IMPORTANTE: Responda APENAS com o JSON puro, sem qualquer texto adicional, sem markdown, sem explicações. RETORNE um objeto JSON válido com esta estrutura exata:
                         {
                             "paciente": {
                                 "nome": "string ou vazio",
                                 "data_nascimento": "string ou vazio",
                                 "idade": "number ou 0",
                                 "convenio": "string ou vazio",
                                 "carteirinha": "string ou vazio"
                             },
                             "medico": {
                                 "nome": "string ou vazio",
                                 "especialidade": "string ou vazio",
                                 "crm": "string ou vazio"
                             },
                             "data_atendimento": "string ou vazio",
                             "observacao": "string ou vazio"
                         }

                         REGRAS:
                         - Se não encontrar uma informação, use string vazia "" ou 0 para números
                         - Para datas, use formato DD/MM/YYYY se possível
                         - Seja preciso e não invente dados
                         """
                    else:
                        logger.error(f"Tipo de documento não suportado: {tipo_documento}")
                        continue

                    # Gerar resposta
                    response = model.generate_content([prompt, uploaded_file])

                    # Processar resposta JSON
                    texto_resposta = response.text.strip()
                    logger.info(f"Resposta bruta do Gemini: {texto_resposta}")

                    # Limpar resposta (remover markdown se presente)
                    if texto_resposta.startswith('```json'):
                        texto_resposta = texto_resposta[7:]
                    if texto_resposta.startswith('```'):
                        texto_resposta = texto_resposta[3:]
                    if texto_resposta.endswith('```'):
                        texto_resposta = texto_resposta[:-3]

                    texto_resposta = texto_resposta.strip()
                    logger.info(f"Resposta limpa: {texto_resposta}")

                    try:
                        dados_arquivo = json.loads(texto_resposta)
                        logger.info(f"Dados extraídos de {arquivo.name}: {dados_arquivo}")

                        # Consolidar dados baseado no tipo de documento
                        if tipo_documento == 'faturamento':
                            # Consolidar dados (usar primeiro valor encontrado que não seja vazio)
                            if dados_arquivo.get('paciente', {}).get('nome') and not dados_consolidados['nome']:
                                dados_consolidados['nome'] = dados_arquivo['paciente']['nome']

                            if dados_arquivo.get('paciente', {}).get('carteirinha') and not dados_consolidados['carteirinha']:
                                dados_consolidados['carteirinha'] = dados_arquivo['paciente']['carteirinha']

                            if dados_arquivo.get('guia', {}).get('numero') and not dados_consolidados['guia']:
                                dados_consolidados['guia'] = dados_arquivo['guia']['numero']

                            if dados_arquivo.get('guia', {}).get('numero_guia_lancada') and not dados_consolidados['numero_guia_lancada']:
                                dados_consolidados['numero_guia_lancada'] = dados_arquivo['guia']['numero_guia_lancada']

                            if dados_arquivo.get('guia', {}).get('data_autorizacao') and not dados_consolidados['data_autorizacao']:
                                dados_consolidados['data_autorizacao'] = dados_arquivo['guia']['data_autorizacao']

                            if dados_arquivo.get('guia', {}).get('data_internacao_cirurgia') and not dados_consolidados['data_internacao_cirurgia']:
                                dados_consolidados['data_internacao_cirurgia'] = dados_arquivo['guia']['data_internacao_cirurgia']

                            if dados_arquivo.get('profissionais', {}).get('medico') and not dados_consolidados['medico']:
                                dados_consolidados['medico'] = dados_arquivo['profissionais']['medico']

                            if dados_arquivo.get('profissionais', {}).get('anestesista') and not dados_consolidados['anestesista']:
                                dados_consolidados['anestesista'] = dados_arquivo['profissionais']['anestesista']

                            if dados_arquivo.get('localizacao', {}).get('local') and not dados_consolidados['local']:
                                dados_consolidados['local'] = dados_arquivo['localizacao']['local']

                            if dados_arquivo.get('localizacao', {}).get('apartamento_enfermaria') and not dados_consolidados['apartamento_enfermaria']:
                                dados_consolidados['apartamento_enfermaria'] = dados_arquivo['localizacao']['apartamento_enfermaria']

                            if dados_arquivo.get('convenio') and not dados_consolidados['convenio']:
                                dados_consolidados['convenio'] = dados_arquivo['convenio']

                            if dados_arquivo.get('urgencia') and not dados_consolidados['urgencia']:
                                dados_consolidados['urgencia'] = dados_arquivo['urgencia']

                            # Adicionar serviços encontrados
                            if dados_arquivo.get('servicos'):
                                dados_consolidados['servicos'].extend(dados_arquivo['servicos'])

                            # Consolidar observações
                            if dados_arquivo.get('valores', {}).get('observacoes'):
                                if dados_consolidados['observacoes']:
                                    dados_consolidados['observacoes'] += "; " + dados_arquivo['valores']['observacoes']
                                else:
                                    dados_consolidados['observacoes'] = dados_arquivo['valores']['observacoes']

                        elif tipo_documento == 'consulta':
                            # Consolidar dados de consulta
                            paciente = dados_arquivo.get('paciente', {})
                            if paciente.get('nome') and not dados_consolidados['paciente']['nome']:
                                dados_consolidados['paciente']['nome'] = paciente['nome']
                            if paciente.get('data_nascimento') and not dados_consolidados['paciente']['data_nascimento']:
                                dados_consolidados['paciente']['data_nascimento'] = paciente['data_nascimento']
                            if paciente.get('idade') and not dados_consolidados['paciente']['idade']:
                                dados_consolidados['paciente']['idade'] = paciente['idade']
                            if paciente.get('convenio') and not dados_consolidados['paciente']['convenio']:
                                dados_consolidados['paciente']['convenio'] = paciente['convenio']
                            if paciente.get('carteirinha') and not dados_consolidados['paciente']['carteirinha']:
                                dados_consolidados['paciente']['carteirinha'] = paciente['carteirinha']

                            medico = dados_arquivo.get('medico', {})
                            if medico.get('nome') and not dados_consolidados['medico']['nome']:
                                dados_consolidados['medico']['nome'] = medico['nome']
                            if medico.get('especialidade') and not dados_consolidados['medico']['especialidade']:
                                dados_consolidados['medico']['especialidade'] = medico['especialidade']
                            if medico.get('crm') and not dados_consolidados['medico']['crm']:
                                dados_consolidados['medico']['crm'] = medico['crm']

                            if dados_arquivo.get('data_atendimento') and not dados_consolidados['data_atendimento']:
                                dados_consolidados['data_atendimento'] = dados_arquivo['data_atendimento']

                            if dados_arquivo.get('observacao') and not dados_consolidados['observacao']:
                                dados_consolidados['observacao'] = dados_arquivo['observacao']

                    except json.JSONDecodeError as e:
                        logger.error(f"Erro ao fazer parse JSON da resposta do Gemini para {arquivo.name}: {e}")
                        logger.error(f"Resposta recebida: {texto_resposta}")
                        continue

                finally:
                    # Limpar arquivo temporário
                    try:
                        os.unlink(temp_file_path)
                    except:
                        pass

            except Exception as e:
                logger.error(f"Erro ao processar arquivo {arquivo.name}: {str(e)}")
                continue

        logger.info(f"Dados consolidados finais: {dados_consolidados}")
        return dados_consolidados

    except Exception as e:
        logger.error(f"Erro geral no processamento com Gemini: {str(e)}")
        return {}


def processar_arquivos_com_ocr(arquivos: List[InMemoryUploadedFile], tipo_documento: str = 'faturamento') -> Dict[str, Any]:
    """
    Processa múltiplos arquivos usando OCR para extrair dados de faturamento médico.

    Args:
        arquivos: Lista de arquivos InMemoryUploadedFile

    Returns:
        Dict com dados extraídos dos arquivos via OCR
    """
    logger.info(f"OCR_AVAILABLE: {OCR_AVAILABLE}")

    if not OCR_AVAILABLE:
        logger.error("OCR não está disponível. pytesseract não está instalado.")
        return {"error": "OCR não está disponível. Instale pytesseract e Tesseract OCR."}

    try:
        logger.info(f"Iniciando processamento OCR para {len(arquivos)} arquivo(s)")
        if tipo_documento == 'faturamento':
            dados_consolidados = {
                'nome': '',
                'carteirinha': '',
                'guia': '',
                'numero_guia_lancada': '',
                'data_autorizacao': '',
                'data_internacao_cirurgia': '',
                'local': '',
                'medico': '',
                'anestesista': '',
                'convenio': '',
                'apartamento_enfermaria': '',
                'urgencia': '',
                'servicos': [],
                'observacoes': ''
            }
        elif tipo_documento == 'consulta':
            dados_consolidados = {
                'paciente': {
                    'nome': '',
                    'data_nascimento': '',
                    'idade': 0,
                    'convenio': '',
                    'carteirinha': ''
                },
                'medico': {
                    'nome': '',
                    'especialidade': '',
                    'crm': ''
                },
                'data_atendimento': '',
                'observacao': ''
            }
        else:
            logger.error(f"Tipo de documento não suportado para consolidação: {tipo_documento}")
            return {}

        for arquivo in arquivos:
            try:
                logger.info(f"Processando arquivo com OCR: {arquivo.name}")

                # Salvar arquivo temporariamente para processamento OCR
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(arquivo.name)[1]) as temp_file:
                    for chunk in arquivo.chunks():
                        temp_file.write(chunk)
                    temp_file_path = temp_file.name

                try:
                    # Abrir imagem com PIL
                    logger.info(f"Abrindo imagem: {temp_file_path}")
                    imagem = Image.open(temp_file_path)
                    logger.info(f"Imagem aberta. Formato: {imagem.format}, Tamanho: {imagem.size}")

                    # Verificar se é uma imagem válida
                    if imagem.format not in ['JPEG', 'PNG', 'TIFF', 'BMP', 'GIF']:
                        logger.warning(f"Formato de arquivo não suportado para OCR: {imagem.format}")
                        continue

                    # Extrair texto com OCR
                    logger.info("Iniciando extração OCR...")
                    texto_extraido = pytesseract.image_to_string(imagem, lang='por+eng')
                    logger.info(f"Texto extraído via OCR (comprimento: {len(texto_extraido)}): {texto_extraido[:500]}...")

                    # Processar texto extraído
                    dados_arquivo = extrair_dados_do_texto(texto_extraido)
                    logger.info(f"Dados extraídos do OCR: {dados_arquivo}")

                    # Consolidar dados
                    if dados_arquivo.get('nome') and not dados_consolidados['nome']:
                        dados_consolidados['nome'] = dados_arquivo['nome']

                    if dados_arquivo.get('carteirinha') and not dados_consolidados['carteirinha']:
                        dados_consolidados['carteirinha'] = dados_arquivo['carteirinha']

                    if dados_arquivo.get('guia') and not dados_consolidados['guia']:
                        dados_consolidados['guia'] = dados_arquivo['guia']

                    if dados_arquivo.get('numero_guia_lancada') and not dados_consolidados['numero_guia_lancada']:
                        dados_consolidados['numero_guia_lancada'] = dados_arquivo['numero_guia_lancada']

                    if dados_arquivo.get('data_autorizacao') and not dados_consolidados['data_autorizacao']:
                        dados_consolidados['data_autorizacao'] = dados_arquivo['data_autorizacao']

                    if dados_arquivo.get('data_internacao_cirurgia') and not dados_consolidados['data_internacao_cirurgia']:
                        dados_consolidados['data_internacao_cirurgia'] = dados_arquivo['data_internacao_cirurgia']

                    if dados_arquivo.get('local') and not dados_consolidados['local']:
                        dados_consolidados['local'] = dados_arquivo['local']

                    if dados_arquivo.get('medico') and not dados_consolidados['medico']:
                        dados_consolidados['medico'] = dados_arquivo['medico']

                    if dados_arquivo.get('anestesista') and not dados_consolidados['anestesista']:
                        dados_consolidados['anestesista'] = dados_arquivo['anestesista']

                    if dados_arquivo.get('convenio') and not dados_consolidados['convenio']:
                        dados_consolidados['convenio'] = dados_arquivo['convenio']

                    if dados_arquivo.get('apartamento_enfermaria') and not dados_consolidados['apartamento_enfermaria']:
                        dados_consolidados['apartamento_enfermaria'] = dados_arquivo['apartamento_enfermaria']

                    if dados_arquivo.get('urgencia') and not dados_consolidados['urgencia']:
                        dados_consolidados['urgencia'] = dados_arquivo['urgencia']

                    # Adicionar serviços encontrados
                    if dados_arquivo.get('servicos'):
                        dados_consolidados['servicos'].extend(dados_arquivo['servicos'])

                    # Consolidar observações
                    if dados_arquivo.get('observacoes'):
                        if dados_consolidados['observacoes']:
                            dados_consolidados['observacoes'] += "; " + dados_arquivo['observacoes']
                        else:
                            dados_consolidados['observacoes'] = dados_arquivo['observacoes']

                finally:
                    # Limpar arquivo temporário
                    try:
                        os.unlink(temp_file_path)
                    except:
                        pass

            except Exception as e:
                logger.error(f"Erro ao processar arquivo {arquivo.name} com OCR: {str(e)}")
                continue

        logger.info(f"Dados consolidados finais via OCR: {dados_consolidados}")
        return dados_consolidados

    except Exception as e:
        logger.error(f"Erro geral no processamento com OCR: {str(e)}")
        return {}


def extrair_dados_do_texto(texto: str) -> Dict[str, Any]:
    """
    Extrai dados específicos do texto usando expressões regulares e padrões.

    Args:
        texto: Texto extraído via OCR

    Returns:
        Dict com dados extraídos
    """
    logger.info(f"Texto recebido para extração OCR (primeiros 200 chars): {texto[:200]}")

    dados = {
        'nome': '',
        'carteirinha': '',
        'guia': '',
        'numero_guia_lancada': '',
        'data_autorizacao': '',
        'data_internacao_cirurgia': '',
        'local': '',
        'medico': '',
        'anestesista': '',
        'convenio': '',
        'apartamento_enfermaria': '',
        'urgencia': '',
        'servicos': [],
        'observacoes': ''
    }

    # Converter para maiúsculo para facilitar matching
    texto_upper = texto.upper()
    linhas = texto.split('\n')

    logger.info(f"Texto em maiúsculo (primeiras 5 linhas): {linhas[:5]}")

    # Padrões de busca
    padroes = {
        'nome': [
            r'NOME[:\s]*([A-Z\s]+)',
            r'PACIENTE[:\s]*([A-Z\s]+)',
            r'BENEFICIÁRIO[:\s]*([A-Z\s]+)'
        ],
        'carteirinha': [
            r'CARTEIRINHA[:\s]*([0-9\s\-]+)',
            r'PLANO[:\s]*([0-9\s\-]+)',
            r'CARTÃO[:\s]*([0-9\s\-]+)'
        ],
        'guia': [
            r'GUIA[:\s]*([0-9]+)',
            r'NÚMERO[:\s]*([0-9]+)',
            r'GUIA\s+Nº[:\s]*([0-9]+)'
        ],
        'numero_guia_lancada': [
            r'GUIA\s+LANÇADA[:\s]*([0-9]+)',
            r'NÚMERO\s+GUIA\s+LANÇADA[:\s]*([0-9]+)'
        ],
        'data_autorizacao': [
            r'DATA\s+AUTORIZAÇÃO[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',
            r'DT\s+AUT[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})'
        ],
        'data_internacao_cirurgia': [
            r'DATA\s+INTERNAÇÃO[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',
            r'DATA\s+CIRURGIA[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{4})',
            r'DT\s+INTERN[:\s]*([0-9]{2}/[0-9]{2}/[0-9]{2}/[0-9]{4})'
        ],
        'local': [
            r'LOCAL[:\s]*([A-Z\s]+)',
            r'HOSPITAL[:\s]*([A-Z\s]+)',
            r'CLÍNICA[:\s]*([A-Z\s]+)'
        ],
        'medico': [
            r'MÉDICO[:\s]*([A-Z\s]+)',
            r'DR[\.]*[:\s]*([A-Z\s]+)'
        ],
        'anestesista': [
            r'ANESTESISTA[:\s]*([A-Z\s]+)',
            r'DR[\.]*\s+ANEST[:\s]*([A-Z\s]+)'
        ],
        'convenio': [
            r'CONVÊNIO[:\s]*([A-Z\s]+)',
            r'PLANO[:\s]*([A-Z\s]+)'
        ]
    }

    # Buscar padrões no texto
    for campo, regex_list in padroes.items():
        for regex in regex_list:
            match = re.search(regex, texto_upper)
            if match:
                valor = match.group(1).strip()
                if valor and len(valor) > 2:  # Evitar matches muito curtos
                    dados[campo] = valor
                    break

    # Buscar apartamento/enfermaria
    if 'APARTAMENTO' in texto_upper:
        dados['apartamento_enfermaria'] = 'Apartamento'
    elif 'ENFERMARIA' in texto_upper:
        dados['apartamento_enfermaria'] = 'Enfermaria'

    # Buscar urgência
    if 'URGÊNCIA' in texto_upper or 'URGENTE' in texto_upper:
        dados['urgencia'] = 'Sim'
    elif 'ELETIVA' in texto_upper:
        dados['urgencia'] = 'Não'

    # Tentar extrair serviços (busca por códigos e valores)
    servicos_encontrados = []
    linhas_servicos = [linha for linha in linhas if re.search(r'\d{4,}', linha) and re.search(r'R\$|\d+,\d{2}', linha)]

    for linha in linhas_servicos[:5]:  # Limitar a 5 serviços
        # Tentar extrair código, descrição e valor
        match = re.search(r'(\d{4,})\s+(.+?)\s+(?:R\$\s*)?(\d+(?:[,.]\d{2})?)', linha)
        if match:
            codigo = match.group(1)
            descricao = match.group(2).strip()
            valor_str = match.group(3).replace(',', '.')

            try:
                valor = float(valor_str)
                servicos_encontrados.append({
                    'codigo': codigo,
                    'descricao': descricao,
                    'quantidade': 1,
                    'valor_unitario': valor
                })
            except ValueError:
                continue

    dados['servicos'] = servicos_encontrados

    logger.info(f"Dados extraídos do texto OCR: {dados}")
    logger.info(f"Total de campos preenchidos: {sum(1 for v in dados.values() if v and v != [])}")
    return dados




def get_nested_value(d: dict, keys: list):
    """
    Obtém valor aninhado em dict.
    """
    for key in keys:
        if isinstance(d, dict):
            d = d.get(key)
        else:
            return None
    return d if d != '' and d != 0 else None


def avaliar_extracao_gemini(dados_extraidos: Dict[str, Any], tipo_documento: str) -> Dict[str, Any]:
    """
    Avalia a qualidade da extração feita pelo Gemini.

    Args:
        dados_extraidos: Dados extraídos
        tipo_documento: Tipo do documento ('faturamento' ou 'consulta')

    Returns:
        Dict com avaliação da extração
    """
    print(f"avaliar_extracao_gemini called with tipo_documento: {tipo_documento}")
    avaliacao = {
        'pontuacao': 0,
        'total_campos': 0,
        'campos_preenchidos': 0,
        'campos_faltando': [],
        'qualidade': 'baixa'
    }

    if tipo_documento == 'faturamento':
        campos_obrigatorios = ['nome', 'guia', 'medico', 'convenio']
        campos_opcionais = ['carteirinha', 'numero_guia_lancada', 'data_autorizacao', 'data_internacao_cirurgia', 'local', 'anestesista', 'apartamento_enfermaria', 'urgencia', 'servicos', 'observacoes']

        all_campos = campos_obrigatorios + campos_opcionais
        avaliacao['total_campos'] = len(all_campos)

        for campo in all_campos:
            if dados_extraidos.get(campo) and dados_extraidos[campo] != '' and dados_extraidos[campo] != []:
                avaliacao['campos_preenchidos'] += 1
            else:
                avaliacao['campos_faltando'].append(campo)

        # Pontuação: obrigatórios valem 1 ponto, opcionais 0.5
        pontuacao_obrigatorios = sum(1 for c in campos_obrigatorios if dados_extraidos.get(c) and dados_extraidos[c] != '' and dados_extraidos[c] != [])
        pontuacao_opcionais = sum(0.5 for c in campos_opcionais if dados_extraidos.get(c) and dados_extraidos[c] != '' and dados_extraidos[c] != [])
        avaliacao['pontuacao'] = pontuacao_obrigatorios + pontuacao_opcionais

    elif tipo_documento == 'consulta':
        print("Entrou no elif consulta")
        campos_obrigatorios = ['paciente.nome', 'medico.nome', 'data_atendimento', 'observacao']
        campos_opcionais = ['paciente.data_nascimento', 'paciente.idade', 'paciente.convenio', 'paciente.carteirinha', 'medico.especialidade', 'medico.crm']

        all_campos = campos_obrigatorios + campos_opcionais
        avaliacao['total_campos'] = len(all_campos)
        print(f"total_campos: {avaliacao['total_campos']}")

        for campo in all_campos:
            parts = campo.split('.')
            value = get_nested_value(dados_extraidos, parts)
            print(f"Campo {campo}: value={value}")
            if value is not None:
                avaliacao['campos_preenchidos'] += 1
            else:
                avaliacao['campos_faltando'].append(campo)

        # Pontuação
        pontuacao_obrigatorios = sum(1 for c in campos_obrigatorios if get_nested_value(dados_extraidos, c.split('.')) is not None)
        pontuacao_opcionais = sum(0.5 for c in campos_opcionais if get_nested_value(dados_extraidos, c.split('.')) is not None)
        avaliacao['pontuacao'] = pontuacao_obrigatorios + pontuacao_opcionais
        print(f"pontuacao: {avaliacao['pontuacao']}")

    # Determinar qualidade baseada na porcentagem de campos preenchidos
    if avaliacao['total_campos'] > 0:
        porcentagem = (avaliacao['campos_preenchidos'] / avaliacao['total_campos']) * 100
        if porcentagem >= 80:
            avaliacao['qualidade'] = 'alta'
        elif porcentagem >= 60:
            avaliacao['qualidade'] = 'media'
        else:
            avaliacao['qualidade'] = 'baixa'

    return avaliacao


def testar_extracao_consulta_exemplo():
    """
    Função de teste para demonstrar a avaliação da extração com dados de exemplo.
    Simula os dados extraídos do documento de consulta fornecido.
    """
    # Dados simulados baseados no exemplo fornecido
    dados_exemplo = {
        'paciente': {
            'nome': 'Eva Maria de Azevedo Silva',
            'data_nascimento': '02/04/1962',
            'idade': 63,
            'convenio': 'Unimed',
            'carteirinha': '2661389000117014'
        },
        'medico': {
            'nome': 'Ducigelda Casas Sousa',
            'especialidade': 'Cirurgia Geral',
            'crm': '1193 AC'
        },
        'data_atendimento': '01/08/2025',
        'observacao': 'O atendimento foi para um nódulo na tireoide (lobo esquerdo) que a paciente tem há um ano. O resultado da punção aspirativa por agulha fina (PAAF) indica um resultado de Bethesda II, que geralmente é compatível com um achado benigno.'
    }

    print("=== TESTE DE EXTRAÇÃO - DADOS DE EXEMPLO ===")
    print(f"Dados simulados: {dados_exemplo}")

    # Debug: testar get_nested_value
    campos_teste = ['paciente.nome', 'medico.nome', 'data_atendimento', 'observacao']
    for campo in campos_teste:
        parts = campo.split('.')
        value = get_nested_value(dados_exemplo, parts)
        print(f"Campo {campo}: parts={parts}, value={value}, type={type(value)}")

    # Avaliar a extração
    try:
        avaliacao = avaliar_extracao_gemini(dados_exemplo, 'consulta')
        print(f"avaliacao type: {type(avaliacao)}")
    except Exception as e:
        print(f"Erro ao avaliar: {e}")
        import traceback
        traceback.print_exc()
        return None

    if avaliacao is None:
        print("avaliacao retornou None!")
        return None

    print("=== AVALIAÇÃO DA EXTRAÇÃO ===")
    print(f"Total de campos: {avaliacao['total_campos']}")
    print(f"Campos preenchidos: {avaliacao['campos_preenchidos']}")
    print(f"Pontuação: {avaliacao['pontuacao']}")
    print(f"Qualidade: {avaliacao['qualidade']}")
    print(f"Campos faltando: {avaliacao['campos_faltando']}")

    return avaliacao

    return avaliacao