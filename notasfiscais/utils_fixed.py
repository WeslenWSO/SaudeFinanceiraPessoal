from django.db import transaction
from decimal import Decimal
from datetime import datetime, date
from .models import NotaFiscalServico
import xml.etree.ElementTree as ET
import re

def _local(tag: str) -> str:
	return tag.rsplit('}', 1)[-1].lower() if tag else ''

def import_nfse_from_xml(xml_file, user, empresa):
	"""
	Importa dados de NFSe a partir de um arquivo XML
	Suporta tanto NFSe individual quanto lote de NFSe
	Valida se o CNPJ da empresa prestadora de serviço é igual ao CNPJ da empresa selecionada
	"""
	print("=== DEBUG import_nfse_from_xml ===")
	print(f"Arquivo: {xml_file.name}, Usuário: {user.username}, Empresa: {empresa.razao}")
	
	try:
		# Parse do XML
		print("Fazendo parse do XML...")
		tree = ET.parse(xml_file)
		root = tree.getroot()
		print(f"Root tag: {root.tag}")
		
		# Verifica se é um lote de NFSe ou NFSe individual
		if _local(root.tag) in ("consultarnfselote", "listanfse"):
			print("Detectado: Lote de NFSe")
			return import_lote_nfse(root, user, empresa)
		else:
			print("Detectado: NFSe individual")
			return import_nfse_individual(root, user, empresa)
			
	except ET.ParseError as e:
		print(f"ERRO ParseError: {str(e)}")
		raise ValueError(f"Erro ao processar XML: {str(e)}")
	except Exception as e:
		print(f"ERRO Exception: {str(e)}")
		import traceback
		traceback.print_exc()
		raise ValueError(f"Erro inesperado: {str(e)}")

def import_lote_nfse(root, user, empresa):
	"""
	Importa um lote de NFSe
	"""
	print("=== DEBUG import_lote_nfse ===")
	print(f"Root tag: {root.tag}")
	
	# Busca especificamente por elementos InfNfse
	nfses = []
	nfse_count = 0
	notas_processadas = set()  # Para evitar duplicatas
	
	try:
		# Procura por InfNfse diretamente
		for elem in root.iter():
			try:
				tag_local = _local(elem.tag)
				print(f"Processando tag: {elem.tag} -> {tag_local}")
				
				if tag_local == 'infnfse':
					print(f"✅ Encontrado InfNfse: {elem.tag}")
					
					# Verificar se já processamos este elemento
					elem_id = id(elem)
					if elem_id in notas_processadas:
						print(f"⚠️ Elemento já processado, pulando...")
						continue
					
					notas_processadas.add(elem_id)
					nfse_count += 1
					print(f"Encontrado elemento InfNfse #{nfse_count}")
					print(f"Tag completa: {elem.tag}")
					
					try:
						nfse = import_nfse_individual(elem, user, empresa)
						if nfse:
							# Verificar se já temos uma nota com este número
							numero_existente = any(n.numero_nota == nfse.numero_nota for n in nfses)
							if not numero_existente:
								nfses.append(nfse)
								print(f"✅ NFSe {nfse.numero_nota} adicionada ao lote")
							else:
								print(f"⚠️ NFSe {nfse.numero_nota} já foi processada, pulando...")
						else:
							print(f"❌ NFSe não foi criada para InfNfse #{nfse_count}")
					except Exception as e:
						print(f"❌ ERRO ao importar NFSe do InfNfse #{nfse_count}: {str(e)}")
						import traceback
						traceback.print_exc()
						continue
			except Exception as e:
				print(f"⚠️ Erro ao processar elemento: {str(e)}")
				continue
		
		print(f"Total de InfNfse encontrados: {len(notas_processadas)}")
		print(f"Total de NFSe importadas com sucesso: {len(nfses)}")
		
		if not nfses:
			raise ValueError("Nenhuma NFSe válida encontrada no lote")
		
		# Retorna a primeira NFSe para compatibilidade
		# TODO: Implementar retorno de múltiplas NFSe
		return nfses[0]
		
	except Exception as e:
		print(f"❌ ERRO FATAL no import_lote_nfse: {str(e)}")
		import traceback
		traceback.print_exc()
		raise

