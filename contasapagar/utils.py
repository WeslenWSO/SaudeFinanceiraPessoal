import logging
import re
from datetime import datetime, date, timedelta
from decimal import Decimal
from typing import List, Dict, Optional

from django.core.files.base import ContentFile
from django.conf import settings
from .models import ContasaPagar
from empresa.models import Empresa
from fornecedor.models import Fornecedor
from categoria.models import Categoria
from cobranca.models import Cobranca
from extrato.models import ContaBancaria
from socio.models import Socio
import tempfile
import os

logger = logging.getLogger(__name__)

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


def limpar_cnpj(cnpj: str) -> str:
    """
    Remove pontos, barras e hífens do CNPJ, deixando apenas números
    """
    if not cnpj:
        return ""
    return ''.join(filter(str.isdigit, cnpj))


def valor_br_para_decimal(valor_str: str) -> Decimal:
    """Converte valor no formato brasileiro (ex.: 1.443,00) para Decimal."""
    s = (valor_str or "").strip()
    if not s:
        return Decimal("0")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except Exception:
        return Decimal("0")


def quinto_dia_util_mes_seguinte(competencia: str) -> Optional[date]:
    """
    Competência MM/AAAA: retorna o 5º dia útil (seg–sex) do mês seguinte.
    """
    if not competencia or "/" not in competencia:
        return None
    try:
        mes, ano = map(int, competencia.strip().split("/"))
    except (ValueError, TypeError):
        return None
    if mes == 12:
        nm, ny = 1, ano + 1
    else:
        nm, ny = mes + 1, ano
    d = date(ny, nm, 1)
    dias_uteis = 0
    while dias_uteis < 5:
        if d.weekday() < 5:
            dias_uteis += 1
            if dias_uteis == 5:
                return d
        d += timedelta(days=1)
    return None


def ler_texto_pdf_relatorio(pdf_file) -> str:
    """Extrai texto bruto do PDF (Relatório de Líquidos etc.)."""
    if pdfplumber is None:
        return ""
    if hasattr(pdf_file, "read"):
        pdf_file.seek(0)
    try:
        with pdfplumber.open(pdf_file) as pdf:
            parts = []
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        if hasattr(pdf_file, "seek"):
            pdf_file.seek(0)
        return "\n".join(parts)
    except Exception:
        if hasattr(pdf_file, "seek"):
            pdf_file.seek(0)
        return ""


# Nomes exatos esperados no cadastro de categorias (empresa)
CATEGORIA_ENCARGOS_PRO_LABORE = "Encargos Funcionários - Pro-labore"
CATEGORIA_ENCARGOS_SALARIO = "Encargos Funcionários - Salario"


from SaudeFinanceira.google_grpc_env import silenciar_logs_grpc_google

silenciar_logs_grpc_google()

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    genai = None
    GEMINI_AVAILABLE = False


class PDFExtractor:
    """Classe para extrair dados de PDFs de comprovantes de arrecadação usando Gemini AI"""

    def __init__(self, pdf_file):
        self.pdf_file = pdf_file
        # Não extrair texto do PDF - usar apenas Gemini AI
        self.text = ""

    def extract_documents(self) -> List[Dict]:
        """
        Extrai múltiplos documentos do PDF usando apenas Gemini AI
        Retorna lista de dicionários com dados de cada documento
        """
        documents = []

        print("DEBUG: Iniciando extração de documentos usando apenas Gemini AI")

        # Usar apenas Gemini AI para extrair dados estruturados
        try:
            print("DEBUG: Tentando usar Gemini AI para extrair dados estruturados")
            gemini_documents = self._extract_with_gemini()
            if gemini_documents:
                print(f"DEBUG: Gemini extraiu {len(gemini_documents)} documentos")
                documents.extend(gemini_documents)
            else:
                print("DEBUG: Gemini não conseguiu extrair documentos válidos")
                raise ValueError("Gemini não conseguiu extrair documentos válidos")
        except Exception as e:
            print(f"DEBUG: Erro ao usar Gemini: {e}")
            print("DEBUG: Detalhes do erro:", str(e))
            raise ValueError(f"Erro ao processar PDF com Gemini: {str(e)}")

        print(f"DEBUG: Total de documentos extraídos: {len(documents)}")
        return documents

    def _extract_with_gemini(self) -> List[Dict]:
        """Extrai dados usando Gemini AI processando o PDF diretamente"""
        print("DEBUG: Verificando disponibilidade do Gemini")
        if genai is None:
            print("DEBUG: Gemini não está disponível - biblioteca não importada")
            raise ImportError("Gemini não está disponível")

        # Configurar Gemini usando a chave da API do settings
        print("DEBUG: Verificando configuração da API key do Gemini")
        from SaudeFinanceira.gemini_config import get_gemini_api_key

        api_key = get_gemini_api_key()
        if api_key:
            print("DEBUG: API key encontrada, configurando Gemini")
            genai.configure(api_key=api_key)
        else:
            print("DEBUG: GEMINI_API_KEY não configurada no settings")
            raise ImportError("GEMINI_API_KEY não configurada no settings")

        print("DEBUG: Criando modelo Gemini")
        model = genai.GenerativeModel('gemini-2.5-flash')

        # Preparar o arquivo PDF para upload
        if hasattr(self.pdf_file, 'read'):
            # É um file-like object (Django UploadedFile)
            pdf_content = self.pdf_file.read()
            self.pdf_file.seek(0)  # Reset para uso futuro
        else:
            # É um path para arquivo
            with open(self.pdf_file, 'rb') as f:
                pdf_content = f.read()

        # Criar arquivo temporário para upload
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(pdf_content)
            temp_file_path = temp_file.name

        try:
            # Upload do PDF para Gemini
            pdf_file = genai.upload_file(temp_file_path)

            prompt = """
            Analise este PDF e extraia os dados estruturados. Pode ser um relatório de salários líquidos ou um resumo de impostos.

            INSTRUÇÕES PARA RELATÓRIO DE SALÁRIOS:
            - Identifique se é um relatório de salários líquidos (contém termos como "RELAÇÃO GERAL DOS LÍQUIDOS", "FOLHA DE PAGAMENTO", "EMPREGADOS", "CONTRIBUINTES", etc.)
            - Para empregados: extraia código, nome, CPF e valor
            - Para contribuintes: extraia código, nome, CPF e valor
            - Extraia também informações da empresa (CNPJ, nome) e competência

            INSTRUÇÕES PARA RESUMO DE IMPOSTOS:
            - Identifique se é um resumo de impostos (contém termos como "RESUMO DOS IMPOSTOS", "IMPOSTOS LANÇADOS", "IMPOSTOS CALCULADOS", etc.)
            - Extraia informações da empresa (CNPJ, nome) e competência
            - Para cada imposto, extraia:
              - Nome do imposto (ex: ISS, PIS, COFINS, CSLL, IRPJ, etc.)
              - Valor a recolher (o valor final do imposto)
              - Competência (MM/YYYY)
            - Procure nas seções "RESUMO DOS IMPOSTOS LANÇADOS" e "RESUMO DOS IMPOSTOS CALCULADOS"
            - Os valores estão no final das linhas, após as bases e alíquotas

            RETORNE APENAS um JSON válido no formato apropriado:

            Para salários:
            {
                "tipo": "relatorio_salarios",
                "empresa": {
                    "cnpj": "XX.XXX.XXX/XXXX-XX",
                    "nome": "Nome da Empresa"
                },
                "competencia": "MM/YYYY",
                "empregados": [...],
                "contribuintes": [...]
            }

            Para resumo de impostos:
            {
                "tipo": "resumo_impostos",
                "empresa": {
                    "cnpj": "XX.XXX.XXX/XXXX-XX",
                    "nome": "Nome da Empresa"
                },
                "impostos": [
                    {
                        "nome_imposto": "ISS",
                        "valor_recolher": 2228.86,
                        "competencia": "06/2025"
                    },
                    {
                        "nome_imposto": "PIS",
                        "valor_recolher": 0.00,
                        "competencia": "06/2025"
                    },
                    {
                        "nome_imposto": "COFINS",
                        "valor_recolher": 0.00,
                        "competencia": "06/2025"
                    },
                    {
                        "nome_imposto": "CSLL",
                        "valor_recolher": 29512.99,
                        "competencia": "06/2025"
                    },
                    {
                        "nome_imposto": "IRPJ",
                        "valor_recolher": 19675.32,
                        "competencia": "06/2025"
                    }
                ]
            }

            Se não for nenhum dos tipos reconhecidos, retorne um JSON vazio: {}
            """

            response = model.generate_content([pdf_file, prompt])
            response_text = response.text.strip()

            # Limpar markdown se presente
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]

            import json
            data = json.loads(response_text)

            if data.get('tipo') == 'relatorio_salarios':
                documents = self._convert_gemini_to_documents(data)
                print(f"DEBUG: Gemini retornou {len(documents)} documentos do tipo relatorio_salarios")
                print(f"DEBUG: Dados brutos do Gemini: {data}")
                for doc in documents:
                    print(f"DEBUG: Documento - Tipo: {doc.get('tipo')}, Empresa CNPJ: {doc.get('empresa_cnpj')}, Valor: {doc.get('valor')}")
                return documents
            elif data.get('tipo') == 'resumo_impostos':
                documents = self._convert_gemini_to_impostos_documents(data)
                print(f"DEBUG: Gemini retornou {len(documents)} documentos do tipo resumo_impostos")
                print(f"DEBUG: Dados brutos do Gemini: {data}")
                for doc in documents:
                    print(f"DEBUG: Documento - Tipo: {doc.get('tipo')}, Empresa CNPJ: {doc.get('empresa_cnpj')}, Valor: {doc.get('valor')}")
                return documents
            else:
                print("DEBUG: Gemini não identificou como relatório de salários ou resumo de impostos")
                return []

        except Exception as e:
            print(f"Erro ao processar resposta do Gemini: {e}")
            return []
        finally:
            # Limpar arquivo temporário
            try:
                os.unlink(temp_file_path)
            except:
                pass

    def _convert_gemini_to_documents(self, gemini_data: Dict) -> List[Dict]:
        """Converte dados do Gemini para formato de documentos"""
        documents = []

        competencia = gemini_data.get('competencia', '')
        empresa_cnpj = limpar_cnpj(gemini_data.get('empresa', {}).get('cnpj', ''))
        empresa_nome = gemini_data.get('empresa', {}).get('nome', '')

        # Processar empregados
        for empregado in gemini_data.get('empregados', []):
            doc = {
                'tipo': 'empregado',
                'codigo': empregado.get('codigo', ''),
                'cpf': empregado.get('cpf', ''),
                'nome': empregado.get('nome', ''),
                'valor': Decimal(str(empregado.get('valor', 0))),
                'competencia': competencia,
                'empresa_cnpj': empresa_cnpj,
                'empresa_nome': empresa_nome
            }
            documents.append(doc)

        # Processar contribuintes
        for contribuinte in gemini_data.get('contribuintes', []):
            doc = {
                'tipo': 'contribuinte',
                'codigo': contribuinte.get('codigo', ''),
                'cnpj': contribuinte.get('cpf', ''),  # Usar CPF como CNPJ
                'nome': contribuinte.get('nome', ''),
                'valor': Decimal(str(contribuinte.get('valor', 0))),
                'competencia': competencia,
                'empresa_cnpj': empresa_cnpj,
                'empresa_nome': empresa_nome
            }
            documents.append(doc)

        return documents

    def _calculate_data_vencimento_imposto(self, tipo_imposto: str, competencia: str) -> Optional[str]:
        """Calcula data de vencimento baseada no tipo de imposto e competência"""
        if not competencia:
            return None

        try:
            # Competência no formato MM/YYYY
            mes, ano = map(int, competencia.split('/'))

            # Regras específicas por tipo de imposto
            tipo_upper = tipo_imposto.upper()

            if 'CSLL' in tipo_upper or 'IRPJ' in tipo_upper:
                # CSLL e IRPJ: último dia do mês seguinte da competência
                if mes == 12:
                    mes = 1
                    ano += 1
                else:
                    mes += 1

                # Último dia do mês
                from calendar import monthrange
                ultimo_dia = monthrange(ano, mes)[1]
                return f"{ultimo_dia:02d}/{mes:02d}/{ano}"

            elif 'ISS' in tipo_upper:
                # ISS: dia 15 do mês seguinte da competência
                if mes == 12:
                    mes = 1
                    ano += 1
                else:
                    mes += 1
                return f"15/{mes:02d}/{ano}"

            elif 'PIS' in tipo_upper or 'COFINS' in tipo_upper:
                # PIS e COFINS: dia 25 do mês seguinte da competência
                if mes == 12:
                    mes = 1
                    ano += 1
                else:
                    mes += 1
                return f"25/{mes:02d}/{ano}"

            elif 'SIMPLES NACIONAL' in tipo_upper or 'SIM' in tipo_upper:
                # Simples Nacional: dia 20 do mês seguinte da competência
                if mes == 12:
                    mes = 1
                    ano += 1
                else:
                    mes += 1
                return f"20/{mes:02d}/{ano}"

            else:
                # Default: último dia do mês seguinte (como CSLL/IRPJ)
                if mes == 12:
                    mes = 1
                    ano += 1
                else:
                    mes += 1

                from calendar import monthrange
                ultimo_dia = monthrange(ano, mes)[1]
                return f"{ultimo_dia:02d}/{mes:02d}/{ano}"

        except Exception as e:
            print(f"Erro ao calcular data de vencimento para {tipo_imposto}: {e}")
            return None

    def _convert_gemini_to_impostos_documents(self, gemini_data: Dict) -> List[Dict]:
        """Converte dados do Gemini para formato de documentos de resumo de impostos"""
        documents = []

        competencia = gemini_data.get('competencia', '')
        empresa_cnpj = limpar_cnpj(gemini_data.get('empresa', {}).get('cnpj', ''))
        empresa_nome = gemini_data.get('empresa', {}).get('nome', '')

        # Processar lista de impostos - um documento por imposto
        for imposto in gemini_data.get('impostos', []):
            valor_recolher = Decimal(str(imposto.get('valor_recolher', 0)))

            # Só criar documento se houver valor a recolher
            if valor_recolher > 0:
                nome_imposto = imposto.get('nome_imposto', '').upper()
                competencia_imposto = imposto.get('competencia', competencia)  # Usar competência específica do imposto ou geral

                # Calcular data de vencimento baseada no nome do imposto
                data_vencimento = self._calculate_data_vencimento_imposto(nome_imposto, competencia_imposto)

                doc = {
                    'tipo': 'imposto_calculado',
                    'tipo_imposto': nome_imposto,
                    'nome_imposto': nome_imposto,
                    'valor_imposto': valor_recolher,
                    'valor': valor_recolher,  # Campo 'valor' para compatibilidade com o código de criação de conta
                    'competencia': competencia_imposto,
                    'data_vencimento': data_vencimento,
                    'empresa_cnpj': empresa_cnpj,
                    'empresa_nome': empresa_nome
                }
                documents.append(doc)

        return documents

    def _extract_traditional(self) -> List[Dict]:
        """Método de extração tradicional como fallback"""
        documents = []

        # Verificar se é um relatório de salários líquidos
        if ("RELAÇÃO GERAL DOS LÍQUIDOS" in self.text or
            "LÍQUIDOS" in self.text or
            "SALARIOS LIQUIDOS" in self.text.upper() or
            "FOLHA DE PAGAMENTO" in self.text.upper() or
            "EMPREGADOS" in self.text.upper() or
            "CONTRIBUINTES" in self.text.upper() or
            "SALARIO" in self.text.upper() or
            "PRO-LABORE" in self.text.upper() or
            "TIPO - RELACAO GERAL DOS LIQUIDOS" in self.text.upper() or
            "RELACAO GERAL DOS LIQUIDOS" in self.text.upper() or
            "LIQUIDOS" in self.text.upper() or
            "SALARIOS" in self.text.upper() or
            "PAGAMENTO" in self.text.upper()):
            print("DEBUG: Detectado relatório de salários líquidos (fallback)")
            return self._extract_salarios_liquidos()

        # Forçar detecção se nenhum padrão funcionou mas temos termos relacionados
        if ("SALARIO" in self.text.upper() or
            "PRO-LABORE" in self.text.upper() or
            "EMPREGADOS" in self.text.upper() or
            "CONTRIBUINTES" in self.text.upper()):
            print("DEBUG: Forçando detecção de relatório de salários líquidos por termos específicos (fallback)")
            return self._extract_salarios_liquidos()

        # Verificar se é um resumo de impostos
        if "RESUMO DOS IMPOSTOS" in self.text.upper() or "IMPOSTOS LANÇADOS" in self.text.upper() or "IMPOSTOS CALCULADOS" in self.text.upper():
            print("DEBUG: Detectado resumo de impostos (fallback)")
            return self._extract_resumo_impostos()

        # Verificar se é um comprovante de arrecadação da Receita Federal
        if "RECEITA FEDERAL" in self.text.upper() or "COMPROVANTE DE ARRECADAÇÃO" in self.text.upper():
            print("DEBUG: Detectado comprovante de arrecadação da Receita Federal (fallback)")
            return self._extract_comprovante_receita()

        # Tentar diferentes padrões para dividir o texto
        patterns = [
            r'Data de Vencimento',
            r'Vencimento',
            r'Documento',
            r'CNPJ',
            r'\d{2}/\d{2}/\d{4}'  # Data no formato DD/MM/YYYY
        ]

        sections = []
        for pattern in patterns:
            sections = re.split(pattern, self.text)
            if len(sections) > 1:
                print(f"DEBUG: Encontradas {len(sections)-1} seções baseadas em '{pattern}'")
                break

        if len(sections) <= 1:
            # Se nenhum padrão funcionou, tentar dividir por linhas que contenham valores monetários
            lines = self.text.split('\n')
            current_section = ""
            for line in lines:
                if re.search(r'\d+,\d{2}', line):  # Padrão de valor monetário brasileiro
                    if current_section:
                        sections.append(current_section)
                    current_section = line
                else:
                    current_section += "\n" + line
            if current_section:
                sections.append(current_section)
            print(f"DEBUG: Encontradas {len(sections)} seções baseadas em valores monetários")

        for i, section in enumerate(sections[1:] if len(sections) > 1 and sections[0].strip() == "" else sections, 1):
            print(f"DEBUG: Processando seção {i}: {section[:200]}...")
            doc_data = self._parse_document_section(section.strip())
            if doc_data:
                documents.append(doc_data)
                print(f"DEBUG: Documento {i} extraído com sucesso")
            else:
                print(f"DEBUG: Seção {i} não produziu documento válido")

        return documents

    def _extract_salarios_liquidos(self) -> List[Dict]:
        """Extrai dados de relatório de salários líquidos"""
        documents = []

        # Extrair informações da empresa
        empresa_info = self._extract_empresa_info()

        # Extrair empregados
        empregados = self._extract_empregados()
        for empregado in empregados:
            doc = {
                'tipo': 'empregado',
                'cpf': empregado['cpf'],
                'nome': empregado['nome'],
                'valor': empregado['valor'],
                'competencia': empresa_info.get('competencia'),
                'empresa_cnpj': empresa_info.get('cnpj'),
                'empresa_nome': empresa_info.get('nome')
            }
            documents.append(doc)

        # Extrair contribuintes
        contribuintes = self._extract_contribuintes()
        for contribuinte in contribuintes:
            doc = {
                'tipo': 'contribuinte',
                'cnpj': contribuinte['cnpj'],
                'nome': contribuinte['nome'],
                'valor': contribuinte['valor'],
                'competencia': empresa_info.get('competencia'),
                'empresa_cnpj': empresa_info.get('cnpj'),
                'empresa_nome': empresa_info.get('nome')
            }
            documents.append(doc)

        print(f"DEBUG: Extraídos {len(empregados)} empregados e {len(contribuintes)} contribuintes")
        return documents

    def _extract_empresa_info(self) -> Dict:
        """Extrai informações da empresa do relatório"""
        info = {}

        # CNPJ da empresa (vários layouts de folha)
        cnpj_match = re.search(r"CNPJ\s*:\s*([\d./-]+)", self.text, re.IGNORECASE)
        if not cnpj_match:
            cnpj_match = re.search(
                r"(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})", self.text
            )
        if cnpj_match:
            info["cnpj"] = cnpj_match.group(1)

        # Nome da empresa
        empresa_match = re.search(r"Empresa:\s*(.+?)(?:\n|$)", self.text, re.IGNORECASE)
        if empresa_match:
            info["nome"] = empresa_match.group(1).strip()

        # Competência (com ou sem acento)
        competencia_match = re.search(
            r"Compet[êe]ncia:\s*(\d{2}/\d{4})", self.text, re.IGNORECASE
        )
        if competencia_match:
            info["competencia"] = competencia_match.group(1)

        return info

    def _extract_empregados(self) -> List[Dict]:
        """Extrai lista de empregados"""
        empregados = []

        # Procurar seção de empregados
        empregados_section = re.search(r'Empregados\s*\n(.*?)(?=Contribuintes|$)', self.text, re.DOTALL)
        if empregados_section:
            section_text = empregados_section.group(1)

            lines = section_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Padrão: CODIGO NOME CPF VALOR (valor pode ser 1.443,00)
                empregado_match = re.match(
                    r"(\d+)\s+(.+?)\s+(\d{3}\.\d{3}\.\d{3}(?:/\d{4})?-\d{2})\s+([\d.,]+)$",
                    line,
                )
                if empregado_match:
                    codigo = empregado_match.group(1)
                    nome = empregado_match.group(2).strip()
                    cpf = empregado_match.group(3)
                    valor_dec = valor_br_para_decimal(empregado_match.group(4))

                    empregados.append({
                        'codigo': codigo,
                        'cpf': cpf,
                        'nome': nome,
                        'valor': valor_dec
                    })
                    print(f"DEBUG: Empregado extraído: {nome} - CPF: {cpf} - Valor: {valor_str}")

        # Se não encontrou empregados na seção específica, tentar procurar por SALARIO
        if not empregados:
            lines = self.text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Procurar linhas que contenham SALARIO e valores
                if 'SALARIO' in line.upper():
                    # Padrão: SALARIO = valor
                    salario_match = re.search(r'SALARIO\s*=\s*([\d.,]+)', line, re.IGNORECASE)
                    if salario_match:
                        valor_str = salario_match.group(1).replace(',', '.')
                        empregados.append({
                            'codigo': '0',
                            'cpf': '000.000.000-00',  # CPF genérico
                            'nome': 'Empregado - Salário',
                            'valor': Decimal(valor_str)
                        })

        print(f"DEBUG: Total empregados extraídos: {len(empregados)}")
        return empregados

    def _extract_contribuintes(self) -> List[Dict]:
        """Extrai lista de contribuintes"""
        contribuintes = []

        # Procurar seção de contribuintes
        contribuintes_section = re.search(r'Contribuintes\s*\n(.*?)(?=Total da Empresa|$)', self.text, re.DOTALL)
        if contribuintes_section:
            section_text = contribuintes_section.group(1)

            lines = section_text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Padrão: CODIGO NOME CPF VALOR (valor pode ser 1.443,00)
                contribuinte_match = re.match(
                    r"(\d+)\s+(.+?)\s+(\d{3}\.\d{3}\.\d{3}(?:/\d{4})?-\d{2})\s+([\d.,]+)$",
                    line,
                )
                if contribuinte_match:
                    codigo = contribuinte_match.group(1)
                    nome = contribuinte_match.group(2).strip()
                    cpf = contribuinte_match.group(3)
                    valor_dec = valor_br_para_decimal(contribuinte_match.group(4))

                    contribuintes.append({
                        'codigo': codigo,
                        'cnpj': cpf,  # Usar CPF como CNPJ para contribuintes
                        'nome': nome,
                        'valor': valor_dec
                    })
                    print(f"DEBUG: Contribuinte extraído: {nome} - CPF: {cpf} - Valor: {valor_dec}")

        # Se não encontrou contribuintes na seção específica, tentar procurar por PRO-LABORE
        if not contribuintes:
            lines = self.text.split('\n')
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                # Procurar linhas que contenham PRO-LABORE e valores
                if 'PRO-LABORE' in line.upper():
                    # Padrão: PRO-LABORE = valor
                    prolabor_match = re.search(r'PRO-LABORE\s*=\s*([\d.,]+)', line, re.IGNORECASE)
                    if prolabor_match:
                        valor_str = prolabor_match.group(1).replace(',', '.')
                        contribuintes.append({
                            'codigo': '0',
                            'cnpj': '00.000.000/0000-00',  # CNPJ genérico
                            'nome': 'Contribuinte - Pró-labore',
                            'valor': Decimal(valor_str)
                        })

        print(f"DEBUG: Total contribuintes extraídos: {len(contribuintes)}")
        return contribuintes

    def _extract_comprovante_receita(self) -> List[Dict]:
        """Extrai dados de comprovante de arrecadação da Receita Federal"""
        documents = []

        # Dividir o texto por comprovantes (cada um começa com "Comprovante de Arrecadação")
        comprovantes = re.split(r'Comprovante de Arrecadação', self.text)[1:]

        for comprovante in comprovantes:
            comprovante = "Comprovante de Arrecadação" + comprovante

            # Extrair CNPJ
            cnpj_match = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', comprovante)
            cnpj = cnpj_match.group(1) if cnpj_match else None

            # Extrair razão social
            razao_match = re.search(r'CLINICA ULTRASSONOGRAFIA E ARTE LTDA', comprovante)
            razao_social = razao_match.group(0) if razao_match else "RECEITA FEDERAL"

            # Extrair período de apuração ou competência
            periodo_match = re.search(r'Período Apuração\s*(\d{2}/\d{4})', comprovante)
            competencia_match = re.search(r'Competência\s*(\d{2}/\d{4})', comprovante)
            periodo_apuracao = periodo_match.group(1) if periodo_match else (competencia_match.group(1) if competencia_match else None)

            # Extrair data de vencimento
            vencimento_match = re.search(r'Data de Vencimento\s*(\d{2}/\d{2}/\d{4})', comprovante)
            data_vencimento = vencimento_match.group(1) if vencimento_match else None

            # Extrair número do documento
            numero_match = re.search(r'Número do Documento\s*(\d+)', comprovante)
            numero_documento = numero_match.group(1) if numero_match else None

            # Extrair composições
            composicoes = self._extract_composicoes_receita(comprovante)

            # Calcular total
            total = sum(comp['total'] for comp in composicoes) if composicoes else Decimal('0')

            if total > 0:
                documents.append({
                    'cnpj': cnpj,
                    'razao_social': razao_social,
                    'periodo_apuracao': periodo_apuracao,
                    'data_vencimento': data_vencimento,
                    'numero_documento': numero_documento,
                    'composicoes': composicoes,
                    'total': total
                })

        return documents

    

    def _parse_currency(self, value_str: str) -> Decimal:
        """Converte string de moeda para Decimal"""
        if not value_str or value_str in ['-', '--']:
            return Decimal('0')

        # Remover pontos e substituir vírgula por ponto
        value_str = value_str.replace('.', '').replace(',', '.')
        try:
            return Decimal(value_str)
        except:
            return Decimal('0')