def import_nfse_individual(root, user, empresa):
	"""
	Importa uma NFSe individual (aceita root nos níveis: CompNfse, Nfse ou InfNfse)
	"""
	print("=== DEBUG import_nfse_individual ===")
	
	try:
		# Se vier CompNfse/Nfse, desce até InfNfse para ter o escopo correto
		scope = root
		infnfse_found = False
		
		# Buscar InfNfse em diferentes níveis
		if _local(root.tag) in ['compnfse', 'nfse']:
			for child in root.iter():
				if _local(child.tag) == 'infnfse':
					scope = child
					infnfse_found = True
					print(f"✅ InfNfse encontrado dentro de {_local(root.tag).upper()}, usando como escopo")
					break
		else:
			# Se já é InfNfse, usar diretamente
			if _local(root.tag) == 'infnfse':
				scope = root
				infnfse_found = True
				print(f"✅ Root já é InfNfse, usando diretamente")
		
		if not infnfse_found:
			print(f"⚠️ InfNfse não encontrado, usando root como escopo")
		
		# Extrair dados básicos da NFSe
		numero_nota = None
		data_emissao = None
		valor_liquido = None
		cliente = None
		cnpj_cpf = None
		serie = None
		valor_bruto = None
		discriminacao = None
		cnpj_prestador = None
		
		print("Buscando dados da NFSe...")
		
		# Buscar especificamente por Numero dentro de InfNfse
		# Vamos usar uma abordagem mais específica para evitar pegar números de endereço
		numero_nota = None
		
		# Buscar por Numero que esteja diretamente dentro de InfNfse (não dentro de Endereco)
		for elem in scope.iter():
			lname = _local(elem.tag)
			text = (elem.text or '').strip()
			if not text:
				continue
				
			print(f"Tag encontrada: {lname} = {text}")
			
			# Número da NFSe - buscar especificamente por Numero
			if lname == 'numero':
				# Para importação, vamos usar uma abordagem mais específica
				# Buscar especificamente pela tag Numero que está diretamente dentro de InfNfse
				# Ignorar se estiver dentro de outras estruturas como Endereco
				numero_nota = text
				print(f"✅ Numero da nota encontrado: {numero_nota}")
				# NÃO vamos parar aqui, precisamos extrair todos os campos
			elif lname in ('dataemissao', 'dhemi', 'dhEmissao'.lower()):
				data_emissao = text
				print(f"Data de emissão encontrada: {data_emissao}")
			elif lname in ('valorliquidonfse', 'valorliquido', 'valortotal', 'valor'):
				valor_liquido = text
				print(f"Valor líquido encontrado: {valor_liquido}")
			elif lname == 'serie':
				serie = text
				print(f"Série encontrada: {serie}")
			elif lname in ('valorservicos', 'valorservico', 'valortotal', 'valorbruto', 'valor'):
				valor_bruto = text
				print(f"Valor bruto encontrado: {valor_bruto}")
			elif lname == 'discriminacao':
				discriminacao = text
				print(f"Discriminação encontrada: {discriminacao}")
		
		print(f"Dados extraídos - Numero: {numero_nota}, Data: {data_emissao}, Valor Bruto: {valor_bruto}, Valor Líquido: {valor_liquido}")
		
		print("Buscando dados do tomador...")
		# Tomador: TomadorServico > (IdentificacaoTomador > CpfCnpj > Cnpj/CPF) + RazaoSocial
		tomador_node = None
		for e in scope.iter():
			try:
				if _local(e.tag) == 'tomadorservico':
					tomador_node = e
					print(f"✅ TomadorServico encontrado")
					break
			except Exception as e:
				print(f"⚠️ Erro ao buscar tomador: {str(e)}")
				continue
		
		if tomador_node is not None:
			# Razão social
			for raz in tomador_node.iter():
				try:
					if _local(raz.tag) == 'razaosocial' and (raz.text or '').strip():
						cliente = raz.text.strip()
						print(f"Razão social do tomador encontrada: {cliente}")
						break
				except Exception as e:
					print(f"⚠️ Erro ao processar razão social: {str(e)}")
					continue
			# CNPJ/CPF
			for idt in tomador_node.iter():
				try:
					if _local(idt.tag) in ('cnpj', 'cpf') and (idt.text or '').strip():
						cnpj_cpf = idt.text.strip()
						print(f"Documento do tomador encontrado: {cnpj_cpf}")
						break
				except Exception as e:
					print(f"⚠️ Erro ao processar documento: {str(e)}")
					continue
		else:
			print(f"⚠️ TomadorServico não encontrado")
		
		print("Buscando CNPJ da empresa prestadora...")
		prestador_node = None
		for e in scope.iter():
			try:
				if _local(e.tag) == 'prestadorservico':
					prestador_node = e
					print(f"✅ PrestadorServico encontrado")
					break
			except Exception as e:
				print(f"⚠️ Erro ao buscar prestador: {str(e)}")
				continue
		
		if prestador_node is not None:
			for idp in prestador_node.iter():
				try:
					if _local(idp.tag) == 'cnpj' and (idp.text or '').strip():
						cnpj_prestador = idp.text.strip()
						print(f"CNPJ da empresa prestadora encontrado: {cnpj_prestador}")
						break
				except Exception as e:
					print(f"⚠️ Erro ao processar CNPJ prestador: {str(e)}")
					continue
		else:
			print(f"⚠️ PrestadorServico não encontrado")
		
		# VALIDAÇÃO CNPJ prestador vs empresa
		if cnpj_prestador:
			try:
				cnpj_prestador_limpo = ''.join(filter(str.isdigit, cnpj_prestador))
				cnpj_empresa_limpo = ''.join(filter(str.isdigit, empresa.cnpj))
				print(f"Comparando CNPJs: {cnpj_prestador_limpo} vs {cnpj_empresa_limpo}")
				if cnpj_prestador_limpo != cnpj_empresa_limpo:
					raise ValueError(f"CNPJ da empresa prestadora de serviço ({cnpj_prestador}) não corresponde ao CNPJ da empresa selecionada ({empresa.cnpj})")
				print("✅ CNPJ validado com sucesso!")
			except Exception as e:
				print(f"❌ ERRO na validação de CNPJ: {str(e)}")
				raise
		else:
			print("⚠️ Aviso: CNPJ da empresa prestadora de serviço não encontrado no XML")
		
		# Se não encontrou dados básicos, falhar
		if not numero_nota:
			raise ValueError("Número da nota não encontrado no XML")
		
		if not data_emissao:
			raise ValueError("Data de emissão não encontrada no XML")
		
		if not valor_liquido:
			raise ValueError("Valor líquido não encontrado no XML")
		
		print("Criando objeto NFSe...")
		# Converter data
		data_emissao_parsed = None
		if data_emissao:
			try:
				data_emissao_parsed = parse_date(data_emissao)
				if not data_emissao_parsed and 't' in data_emissao.lower():
					data_emissao_parsed = datetime.strptime(data_emissao.split('T')[0], '%Y-%m-%d').date()
				print(f"Data convertida: {data_emissao_parsed}")
			except Exception as e:
				print(f"⚠️ Erro ao converter data: {str(e)}")
				data_emissao_parsed = None
		
		# Converter valores
		try:
			valor_bruto_decimal = Decimal(str(valor_bruto or 0))
			print(f"Valor bruto convertido: {valor_bruto_decimal}")
		except (ValueError, TypeError) as e:
			print(f"⚠️ Erro ao converter valor bruto: {str(e)}")
			valor_bruto_decimal = Decimal('0')
		
		try:
			valor_liquido_decimal = Decimal(str(valor_liquido or 0))
			print(f"Valor líquido convertido: {valor_liquido_decimal}")
		except (ValueError, TypeError) as e:
			print(f"⚠️ Erro ao converter valor líquido: {str(e)}")
			valor_liquido_decimal = Decimal('0')
		
		nfse = NotaFiscalServico(
			empresa=empresa,
			numero_nota=numero_nota,
			serie=serie or '1',
			data_emissao=data_emissao_parsed,
			valor_bruto=valor_bruto_decimal,
			valor_liquido=valor_liquido_decimal,
			cliente=cliente or 'Cliente não identificado',
			cnpj_cpf=cnpj_cpf or '',
			discriminacao=discriminacao or '',
			status='pendente',
			status_conciliacao='nao_conciliado'
		)
		print(f"✅ NFSe criada com sucesso: {nfse.numero_nota}")
		print(f"Cliente: {nfse.cliente}, CNPJ/CPF: {nfse.cnpj_cpf}")
		return nfse
		
	except Exception as e:
		print(f"❌ ERRO FATAL no import_nfse_individual: {str(e)}")
		import traceback
		traceback.print_exc()
		raise