class ContaPagarCreator:
    """Classe para criar contas a pagar a partir dos dados extraídos"""

    def __init__(self, empresa: Empresa, modo_relatorio_liquidos: bool = False):
        self.empresa = empresa
        self.contas_puladas = 0  # Contador de contas puladas por já existirem
        self.modo_relatorio_liquidos = modo_relatorio_liquidos
        self.erro_importacao: Optional[str] = None

    def create_contas_from_documents(self, documents: List[Dict]) -> List[ContasaPagar]:
        """Cria contas a pagar a partir da lista de documentos"""
        contas_criadas = []
        self.contas_puladas = 0

        for doc_data in documents:
            try:
                conta = self._create_conta_from_document(doc_data)
                if self.modo_relatorio_liquidos and self.erro_importacao:
                    break
                if conta:
                    contas_criadas.append(conta)
                else:
                    self.contas_puladas += 1
            except Exception as e:
                print(f"Erro ao criar conta para documento: {e}")
                continue

        return contas_criadas

    def _create_conta_from_document(self, doc_data: Dict) -> Optional[ContasaPagar]:
        """Cria uma conta a pagar individual"""
        # Verificar se é relatório de salários líquidos
        if doc_data.get('tipo') in ['empregado', 'contribuinte']:
            return self._create_conta_salario_liquido(doc_data)

        # Para impostos, validar se já foi gravado antes de criar
        if doc_data.get('tipo') in ['imposto_calculado', 'imposto_lancado']:
            if self._imposto_ja_gravado(doc_data):
                print(f"DEBUG: Imposto já gravado - pulando criação: {doc_data.get('nome_imposto')} {doc_data.get('competencia')}")
                return None

        # Buscar fornecedor pelo CNPJ
        fornecedor = self._get_or_create_fornecedor(doc_data)
        if not fornecedor:
            return None

        # Buscar categoria específica do imposto ou deixar em branco
        categoria = self._get_categoria_por_imposto(doc_data)

        # Buscar cobrança padrão
        forma_pgto = self._get_forma_pagamento_padrao()
        if not forma_pgto:
            return None

        # Buscar cobrança padrão
        cobranca = self._get_cobranca_padrao()
        if not cobranca:
            return None

        # Buscar conta bancária padrão
        conta_banco = self._get_conta_bancaria_padrao()

        # Valores financeiros
        valor_principal = doc_data.get('valor', Decimal('0'))
        valor_juros = Decimal('0')
        valor_multa = Decimal('0')

        # Data de vencimento
        if doc_data.get('tipo') in ['empregado', 'contribuinte']:
            # Para salários: dia 5 do mês seguinte da competência
            competencia = doc_data.get('competencia')
            dtvenc = self._calculate_data_vencimento_salario(competencia)
        elif doc_data.get('tipo') in ['imposto_calculado', 'imposto_lancado']:
            # Para impostos: usar data de vencimento específica do imposto
            data_vencimento_str = doc_data.get('data_vencimento')
            if data_vencimento_str:
                dtvenc = self._parse_date(data_vencimento_str)
            else:
                # Fallback: último dia do mês seguinte da competência
                competencia = doc_data.get('competencia')
                dtvenc = self._parse_periodo_to_date(competencia)
        else:
            dtvenc = self._parse_date(doc_data.get('data_vencimento'))

        # Data de emissão (usar período de apuração se disponível)
        if doc_data.get('tipo') in ['empregado', 'contribuinte']:
            # Para salários: último dia do mês da competência
            competencia = doc_data.get('competencia')
            dtEmissao = self._parse_periodo_to_date(competencia)
        elif doc_data.get('tipo') in ['imposto_calculado', 'imposto_lancado']:
            # Para impostos: último dia da competência
            competencia = doc_data.get('competencia')
            dtEmissao = self._parse_periodo_to_date(competencia)
        else:
            periodo_apuracao = doc_data.get('periodo_apuracao')
            if periodo_apuracao:
                dtEmissao = self._parse_periodo_to_date(periodo_apuracao)
            else:
                dtEmissao = dtvenc or datetime.now().date()

        # Número do documento (usar competência para salários)
        if doc_data.get('tipo') in ['empregado', 'contribuinte']:
            numdoc = doc_data.get('competencia', '')
        else:
            numdoc = doc_data.get('numero_documento', '')

        # Descrição e observação baseadas no tipo de documento
        descricao, obs = self._create_descricao_e_observacao(doc_data)

        # Criar conta a pagar
        conta = ContasaPagar.objects.create(
            empresa=self.empresa,
            
            fornecedor=fornecedor,
            descricao=descricao,
            numdoc=numdoc,
            valorDoc=valor_principal,
            juros=valor_juros,
            multa=valor_multa,
            categoria=categoria,
            cobranca=forma_pgto or cobranca,
            conta_banco=conta_banco,
            dtvenc=dtvenc,
            dtEmissao=dtEmissao,
            status='pendente',
            obs=obs
        )

        return conta

    def _create_conta_salario_liquido(self, doc_data: Dict) -> Optional[ContasaPagar]:
        """Cria conta a pagar para salários líquidos"""
        if self._salario_ja_gravado(doc_data):
            print(f"DEBUG: Salário já gravado - pulando criação: {doc_data.get('nome')} {doc_data.get('competencia')}")
            self.contas_puladas += 1
            return None

        fornecedor = self._get_or_create_fornecedor_salario(doc_data)
        if not fornecedor:
            if self.modo_relatorio_liquidos and not self.erro_importacao:
                self.erro_importacao = "Não foi possível obter CPF válido para o fornecedor."
            return None

        conta_banco = self._get_conta_bancaria_padrao()
        if not conta_banco:
            self.erro_importacao = "Nenhuma conta bancária ativa para a empresa."
            return None

        competencia = doc_data.get("competencia", "") or "N/A"
        nome = (doc_data.get("nome") or "").strip()
        cpf_limpo = limpar_cnpj(doc_data.get("cpf", doc_data.get("cnpj", "")))
        valor_total = doc_data["valor"]

        if self.modo_relatorio_liquidos:
            cobranca = self._get_cobranca_pix_only()
            if not cobranca:
                self.erro_importacao = (
                    'Cadastre uma forma de cobrança com descrição contendo "PIX".'
                )
                return None
            pro_labore = self._cpf_eh_socio_da_empresa(cpf_limpo, nome)
            categoria = self._get_categoria_encargos(pro_labore)
            if not categoria:
                alvo = (
                    CATEGORIA_ENCARGOS_PRO_LABORE
                    if pro_labore
                    else CATEGORIA_ENCARGOS_SALARIO
                )
                self.erro_importacao = (
                    f'Categoria não encontrada para esta empresa: "{alvo}". '
                    "Cadastre-a em Categorias."
                )
                return None
            descricao = self._montar_descricao_vlr_ref(nome, competencia)
            dt_emissao = self._parse_periodo_to_date(competencia)
            dt_venc = quinto_dia_util_mes_seguinte(competencia)
            if not dt_emissao or not dt_venc:
                self.erro_importacao = f"Competência inválida para datas: {competencia}"
                return None
            numdoc = (competencia.replace("/", "")[:15]) if competencia else "1"
            return ContasaPagar.objects.create(
                empresa=self.empresa,
                fornecedor=fornecedor,
                descricao=descricao,
                valorDoc=valor_total,
                categoria=categoria,
                cobranca=cobranca,
                conta_banco=conta_banco,
                dtvenc=dt_venc,
                dtEmissao=dt_emissao,
                status="pendente",
                obs=f"Import Relatório de Líquidos — competência {competencia}",
                cpf_cnpj=cpf_limpo,
                numdoc=numdoc,
                parcela="1",
                juros=Decimal("0"),
                multa=Decimal("0"),
                desconto=Decimal("0"),
                nossonumero="0",
                nsu="0",
            )

        categoria = self._get_categoria_salario()
        if not categoria:
            return None

        forma_pgto = self._get_forma_pagamento_padrao()
        if not forma_pgto:
            return None

        cobranca = self._get_cobranca_padrao()
        if not cobranca:
            return None

        tipo = doc_data["tipo"]
        cpf = doc_data.get("cpf", doc_data.get("cnpj", ""))
        if tipo == "empregado":
            descricao = f"Pagamento Salário Líquido - {nome} / {cpf} / Competência {competencia}"
        else:
            descricao = f"Pagamento Pró-labore - {nome} / {cpf} / Competência {competencia}"

        dtvenc = self._calculate_data_vencimento_salario(competencia)
        dtEmissao = self._parse_periodo_to_date(competencia)

        return ContasaPagar.objects.create(
            empresa=self.empresa,
            fornecedor=fornecedor,
            descricao=descricao,
            valorDoc=valor_total,
            categoria=categoria,
            cobranca=forma_pgto or cobranca,
            conta_banco=conta_banco,
            dtvenc=dtvenc,
            dtEmissao=dtEmissao,
            status="pendente",
            obs=f"Relatório de Salários Líquidos - Competência: {competencia}",
            cpf_cnpj=cpf_limpo,
        )

    def _get_or_create_fornecedor(self, doc_data: Dict) -> Optional[Fornecedor]:
        """Busca ou cria fornecedor baseado no CNPJ"""
        cnpj = doc_data.get('cnpj')
        razao_social = doc_data.get('razao_social', 'Fornecedor Extraído de PDF')

        # Para PDFs de imposto, sempre usar RECEITA FEDERAL
        if not cnpj or 'RECEITA FEDERAL' in razao_social.upper() or not razao_social or razao_social == 'Fornecedor Extraído de PDF':
            # Usar RECEITA FEDERAL como fornecedor padrão para impostos
            fornecedor, created = Fornecedor.objects.get_or_create(
                cnpj='00394460005887',  # CNPJ específico para RECEITA FEDERAL
                empresa=self.empresa,
                defaults={
                    'razao': 'RECEITA FEDERAL',
                    'telefone': '9',  # Telefone fixo
                }
            )
            return fornecedor

        fornecedor, created = Fornecedor.objects.get_or_create(
            cnpj=cnpj,
            empresa=self.empresa,
            defaults={
                'razao': razao_social,
            }
        )

        return fornecedor

    def _get_or_create_fornecedor_salario(self, doc_data: Dict) -> Optional[Fornecedor]:
        """
        Busca ou cria fornecedor (pessoa) com CPF/CNPJ só números e razão social = nome da folha.
        A chave única é (empresa, cnpj); CPF de 11 dígitos fica no campo cnpj do modelo.
        """
        if self.modo_relatorio_liquidos:
            doc_raw = doc_data.get("cpf") or doc_data.get("cnpj") or ""
        elif doc_data.get("tipo") == "empregado":
            doc_raw = doc_data.get("cpf") or ""
        elif doc_data.get("tipo") == "contribuinte":
            doc_raw = doc_data.get("cnpj") or doc_data.get("cpf") or ""
        else:
            return None

        nome = (doc_data.get("nome") or "").strip()
        doc_digits = limpar_cnpj(doc_raw or "")
        if len(doc_digits) == 14:
            key = doc_digits
        elif len(doc_digits) >= 11:
            key = doc_digits[-11:]
        else:
            return None

        fn, created = Fornecedor.objects.get_or_create(
            empresa=self.empresa,
            cnpj=key,
            defaults={
                "razao": nome or "Colaborador",
                "telefone": "",
            },
        )
        if nome and (created or (fn.razao or "").strip() != nome):
            fn.razao = nome
            fn.save(update_fields=["razao"])
        return fn

    def _get_categoria_imposto(self) -> Optional[Categoria]:
        """Busca categoria para impostos"""
        # Tentar encontrar categoria IMPOSTOS-IMPORTADO
        categoria = Categoria.objects.filter(
            empresa=self.empresa,
            nome='IMPOSTOS-IMPORTADO'
        ).first()

        if not categoria:
            # Criar categoria IMPOSTOS-IMPORTADO se não existir
            categoria, created = Categoria.objects.get_or_create(
                empresa=self.empresa,
                nome='IMPOSTOS-IMPORTADO',
                defaults={
                    'grupo': 'MIGRACAO',
                    'classificacao': '999',
                    'sintetico': 'A',
                    'tipo': 'D'
                }
            )

        return categoria

    def _get_categoria_por_imposto(self, doc_data: Dict) -> Optional[Categoria]:
        """Busca categoria específica do imposto pelo nome, ou deixa em branco se não existir"""
        nome_imposto = doc_data.get('nome_imposto', '').upper()

        if nome_imposto:
            # Buscar categoria com o nome do imposto
            categoria = Categoria.objects.filter(
                empresa=self.empresa,
                nome__iexact=nome_imposto
            ).first()

            return categoria  # Retorna None se não encontrar

        return None

    def _get_categoria_salario(self) -> Optional[Categoria]:
        """Busca categoria para salários"""
        # Tentar encontrar categoria de salários
        categoria = Categoria.objects.filter(
            empresa=self.empresa,
            nome__icontains='salario'
        ).first()

        if not categoria:
            categoria = Categoria.objects.filter(
                empresa=self.empresa,
                nome__icontains='pessoal'
            ).first()

        if not categoria:
            # Criar categoria padrão se não existir
            categoria, created = Categoria.objects.get_or_create(
                empresa=self.empresa,
                nome='Salários e Encargos'
            )

        return categoria

    def _get_forma_pagamento_padrao(self) -> Optional[Cobranca]:
        """Busca cobrança padrão"""
        return Cobranca.objects.filter(descricao__icontains='PIX').first() or Cobranca.objects.first()

    def _get_cobranca_padrao(self) -> Optional[Cobranca]:
        """Busca cobrança padrão"""
        return Cobranca.objects.first()

    def _get_conta_bancaria_padrao(self) -> Optional[ContaBancaria]:
        """Busca conta bancária padrão ativa"""
        return ContaBancaria.objects.filter(empresa=self.empresa, status='A').first()

    def _montar_descricao_vlr_ref(self, nome: str, competencia: str, max_len: int = 100) -> str:
        """VLR REF A {NOME} {MM/AAAA}"""
        nome = (nome or "").strip()
        comp = (competencia or "").strip()
        base = f"VLR REF A {nome} {comp}".strip()
        if len(base) <= max_len:
            return base
        pref = "VLR REF A "
        suf = f" {comp}"
        room = max_len - len(pref) - len(suf)
        nome_c = nome[: max(0, room)] if room > 0 else ""
        return f"{pref}{nome_c}{suf}"[:max_len]

    def _cpf_eh_socio_da_empresa(self, cpf_11: str, nome_linha: str) -> bool:
        """True se o CPF estiver no cadastro de sócios da empresa (nome opcional)."""
        if len(cpf_11) != 11:
            return False
        nome_norm = " ".join((nome_linha or "").upper().split())
        for s in Socio.objects.filter(empresa_id=self.empresa.id):
            scpf = limpar_cnpj(s.cpf or "")
            if len(scpf) == 11 and scpf == cpf_11:
                return True
            if len(scpf) != 11 and nome_norm:
                full = f"{s.socio or ''} {s.lastname or ''}".strip()
                full_norm = " ".join(full.upper().split())
                if full_norm and (full_norm == nome_norm or nome_norm in full_norm):
                    return True
        return False

    def _get_categoria_encargos(self, pro_labore: bool) -> Optional[Categoria]:
        nome = (
            CATEGORIA_ENCARGOS_PRO_LABORE
            if pro_labore
            else CATEGORIA_ENCARGOS_SALARIO
        )
        return Categoria.objects.filter(empresa=self.empresa, nome__iexact=nome).first()

    def _get_cobranca_pix_only(self) -> Optional[Cobranca]:
        """Forma de cobrança PIX (obrigatória no import relatório)."""
        return (
            Cobranca.objects.filter(descricao__icontains="PIX")
            .order_by("id")
            .first()
        )

    def _imposto_ja_gravado(self, doc_data: Dict) -> bool:
        """Verifica se o imposto já foi gravado para evitar duplicatas"""
        nome_imposto = doc_data.get('nome_imposto', '').upper()
        competencia = doc_data.get('competencia', '')
        valor = doc_data.get('valor', Decimal('0'))

        print(f"DEBUG: Verificando se imposto já gravado - Nome: {nome_imposto}, Competência: {competencia}, Valor: {valor}, Empresa: {self.empresa}")

        if not nome_imposto or not competencia:
            print("DEBUG: Nome do imposto ou competência não encontrados, permitindo criação")
            return False

        # Verificar se já existe uma conta a pagar com mesma descrição e valor
        # A descrição geralmente contém o nome do imposto e competência
        descricao_busca = f"{nome_imposto} COMP: {competencia}"

        print(f"DEBUG: Buscando descrição: '{descricao_busca}'")

        contas_existentes = ContasaPagar.objects.filter(
            empresa=self.empresa,
            descricao__icontains=descricao_busca,
            valorDoc=valor,
            status__in=['pendente', 'pago']  # Considerar pendente ou pago
        )

        print(f"DEBUG: Contas encontradas: {contas_existentes.count()}")

        for conta in contas_existentes:
            print(f"DEBUG: Conta existente - ID: {conta.id}, Descrição: '{conta.descricao}', Valor: {conta.valorDoc}")

        existe = contas_existentes.exists()

        print(f"DEBUG: Imposto já gravado? {existe}")

        return existe

    def _salario_ja_gravado(self, doc_data: Dict) -> bool:
        """Verifica se o salário já foi gravado para evitar duplicatas"""
        cpf = doc_data.get('cpf', doc_data.get('cnpj', ''))
        competencia = doc_data.get('competencia', '')
        valor = doc_data.get('valor', Decimal('0'))
        tipo = doc_data.get('tipo', '')

        print(f"DEBUG: Verificando se salário já gravado - CPF: {cpf}, Competência: {competencia}, Valor: {valor}, Tipo: {tipo}, Empresa: {self.empresa}")

        if not cpf or not competencia:
            print("DEBUG: CPF ou competência não encontrados, permitindo criação")
            return False

        # Limpar CPF/CNPJ (remover pontos, barras, hífens)
        cpf_limpo = limpar_cnpj(cpf)

        # Buscar contas existentes com mesmo CPF, competência, valor e empresa
        contas_existentes = ContasaPagar.objects.filter(
            empresa=self.empresa,
            cpf_cnpj=cpf_limpo,
            valorDoc=valor,
            status__in=['pendente', 'pago']  # Considerar pendente ou pago
        )

        # Filtrar por competência na descrição (para salários, a competência está na descrição)
        contas_filtradas = []
        for conta in contas_existentes:
            if competencia in conta.descricao:
                contas_filtradas.append(conta)

        print(f"DEBUG: Contas encontradas com CPF {cpf_limpo} e valor {valor}: {len(contas_filtradas)}")

        for conta in contas_filtradas:
            print(f"DEBUG: Conta existente - ID: {conta.id}, Descrição: '{conta.descricao}', Valor: {conta.valorDoc}, CPF: {conta.cpf_cnpj}")

        existe = len(contas_filtradas) > 0

        print(f"DEBUG: Salário já gravado? {existe}")

        return existe

    def _create_descricao_e_observacao(self, doc_data: Dict) -> tuple[str, str]:
        """Cria descrição e observação baseadas no tipo de documento"""
        tipo = doc_data.get('tipo', '')

        if tipo in ['imposto_calculado', 'imposto_lancado']:
            # Para impostos: observação = "Pagamento de Impostos - Extraído de PDF"
            # descrição = nome do imposto + "comp:" + competência
            nome_imposto = doc_data.get('nome_imposto', 'Imposto')
            competencia = doc_data.get('competencia', '')
            descricao = f"{nome_imposto} COMP: {competencia}" if competencia else nome_imposto
            obs = "Pagamento de Impostos - Extraído de PDF"
            return descricao, obs
        else:
            # Para outros tipos, usar lógica existente
            composicoes = doc_data.get('composicoes', [])
            if not composicoes:
                obs = f"Documento extraído de PDF - Período: {doc_data.get('periodo_apuracao', 'N/A')}"
                descricao = doc_data.get('razao_social', 'Documento Extraído de PDF')
            else:
                # Juntar códigos e descrições para observação
                obs_parts = []
                for comp in composicoes:
                    codigo = comp.get('codigo', '')
                    descricao_comp = comp.get('descricao', '')
                    if codigo and descricao_comp:
                        obs_parts.append(f"{codigo}-{descricao_comp}")
                    elif descricao_comp:
                        obs_parts.append(descricao_comp)

                obs = "; ".join(obs_parts)
                periodo = doc_data.get('periodo_apuracao', '')
                if periodo:
                    obs += f" - Período: {periodo}"

                # Limitar tamanho para caber no campo
                obs = obs[:250]

                # Descrição baseada na razão social
                descricao = doc_data.get('razao_social', 'Documento Extraído de PDF')

            return descricao, obs

    def _create_observacao(self, doc_data: Dict) -> str:
        """Cria observação juntando códigos e descrições"""
        composicoes = doc_data.get('composicoes', [])
        if not composicoes:
            return f"Documento extraído de PDF - Período: {doc_data.get('periodo_apuracao', 'N/A')}"

        # Juntar códigos e descrições
        obs_parts = []
        for comp in composicoes:
            codigo = comp.get('codigo', '')
            descricao = comp.get('descricao', '')
            if codigo and descricao:
                obs_parts.append(f"{codigo}-{descricao}")
            elif descricao:
                obs_parts.append(descricao)

        obs = "; ".join(obs_parts)
        periodo = doc_data.get('periodo_apuracao', '')
        if periodo:
            obs += f" - Período: {periodo}"

        # Limitar tamanho para caber no campo
        return obs[:250]

    def _parse_periodo_to_date(self, periodo_str: str) -> Optional[datetime.date]:
        """Converte período de apuração (MM/YYYY) para data (último dia do mês)"""
        if not periodo_str:
            return None

        try:
            mes, ano = map(int, periodo_str.split('/'))

            # Último dia do mês
            from calendar import monthrange
            ultimo_dia = monthrange(ano, mes)[1]

            return datetime(ano, mes, ultimo_dia).date()
        except:
            return None

    def _parse_date(self, date_str: str) -> Optional[datetime.date]:
        """Converte string de data para date object"""
        if not date_str:
            return None

        try:
            return datetime.strptime(date_str, '%d/%m/%Y').date()
        except:
            return None

    def _calculate_data_vencimento_salario(self, competencia: str) -> Optional[datetime.date]:
        """Calcula data de vencimento para salários (dia 5 do próximo mês)"""
        if not competencia:
            return datetime.now().date()

        try:
            # Competência no formato MM/YYYY
            mes, ano = map(int, competencia.split('/'))

            # Próximo mês
            if mes == 12:
                mes = 1
                ano += 1
            else:
                mes += 1

            # Dia 5 do próximo mês
            return datetime(ano, mes, 5).date()
        except:
            return datetime.now().date()


def processar_pdf_contas_pagar(pdf_file, empresa: Empresa) -> tuple[List[ContasaPagar], str]:
    """
    Função principal para processar PDF e criar contas a pagar

    Args:
        pdf_file: Arquivo PDF (File object ou path)
        empresa: Instância da empresa

    Returns:
        Tupla (lista de contas a pagar criadas, mensagem de erro se houver)
    """
    try:
        # Extrair dados do PDF
        extractor = PDFExtractor(pdf_file)
        documents = extractor.extract_documents()

        if not documents:
            return [], "Nenhum documento válido encontrado no PDF"

        # Validar CNPJ da empresa do arquivo com CNPJ da empresa logada
        empresa_cnpj_arquivo = None
        for doc in documents:
            if doc.get('empresa_cnpj'):
                empresa_cnpj_arquivo = doc.get('empresa_cnpj')
                break

        print(f"DEBUG: CNPJ da empresa logada (original): {empresa.cnpj}")
        print(f"DEBUG: CNPJ do arquivo (original): {empresa_cnpj_arquivo}")

        if empresa_cnpj_arquivo:
            # Limpar CNPJ do arquivo (remover pontos, barras, hífens)
            cnpj_arquivo_limpo = re.sub(r'[^\d]', '', empresa_cnpj_arquivo)
            cnpj_empresa_limpo = re.sub(r'[^\d]', '', empresa.cnpj or '')

            print(f"DEBUG: CNPJ da empresa logada (limpo): {cnpj_empresa_limpo}")
            print(f"DEBUG: CNPJ do arquivo (limpo): {cnpj_arquivo_limpo}")
            print(f"DEBUG: Comparação - Arquivo: {cnpj_arquivo_limpo} vs Empresa: {cnpj_empresa_limpo}")
            print(f"DEBUG: São iguais? {cnpj_arquivo_limpo == cnpj_empresa_limpo}")

            if cnpj_arquivo_limpo != cnpj_empresa_limpo:
                return [], "Não é possível importar documento que não pertence à empresa."
        else:
            print("DEBUG: AVISO - Nenhum CNPJ de empresa encontrado no arquivo PDF")
            return [], "Não foi possível identificar o CNPJ da empresa no arquivo PDF. Importação não permitida."

        # Criar contas a pagar
        creator = ContaPagarCreator(empresa)
        contas_criadas = creator.create_contas_from_documents(documents)

        # Verificar se todas as contas foram puladas
        if len(contas_criadas) == 0 and creator.contas_puladas > 0:
            return contas_criadas, f"Lançamentos já existentes. {creator.contas_puladas} conta(s) não foram criadas porque já existem no sistema."

        return contas_criadas, ""

    except Exception as e:
        return [], f"Erro ao processar PDF: {str(e)}"