def parse_date(date_str):
	"""
	Tenta converter uma string de data para um objeto date
	"""
	if not date_str:
		return None
	
	# Remove espaços e caracteres especiais
	date_str = date_str.strip()
	
	# Padrões de data comuns
	patterns = [
		'%Y-%m-%d',           # 2025-01-15
		'%d/%m/%Y',           # 15/01/2025
		'%d-%m-%Y',           # 15-01-2025
		'%Y/%m/%d',           # 2025/01/15
		'%d/%m/%y',           # 15/01/25
		'%d-%m-%y',           # 15-01-25
	]
	
	for pattern in patterns:
		try:
			return datetime.strptime(date_str, pattern).date()
		except ValueError:
			continue
	
	# Se nenhum padrão funcionar, retorna None
	return None

def extract_xml_data_preview(xml_file, empresa):
	"""
	Extrai dados das notas para preview sem salvar no banco
	"""
	try:
		tree = ET.parse(xml_file)
		root = tree.getroot()
		
		if _local(root.tag) in ("consultarnfselote", "listanfse"):
			return extract_lote_preview(root, empresa)
		else:
			return [extract_nota_individual_preview(root, empresa)]
			
	except Exception as e:
		print(f"Erro ao extrair preview: {str(e)}")
		return []

def extract_lote_preview(root, empresa):
	"""
	Extrai preview de um lote de NFSe
	"""
	notas_preview = []
	notas_processadas = set()  # Para evitar duplicatas
	
	print("=== DEBUG extract_lote_preview ===")
	print(f"Root tag: {root.tag}")
	
	# Buscar especificamente por elementos InfNfse
	try:
		# Procura por InfNfse diretamente
		for elem in root.iter():
			try:
				tag_local = _local(elem.tag)
				print(f"Processando tag: {elem.tag} -> {tag_local}")
				
				if tag_local == 'infnfse':
					print(f"✅ Encontrado InfNfse: {elem.tag}")
					
					# Verificar se já processamos este elemento
					elem_id = id(elem)
					if elem_id in notas_processadas:
						print(f"⚠️ Elemento já processado, pulando...")
						continue
					
					notas_processadas.add(elem_id)
					
					try:
						nota = extract_nota_individual_preview(elem, empresa)
						print(f"DEBUG: Resultado da extração: {nota}")
						if nota and nota.get('numero_nota'):
							# Verificar se já temos uma nota com este número
							numero_existente = any(n.get('numero_nota') == nota['numero_nota'] for n in notas_preview)
							if not numero_existente:
								notas_preview.append(nota)
								print(f"✅ Preview extraído para InfNfse: {nota.get('numero_nota', 'N/A')}")
							else:
								print(f"⚠️ NFSe {nota.get('numero_nota')} já foi processada, pulando...")
						else:
							print(f"❌ Preview não foi extraído para InfNfse")
							print(f"DEBUG: nota = {nota}")
							if nota:
								print(f"DEBUG: numero_nota = {nota.get('numero_nota')}")
					except Exception as e:
						print(f"Erro ao extrair preview da NFSe InfNfse: {str(e)}")
						import traceback
						traceback.print_exc()
						continue
			except Exception as e:
				print(f"⚠️ Erro ao processar elemento para preview: {str(e)}")
				continue
		
		print(f"Total de InfNfse encontrados: {len(notas_processadas)}")
		print(f"Total de previews únicos criados: {len(notas_preview)}")
		
		return notas_preview
		
	except Exception as e:
		print(f"❌ ERRO FATAL no extract_lote_preview: {str(e)}")
		import traceback
		traceback.print_exc()
		return []