def processar_relatorio_liquidos_pdf(pdf_file, empresa: Empresa) -> tuple:
    """
    Importa PDF de Relatório / Relação Geral dos Líquidos (folha).

    1) Tenta extrair texto com **pdfplumber** (camada de texto do PDF — não é OCR).
    2) Se não houver linhas ou texto insuficiente, e existir **GEMINI_API_KEY** no
       settings, usa **Google Gemini** com o arquivo PDF (visão do documento).
    """
    try:
        if pdfplumber is None:
            return [], "Biblioteca pdfplumber não disponível no servidor."

        text = ler_texto_pdf_relatorio(pdf_file)
        documents = []
        fonte = ""

        if text and len(text.strip()) >= 20:
            extractor = PDFExtractor(pdf_file)
            extractor.text = text
            documents = extractor._extract_salarios_liquidos()
            if documents:
                fonte = "texto do PDF (pdfplumber)"
                logger.info(
                    "Relatório líquidos: %s linhas via regex/pdfplumber",
                    len(documents),
                )

        if not documents and GEMINI_AVAILABLE:
            from SaudeFinanceira.gemini_config import get_gemini_api_key

            if get_gemini_api_key():
                try:
                    pdf_file.seek(0)
                    extractor = PDFExtractor(pdf_file)
                    gem_all = extractor._extract_with_gemini()
                    documents = [
                        d
                        for d in (gem_all or [])
                        if d.get("tipo") in ("empregado", "contribuinte")
                    ]
                    if documents:
                        fonte = "Gemini API (GEMINI_API_KEY)"
                        logger.info(
                            "Relatório líquidos: %s linhas via Gemini", len(documents)
                        )
                except Exception as ex:
                    logger.warning("Relatório líquidos: fallback Gemini falhou: %s", ex)

        if not documents:
            from SaudeFinanceira.gemini_config import get_gemini_api_key

            msg = (
                "Não foi possível ler linhas de Empregados/Contribuintes. "
                "Se o PDF for escaneado (só imagem), o pdfplumber não enxerga texto — "
                "configure GEMINI_API_KEY em settings.py para leitura via API Gemini."
            )
            if not get_gemini_api_key():
                msg += (
                    " Ou exporte o relatório com texto selecionável (não é OCR nativo no sistema)."
                )
            return [], msg

        empresa_cnpj_arquivo = None
        for doc in documents:
            if doc.get("empresa_cnpj"):
                empresa_cnpj_arquivo = doc.get("empresa_cnpj")
                break
        if not empresa_cnpj_arquivo:
            return [], "Não foi possível identificar o CNPJ da empresa no relatório."

        cnpj_arquivo_limpo = re.sub(r"[^\d]", "", str(empresa_cnpj_arquivo))
        cnpj_empresa_limpo = re.sub(r"[^\d]", "", empresa.cnpj or "")
        if cnpj_arquivo_limpo != cnpj_empresa_limpo:
            return [], "O CNPJ do PDF não confere com a empresa selecionada na sessão."

        creator = ContaPagarCreator(empresa, modo_relatorio_liquidos=True)
        contas_criadas = creator.create_contas_from_documents(documents)

        if creator.erro_importacao:
            return [], creator.erro_importacao

        if len(contas_criadas) == 0 and creator.contas_puladas > 0:
            return contas_criadas, (
                f"Nenhuma conta nova. {creator.contas_puladas} lançamento(s) já existentes ou ignorados."
            )
        if len(contas_criadas) == 0:
            return [], "Nenhuma conta a pagar foi gerada."

        if fonte:
            logger.info("Relatório líquidos gravado: %s contas (%s)", len(contas_criadas), fonte)
        return contas_criadas, ""
    except Exception as e:
        return [], f"Erro ao processar relatório de líquidos: {str(e)}"


def formatar_cpf_cnpj_sicoob(cpf_cnpj):
    """Formata CPF/CNPJ conforme padrão Sicoob no histórico (ex.: ***.317.642-**)."""
    if cpf_cnpj is None:
        return None
    cpf_cnpj_limpo = "".join(filter(str.isdigit, str(cpf_cnpj)))
    if len(cpf_cnpj_limpo) == 11:
        if len(cpf_cnpj_limpo) >= 9:
            return f"***.{cpf_cnpj_limpo[-8:-5]}.{cpf_cnpj_limpo[-5:-2]}-**"
    elif len(cpf_cnpj_limpo) == 14:
        if len(cpf_cnpj_limpo) >= 14:
            return (
                f"{cpf_cnpj_limpo[-14:-12]}.{cpf_cnpj_limpo[-12:-9]}."
                f"{cpf_cnpj_limpo[-9:-6]} {cpf_cnpj_limpo[-6:-2]}-{cpf_cnpj_limpo[-2:]}"
            )
    return None


def buscar_lancamentos_por_cpf_cnpj(conta_banco, cpf_cnpj_formatado, data_inicio, data_fim, empresa_id):
    """
    Busca lançamentos no extrato por CPF/CNPJ formatado no período especificado

    Args:
        conta_banco: ContaBancaria do Sicoob
        cpf_cnpj_formatado: CPF/CNPJ formatado conforme padrão Sicoob
        data_inicio: Data de início da busca
        data_fim: Data de fim da busca
        empresa_id: ID da empresa

    Returns:
        QuerySet de lançamentos que correspondem aos critérios
    """
    from extrato.models import Lancamento

    # Buscar lançamentos não conciliados com valor negativo (débitos)
    # no período especificado e que contenham o CPF/CNPJ formatado no histórico
    lancamentos = Lancamento.objects.filter(
        empresa_id=empresa_id,
        conta=conta_banco,
        conciliado=False,
        valor__lt=0,  # Apenas débitos
        data__gte=data_inicio,
        data__lte=data_fim,
        historico__icontains=cpf_cnpj_formatado  # Verificar se contém o CPF formatado no histórico
    ).order_by('data')

    return lancamentos