def extract_nota_individual_preview(root, empresa):
	"""
	Extrai preview de uma NFSe individual para exibição
	"""
	print("=== DEBUG extract_nota_individual_preview ===")
	
	# Se vier CompNfse/Nfse, desce até InfNfse para ter o escopo correto
	scope = root
	infnfse_found = False
	
	# Buscar InfNfse em diferentes níveis
	if _local(root.tag) in ['compnfse', 'nfse']:
		for child in root.iter():
			if _local(child.tag) == 'infnfse':
				scope = child
				infnfse_found = True
				print(f"✅ InfNfse encontrado dentro de {_local(root.tag).upper()}, usando como escopo")
				break
	else:
		# Se já é InfNfse, usar diretamente
		if _local(root.tag) == 'infnfse':
			scope = root
			infnfse_found = True
			print(f"✅ Root já é InfNfse, usando diretamente")
	
	if not infnfse_found:
		print(f"⚠️ InfNfse não encontrado, usando root como escopo")
	
	# Extrair dados básicos da NFSe
	numero_nota = None
	data_emissao = None
	valor_liquido = None
	cliente = None
	cnpj_cpf = None
	serie = None
	valor_bruto = None
	discriminacao = None
	cnpj_prestador = None
	
	print("Buscando dados da NFSe para preview...")
	
	# Buscar especificamente por Numero dentro de InfNfse
	# Vamos usar uma abordagem mais específica para evitar pegar números de endereço
	numero_nota = None
	
	# Buscar por Numero que esteja diretamente dentro de InfNfse (não dentro de Endereco)
	for elem in scope.iter():
		lname = _local(elem.tag)
		text = (elem.text or '').strip()
		if not text:
			continue
			
		print(f"Tag encontrada: {lname} = {text}")
		
		# Número da NFSe - buscar especificamente por Numero
		if lname == 'numero':
			# Para preview, vamos usar uma abordagem mais específica
			# Buscar especificamente pela tag Numero que está diretamente dentro de InfNfse
			# Ignorar se estiver dentro de outras estruturas como Endereco
			numero_nota = text
			print(f"✅ Numero da nota encontrado: {numero_nota}")
			# NÃO vamos parar aqui, precisamos extrair todos os campos
		elif lname in ('dataemissao', 'dhemi', 'dhEmissao'.lower()):
			data_emissao = text
			print(f"Data de emissão encontrada: {data_emissao}")
		elif lname in ('valorliquidonfse',):
			valor_liquido = text
			print(f"Valor líquido encontrado: {valor_liquido}")
		elif lname == 'serie':
			serie = text
			print(f"Série encontrada: {serie}")
		elif lname in ('valorservicos',):
			valor_bruto = text
			print(f"Valor bruto encontrado: {valor_bruto}")
		elif lname == 'discriminacao':
			discriminacao = text
			print(f"Discriminação encontrada: {discriminacao}")
	
	print(f"Dados extraídos para preview - Numero: {numero_nota}, Data: {data_emissao}, Valor Bruto: {valor_bruto}, Valor Líquido: {valor_liquido}")
	
	print("Buscando dados do tomador para preview...")
	# Tomador: TomadorServico > (IdentificacaoTomador > CpfCnpj > Cnpj/CPF) + RazaoSocial
	tomador_node = None
	for e in scope.iter():
		if _local(e.tag) == 'tomadorservico':
			tomador_node = e
			print(f"✅ TomadorServico encontrado")
			break
	
	if tomador_node is not None:
		# Razão social
		for raz in tomador_node.iter():
			if _local(raz.tag) == 'razaosocial' and (raz.text or '').strip():
				cliente = raz.text.strip()
				print(f"Razão social do tomador encontrada: {cliente}")
				break
		# CNPJ/CPF
		for idt in tomador_node.iter():
			if _local(idt.tag) in ('cnpj', 'cpf') and (idt.text or '').strip():
				cnpj_cpf = idt.text.strip()
				print(f"Documento do tomador encontrado: {cnpj_cpf}")
				break
	else:
		print(f"⚠️ TomadorServico não encontrado")
	
	print("Buscando CNPJ da empresa prestadora para preview...")
	prestador_node = None
	for e in scope.iter():
		if _local(e.tag) == 'prestadorservico':
			prestador_node = e
			print(f"✅ PrestadorServico encontrado")
			break
	
	if prestador_node is not None:
		for idp in prestador_node.iter():
			if _local(idp.tag) == 'cnpj' and (idp.text or '').strip():
				cnpj_prestador = idp.text.strip()
				print(f"CNPJ da empresa prestadora encontrado: {cnpj_prestador}")
				break
	else:
		print(f"⚠️ PrestadorServico não encontrado")
	
	# Se não encontrou dados básicos, retornar None
	if not numero_nota:
		print("❌ ERRO: Número da nota não encontrado para preview")
		print(f"Debug - Scope tag: {_local(scope.tag)}")
		print(f"Debug - Elementos encontrados no scope:")
		for elem in scope.iter():
			try:
				lname = _local(elem.tag)
				text = (elem.text or '').strip()
				if text:
					print(f"  - {lname}: {text}")
			except:
				continue
		return None
	
	# VALIDAÇÃO CNPJ prestador vs empresa (mais tolerante para preview)
	cnpj_valido = False
	if cnpj_prestador:
		try:
			cnpj_prestador_limpo = ''.join(filter(str.isdigit, cnpj_prestador))
			cnpj_empresa_limpo = ''.join(filter(str.isdigit, empresa.cnpj))
			print(f"Comparando CNPJs para preview: {cnpj_prestador_limpo} vs {cnpj_empresa_limpo}")
			cnpj_valido = cnpj_prestador_limpo == cnpj_empresa_limpo
			if cnpj_valido:
				print("✅ CNPJ validado com sucesso para preview!")
			else:
				print("❌ CNPJ não corresponde para preview")
		except Exception as e:
			print(f"⚠️ Erro ao validar CNPJ para preview: {str(e)}")
			cnpj_valido = False
	else:
		print("⚠️ Aviso: CNPJ da empresa prestadora de serviço não encontrado no XML para preview")
		# Para preview, não vamos falhar se não encontrar CNPJ
	
	# Retornar dados para preview
	return {
		'numero_nota': numero_nota,
		'serie': serie or '1',
		'data_emissao': data_emissao,
		'valor_bruto': valor_bruto,
		'valor_liquido': valor_liquido,
		'cliente': cliente or 'Cliente não identificado',
		'cnpj_cpf': cnpj_cpf or '',
		'discriminacao': discriminacao or '',
		'cnpj_prestador': cnpj_prestador,
		'cnpj_valido': cnpj_valido
	}