def conciliar_conta_automaticamente_sicoob(conta, empresa_id, user):
    """
    Tenta conciliar uma conta automaticamente com o extrato bancário do Sicoob

    Args:
        conta: Instância de ContasaPagar
        empresa_id: ID da empresa
        user: Usuário que está executando a ação

    Returns:
        bool: True se conseguiu conciliar, False caso contrário
    """
    from extrato.models import Lancamento, ExtratoMovimento, Conciliacao
    from datetime import timedelta

    # Verificar se o banco é Sicoob
    if not conta.conta_banco or conta.conta_banco.banco.nome.lower() != 'sicoob':
        return False

    from fornecedor.cnpj_utils import limpar_cnpj as _limpar_doc

    doc_digits = "".join(filter(str.isdigit, (conta.cpf_cnpj or "")))
    if len(doc_digits) < 4 and conta.fornecedor_id:
        doc_digits = _limpar_doc(conta.fornecedor.cnpj or "")
    if len(doc_digits) < 4:
        return False

    # Formatar CPF/CNPJ conforme padrão Sicoob
    cpf_formatado = formatar_cpf_cnpj_sicoob(doc_digits)
    if not cpf_formatado:
        return False

    if not conta.dtvenc:
        return False

    # Definir período de busca: 15 dias antes e 30 dias depois da data de vencimento
    data_inicio = conta.dtvenc - timedelta(days=15)
    data_fim = conta.dtvenc + timedelta(days=30)

    # Buscar lançamentos compatíveis
    lancamentos = buscar_lancamentos_por_cpf_cnpj(
        conta.conta_banco, cpf_formatado, data_inicio, data_fim, empresa_id
    )

    # Procurar lançamento com valor compatível
    valor_conta = conta.get_valor_total_com_ajustes()
    for lancamento in lancamentos:
        valor_lancamento_abs = abs(lancamento.valor)
        # Comparar valores com tolerância de 0.01
        if abs(valor_lancamento_abs - valor_conta) <= 0.01:
            # Encontrou correspondência - conciliar
            conciliacao = Conciliacao.objects.create(
                criado_por=user if user.is_authenticated else None
            )

            # Marcar lançamento como conciliado
            lancamento.conciliado = True
            lancamento.idconciliacao = conciliacao
            lancamento.save()

            # Criar movimento no extrato
            movimento = ExtratoMovimento.objects.create(
                empresa_id=empresa_id,
                data_baixa=lancamento.data,
                descricao=f'Pagamento - {conta.descricao}',
                valor=valor_conta,
                situacao='pago',
                conta_banco=conta.conta_banco,
                conta_pagar=conta,
                lancamento=lancamento
            )

            # Atualizar conta a pagar
            conta.dtPag = lancamento.data
            conta.valorPago = valor_conta
            conta.status = 'pago'
            conta.save()

            return True

    return False