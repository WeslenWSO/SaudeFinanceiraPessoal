from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db import transaction
from django.http import JsonResponse
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.utils import timezone
from django.db.models import Q
from .models import NotaFiscalEntrada, NotaFiscalEntradaItem
from empresa.models import Empresa
from fornecedor.models import Fornecedor
from regraConciliacao.models import RegraConciliacao
from categoria.models import Categoria
from contasapagar.models import ContasaPagar
from cobranca.models import Cobranca
from cobranca.models import Cobranca
from extrato.models import ContaBancaria
import xml.etree.ElementTree as ET
import re
import hashlib
from decimal import Decimal
from datetime import datetime, time, timedelta

from django.utils.dateparse import parse_datetime, parse_date
from dateutil import parser as date_parser

from notasfiscais.utils import NS_SPED, _t, _d, _dec, _qname, limpar_cnpj

NFE_NS_URI = 'http://www.portalfiscal.inf.br/nfe'


def _is_nfse_sped_portal(root):
    """True se o XML contém infNFSe do layout SPED (Portal Nacional)."""
    tag_inf = _qname(NS_SPED, "infNFSe")
    if root.find(".//%s" % tag_inf) is not None:
        return True
    if root.find(tag_inf) is not None:
        return True
    return False


def _chave_acesso_nfse_sped_entrada(empresa_id, numero, serie, doc_forn):
    """Chave única 44 caracteres para NFSe SPED (sem chave numérica de 44 dígitos)."""
    base = "%s|%s|%s|%s|NFSPED" % (empresa_id, numero, serie, doc_forn or "0")
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:44]


def _parse_dt_nfse_sped_entrada(infnfse_elem):
    for path in ("dhProc", "dhEmi", "DPS/infDPS/dhEmi"):
        text = _t(infnfse_elem, path, NS_SPED)
        if text:
            try:
                norm = text.replace("Z", "+00:00") if text.endswith("Z") else text
                dt = date_parser.parse(norm)
                if timezone.is_naive(dt):
                    return timezone.make_aware(dt)
                return dt
            except (ValueError, TypeError, OverflowError):
                pass
    d = _d(infnfse_elem, "dhProc", NS_SPED) or _d(infnfse_elem, "dhEmi", NS_SPED)
    if d:
        return timezone.make_aware(datetime.combine(d, time.min))
    return timezone.now()


def _extrair_prestador_sped_entrada(infnfse_elem):
    """Prestador = fornecedor na nota de entrada (comprador = tomador).

    Layout SPED costuma usar DPS/infDPS/prest; no Portal Nacional também há
    identificação do emitente em emit (CNPJ, xNome), análogo à NF-e.
    """
    cnpj = _t(infnfse_elem, "DPS/infDPS/prest/CNPJ", NS_SPED) or _t(
        infnfse_elem, "DPS/infDPS/prest/CPF", NS_SPED
    )
    nome = (
        _t(infnfse_elem, "DPS/infDPS/prest/xNome", NS_SPED)
        or _t(infnfse_elem, "DPS/infDPS/prest/xRazSoc", NS_SPED)
        or _t(infnfse_elem, "DPS/infDPS/prest/xFant", NS_SPED)
        or ""
    )
    if not cnpj:
        cnpj = _t(infnfse_elem, "emit/CNPJ", NS_SPED) or _t(
            infnfse_elem, "emit/CPF", NS_SPED
        )
    if not nome:
        nome = (
            _t(infnfse_elem, "emit/xNome", NS_SPED)
            or _t(infnfse_elem, "emit/xRazSoc", NS_SPED)
            or _t(infnfse_elem, "emit/xFant", NS_SPED)
            or ""
        )
    return ((cnpj or "").strip(), (nome or "").strip())


def processar_xml_nfse_sped_entrada(xml_content, empresa_id):
    """
    Importa NFSe no formato Portal Nacional (SPED): namespace infNFSe, DPS/infDPS, etc.
    """
    try:
        root = ET.fromstring(xml_content)
        empresa = Empresa.objects.get(id=empresa_id)
        tag_inf = _qname(NS_SPED, "infNFSe")
        inf_list = root.findall(".//%s" % tag_inf)
        if not inf_list:
            inf_one = root.find(tag_inf)
            if inf_one is not None:
                inf_list = [inf_one]
        if not inf_list:
            raise ValueError("Nenhuma infNFSe (Portal Nacional) encontrada no XML.")

        notas_processadas = []
        for infnfse in inf_list:
            numero_nota = _t(infnfse, "nNFSe", NS_SPED)
            if not numero_nota:
                continue
            serie = _t(infnfse, "DPS/infDPS/serie", NS_SPED) or "1"

            prest_raw, prest_nome = _extrair_prestador_sped_entrada(infnfse)
            prest_doc = limpar_cnpj(prest_raw) if prest_raw else ""

            tomador_nome = _t(infnfse, "DPS/infDPS/toma/xNome", NS_SPED) or ""
            tomador_raw = _t(infnfse, "DPS/infDPS/toma/CNPJ", NS_SPED) or _t(
                infnfse, "DPS/infDPS/toma/CPF", NS_SPED
            )
            tomador_doc = limpar_cnpj(tomador_raw) if tomador_raw else ""

            if not prest_doc and not prest_nome:
                raise ValueError(
                    "NFSe Portal Nacional: dados do prestador (fornecedor) não encontrados "
                    "(esperado DPS/infDPS/prest ou emit com CNPJ/CPF e xNome)."
                )

            chave_acesso = _chave_acesso_nfse_sped_entrada(
                empresa_id, numero_nota, serie, prest_doc or tomador_doc
            )

            if NotaFiscalEntrada.objects.filter(
                empresa=empresa, chave_acesso=chave_acesso
            ).exists():
                continue
            if NotaFiscalEntrada.objects.filter(
                empresa=empresa, numero_nota=numero_nota, serie=serie
            ).exists():
                continue

            valor_bruto = _dec(infnfse, "valores/vBC", NS_SPED)
            if not valor_bruto or valor_bruto <= 0:
                valor_bruto = _dec(infnfse, "valores/vServPrest/vServ", NS_SPED)
            valor_liq = _dec(infnfse, "valores/vLiq", NS_SPED)
            valor_liquido = valor_liq if valor_liq > 0 else valor_bruto
            if not valor_bruto or valor_bruto <= 0:
                valor_bruto = valor_liquido

            v_pis = _dec(
                infnfse, "DPS/infDPS/valores/trib/tribFed/piscofins/vPis", NS_SPED
            )
            v_cofins = _dec(
                infnfse, "DPS/infDPS/valores/trib/tribFed/piscofins/vCofins", NS_SPED
            )
            tp_ret_pis_cofins = _t(
                infnfse,
                "DPS/infDPS/valores/trib/tribFed/piscofins/tpRetPisCofins",
                NS_SPED,
            ) or _t(
                infnfse,
                "DPS/infDPS/valores/trib/tribFed/tpRetPisCofins",
                NS_SPED,
            )
            if tp_ret_pis_cofins in ("0", "2"):
                v_pis = Decimal("0")
                v_cofins = Decimal("0")

            v_iss = _dec(infnfse, "valores/vISSQN", NS_SPED)
            discriminacao = _t(infnfse, "serv/cServ/xDescServ", NS_SPED) or "SERVIÇO PRESTADO"
            data_emissao = _parse_dt_nfse_sped_entrada(infnfse)

            fornecedor = None
            if prest_doc:
                fornecedor, created = Fornecedor.objects.get_or_create(
                    empresa=empresa,
                    cnpj=prest_doc,
                    defaults={
                        "razao": (prest_nome or "Prestador")[:200],
                        "telefone": "",
                    },
                )
                if created:
                    print(
                        "Fornecedor (prestador SPED) criado: %s - doc: %s"
                        % (fornecedor.razao, fornecedor.cnpj)
                    )

            with transaction.atomic():
                nota_fiscal = NotaFiscalEntrada.objects.create(
                    empresa=empresa,
                    tipo_nota="tomador",
                    chave_acesso=chave_acesso,
                    numero_nota=numero_nota.strip(),
                    serie=serie.strip(),
                    modelo="NFS",
                    fornecedor_cnpj=prest_doc or "",
                    fornecedor_nome=(prest_nome or "Prestador")[:200],
                    fornecedor=fornecedor,
                    destinatario_cnpj=tomador_doc or "",
                    destinatario_nome=(tomador_nome or "")[:200],
                    data_emissao=data_emissao,
                    data_saida_entrada=None,
                    valor_produtos=valor_bruto,
                    valor_frete=Decimal("0"),
                    valor_seguro=Decimal("0"),
                    valor_desconto=Decimal("0"),
                    valor_ii=Decimal("0"),
                    valor_ipi=Decimal("0"),
                    valor_pis=v_pis,
                    valor_cofins=v_cofins,
                    valor_icms=v_iss,
                    valor_total=valor_liquido,
                    xml_content=xml_content,
                    status="importada",
                )
                NotaFiscalEntradaItem.objects.create(
                    nota_fiscal=nota_fiscal,
                    numero_item=1,
                    codigo_produto="SERVICO",
                    nome_produto=discriminacao[:200],
                    cfop="0000",
                    unidade="UN",
                    quantidade=Decimal("1"),
                    valor_unitario=valor_bruto,
                    valor_total=valor_bruto,
                    valor_pis=v_pis,
                    valor_cofins=v_cofins,
                    valor_icms=v_iss,
                    valor_ipi=Decimal("0"),
                    valor_ii=Decimal("0"),
                )
            notas_processadas.append(nota_fiscal)

        print("DEBUG: NFSe SPED — notas processadas: %s" % len(notas_processadas))
        return notas_processadas[0] if notas_processadas else None

    except Exception as e:
        print("Erro ao processar XML NFSe SPED (Portal Nacional): %s" % str(e))
        import traceback

        traceback.print_exc()
        return None


def _decode_xml_bytes(raw):
    """UTF-8, UTF-8 com BOM ou Latin-1 (XMLs de alguns emissores)."""
    if isinstance(raw, str):
        return raw
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            return raw.decode('latin-1')


def _extrair_chave_acesso_nfe(inf_nfe, xml_content, xml_filename=None):
    """
    Chave 44 dígitos: atributo Id, texto do XML ou nome do arquivo (ex.: 1126...9996.xml).
    """
    id_attr = (inf_nfe.get('Id') or '').strip()
    chave = ''
    if id_attr.upper().startswith('NFE'):
        chave = id_attr[3:].strip()
    elif id_attr:
        chave = re.sub(r'^NFe', '', id_attr, flags=re.I).strip()
    if len(chave) == 44 and chave.isdigit():
        return chave
    m = re.search(r'chNFe=(\d{44})', xml_content)
    if m:
        return m.group(1)
    m = re.search(r'\b(\d{44})\b', xml_content)
    if m and m.group(1).isdigit():
        return m.group(1)
    if xml_filename:
        digits = re.sub(r'\D', '', xml_filename)
        if len(digits) >= 44:
            return digits[:44]
    raise ValueError('Chave de acesso da NF-e não encontrada (esperados 44 dígitos). Verifique o XML ou renomeie o arquivo com a chave.')


def _parse_data_emissao_nfe(ide, ns):
    """dhEmi (preferencial), dhCont ou dEmi — retorna datetime consciente de fuso."""
    if ide is None:
        return timezone.now()
    for tag in ('nfe:dhEmi', 'nfe:dhCont'):
        el = ide.find(tag, ns)
        if el is not None:
            s = _nfe_elem_text(el, '')
            if s:
                dt = parse_datetime(s.replace(' ', 'T') if 'T' not in s and len(s) > 10 else s)
                if dt is not None:
                    if timezone.is_naive(dt):
                        return timezone.make_aware(dt)
                    return dt
    el = ide.find('nfe:dEmi', ns)
    if el is not None:
        s = _nfe_elem_text(el, '')
        if s:
            pd = parse_date(s[:10])
            if pd is not None:
                return timezone.make_aware(datetime.combine(pd, time.min))
    return timezone.now()


def _parse_data_opcional_nfe(ide, tag, ns):
    el = ide.find(tag, ns) if ide is not None else None
    if el is None:
        return None
    s = _nfe_elem_text(el, '')
    if not s:
        return None
    dt = parse_datetime(s.replace(' ', 'T') if 'T' not in s and len(s) > 10 else s)
    if dt is not None:
        if timezone.is_naive(dt):
            return timezone.make_aware(dt)
        return dt
    pd = parse_date(s[:10])
    if pd is not None:
        return timezone.make_aware(datetime.combine(pd, time.min))
    return None


def _totais_nfe_como_dict(inf_nfe, ns):
    """
    Totais em ICMSTot (mercadoria) ou ISSQNtot (notas de tomador / serviço com ISS).
    """
    out = {
        'valor_produtos': Decimal('0'),
        'valor_frete': Decimal('0'),
        'valor_seguro': Decimal('0'),
        'valor_desconto': Decimal('0'),
        'valor_ii': Decimal('0'),
        'valor_ipi': Decimal('0'),
        'valor_pis': Decimal('0'),
        'valor_cofins': Decimal('0'),
        'valor_icms': Decimal('0'),
        'valor_total': Decimal('0'),
    }
    icms = inf_nfe.find('nfe:total/nfe:ICMSTot', ns)
    if icms is not None:

        def g(tag):
            el = icms.find(tag, ns)
            return Decimal(_nfe_elem_text(el, '0') or '0')

        out['valor_produtos'] = g('nfe:vProd')
        out['valor_frete'] = g('nfe:vFrete')
        out['valor_seguro'] = g('nfe:vSeg')
        out['valor_desconto'] = g('nfe:vDesc')
        out['valor_ii'] = g('nfe:vII')
        out['valor_ipi'] = g('nfe:vIPI')
        out['valor_pis'] = g('nfe:vPIS')
        out['valor_cofins'] = g('nfe:vCOFINS')
        out['valor_icms'] = g('nfe:vICMS')
        out['valor_total'] = g('nfe:vNF')
        return out

    iss = inf_nfe.find('nfe:total/nfe:ISSQNtot', ns)
    if iss is not None:
        vserv = Decimal(_nfe_elem_text(iss.find('nfe:vServ', ns), '0') or '0')
        out['valor_produtos'] = vserv
        out['valor_pis'] = Decimal(_nfe_elem_text(iss.find('nfe:vPIS', ns), '0') or '0')
        out['valor_cofins'] = Decimal(_nfe_elem_text(iss.find('nfe:vCOFINS', ns), '0') or '0')
        out['valor_icms'] = Decimal(_nfe_elem_text(iss.find('nfe:vISS', ns), '0') or '0')
        vdesc = (
            iss.find('nfe:vDescIncondicionado', ns)
            or iss.find('nfe:vDescIncond', ns)
            or iss.find('nfe:vDesc', ns)
        )
        if vdesc is not None:
            out['valor_desconto'] = Decimal(_nfe_elem_text(vdesc, '0') or '0')
        vnf = iss.find('nfe:vNF', ns)
        if vnf is not None:
            out['valor_total'] = Decimal(_nfe_elem_text(vnf, '0') or '0')
        else:
            out['valor_total'] = vserv
        return out

    vnf = inf_nfe.find('.//nfe:vNF', ns)
    if vnf is not None:
        v = Decimal(_nfe_elem_text(vnf, '0') or '0')
        out['valor_produtos'] = v
        out['valor_total'] = v
    return out


def _nfe_elem_text(el, default=''):
    """Texto seguro de um elemento XML (evita AttributeError se el for None)."""
    if el is None:
        return default
    t = el.text
    return (t.strip() if t else default) or default


def _listar_dets_inf_nfe(inf_nfe, ns):
    """
    Retorna todos os <det> da NF-e. Usa busca recursiva (.//) porque em alguns XMLs
    a árvore difere; findall('det') só pega filhos diretos.
    """
    dets = inf_nfe.findall('.//nfe:det', ns)
    if dets:
        return dets
    dets = inf_nfe.findall('nfe:det', ns)
    if dets:
        return dets
    # Fallback: tag com namespace explícito
    tag_det = f'{{{NFE_NS_URI}}}det'
    return [e for e in inf_nfe.iter() if e.tag == tag_det]


def _prod_text(prod, tag, ns, default=''):
    if prod is None:
        return default
    return _nfe_elem_text(prod.find(f'nfe:{tag}', ns), default)


@login_required
def importar_xml(request):
    """View para importar XML de notas fiscais de entrada"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('dashboard:relatorio_mensal')

    if request.method == 'POST':
        xml_files = request.FILES.getlist('xml_files')

        if not xml_files:
            messages.error(request, 'Selecione pelo menos um arquivo XML.')
            return redirect('notafiscalentrada:importar')

        importados = 0
        erros = []

        for xml_file in xml_files:
            try:
                print(f"DEBUG: Processando arquivo {xml_file.name}")

                raw = xml_file.read()
                xml_content = _decode_xml_bytes(raw)
                print(f"DEBUG: Arquivo lido, tamanho: {len(xml_content)} caracteres")

                nota_fiscal = processar_xml_nfe(xml_content, empresa_id, xml_filename=xml_file.name)

                if nota_fiscal:
                    importados += 1
                    messages.success(request, f'Nota {nota_fiscal.numero_nota} importada com sucesso!')
                    print(f"DEBUG: Nota {nota_fiscal.numero_nota} importada com sucesso")
                else:
                    erros.append(f'Erro ao processar {xml_file.name}')
                    print(f"DEBUG: Erro ao processar {xml_file.name} - nota_fiscal é None")

            except Exception as e:
                erros.append(f'Erro no arquivo {xml_file.name}: {str(e)}')
                print(f"DEBUG: Exceção no arquivo {xml_file.name}: {str(e)}")
                import traceback
                traceback.print_exc()

        if erros:
            for erro in erros:
                messages.warning(request, erro)

        if importados > 0:
            messages.success(request, f'{importados} nota(s) fiscal(is) importada(s) com sucesso!')

        return redirect('notafiscalentrada:listar')

    return render(request, 'notafiscalentrada/importar.html')

def processar_xml_nfe(xml_content, empresa_id, xml_filename=None):
    """Processa o XML da NFe/NFS-e e cria os registros no banco"""

    try:
        print("DEBUG: Iniciando processamento do XML")
        # Parse do XML
        root = ET.fromstring(xml_content)
        print(f"DEBUG: Root tag: {root.tag}")

        # NFSe Portal Nacional (layout SPED: infNFSe, namespace sped.fazenda.gov.br)
        if _is_nfse_sped_portal(root):
            print("DEBUG: Detectado NFSe Portal Nacional (SPED)")
            return processar_xml_nfse_sped_entrada(xml_content, empresa_id)

        # Detectar tipo de XML
        if root.tag == 'ConsultarNfseLote' or root.find('.//Nfse') is not None:
            print("DEBUG: Detectado como NFS-e")
            # É NFS-e (Nota Fiscal de Serviços)
            return processar_xml_nfse(xml_content, empresa_id)
        elif (
            root.tag == 'nfeProc'
            or root.find('.//infNFe') is not None
            or root.find(f'.//{{{NFE_NS_URI}}}infNFe') is not None
        ):
            print("DEBUG: Detectado como NFe")
            return processar_xml_nfe_produto(xml_content, empresa_id, xml_filename=xml_filename)
        else:
            print(f"DEBUG: Tipo de XML não identificado. Root tag: {root.tag}")
            # Tentar detectar por conteúdo
            if 'Nfse' in xml_content:
                print("DEBUG: Detectado NFS-e por conteúdo")
                return processar_xml_nfse(xml_content, empresa_id)
            elif 'infNFe' in xml_content:
                print("DEBUG: Detectado NFe por conteúdo")
                return processar_xml_nfe_produto(xml_content, empresa_id, xml_filename=xml_filename)
            elif (
                'sped.fazenda.gov.br/nfse' in xml_content
                or 'infNFSe' in xml_content
            ):
                print("DEBUG: Tentativa NFSe Portal Nacional (SPED) por conteúdo")
                return processar_xml_nfse_sped_entrada(xml_content, empresa_id)
            else:
                raise ValueError(f"Tipo de XML não suportado. Root tag: {root.tag}")

    except ValueError:
        raise
    except Exception as e:
        print(f"Erro ao processar XML: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def processar_xml_nfe_produto(xml_content, empresa_id, xml_filename=None):
    """Processa o XML da NFe (produtos ou nota de tomador / ISSQN)."""

    try:
        root = ET.fromstring(xml_content)

        ns = {'nfe': NFE_NS_URI}

        empresa = Empresa.objects.get(id=empresa_id)

        inf_nfe = root.find('.//nfe:infNFe', ns)
        if inf_nfe is None:
            inf_nfe = root.find(f'.//{{{NFE_NS_URI}}}infNFe')
        if not inf_nfe:
            raise ValueError('Estrutura XML inválida - infNFe não encontrado')

        chave_acesso = _extrair_chave_acesso_nfe(inf_nfe, xml_content, xml_filename)

        if NotaFiscalEntrada.objects.filter(empresa=empresa, chave_acesso=chave_acesso).exists():
            raise ValueError(f'Nota fiscal com chave {chave_acesso} já foi importada')

        ide = inf_nfe.find('nfe:ide', ns)
        emit = inf_nfe.find('nfe:emit', ns)
        dest = inf_nfe.find('nfe:dest', ns)

        totais = _totais_nfe_como_dict(inf_nfe, ns)

        det_elements = _listar_dets_inf_nfe(inf_nfe, ns)
        tipo_nota = 'tomador' if not det_elements else 'comercio'

        el_cnpj = emit.find('nfe:CNPJ', ns) if emit is not None else None
        el_cpf = emit.find('nfe:CPF', ns) if emit is not None else None
        fornecedor_cnpj = _nfe_elem_text(el_cnpj) or _nfe_elem_text(el_cpf)
        fornecedor_nome = _nfe_elem_text(emit.find('nfe:xNome', ns), 'FORNECEDOR') if emit is not None else 'FORNECEDOR'
        fornecedor_fone = ''
        if emit is not None:
            fone_el = emit.find('nfe:enderEmit/nfe:fone', ns)
            fornecedor_fone = _nfe_elem_text(fone_el)

        fornecedor = None
        if fornecedor_cnpj:
            fornecedor, created = Fornecedor.objects.get_or_create(
                empresa=empresa,
                cnpj=fornecedor_cnpj,
                defaults={
                    'razao': fornecedor_nome,
                    'telefone': fornecedor_fone,
                }
            )
            if created:
                print(f"Fornecedor criado: {fornecedor.razao} - CNPJ: {fornecedor.cnpj}")

        dest_doc = ''
        dest_nome = ''
        if dest is not None:
            dest_doc = _nfe_elem_text(dest.find('nfe:CNPJ', ns)) or _nfe_elem_text(dest.find('nfe:CPF', ns))
            dest_nome = _nfe_elem_text(dest.find('nfe:xNome', ns), 'DESTINATÁRIO')

        data_emissao_dt = _parse_data_emissao_nfe(ide, ns)
        data_saida_dt = _parse_data_opcional_nfe(ide, 'nfe:dhSaiEnt', ns)

        with transaction.atomic():
            nota_fiscal = NotaFiscalEntrada.objects.create(
                empresa=empresa,
                tipo_nota=tipo_nota,
                chave_acesso=chave_acesso,
                numero_nota=_nfe_elem_text(ide.find('nfe:nNF', ns), '0') if ide is not None else '0',
                serie=_nfe_elem_text(ide.find('nfe:serie', ns), '1') if ide is not None else '1',
                modelo=_nfe_elem_text(ide.find('nfe:mod', ns), '55') if ide is not None else '55',
                fornecedor_cnpj=fornecedor_cnpj,
                fornecedor_nome=fornecedor_nome,
                fornecedor=fornecedor,
                destinatario_cnpj=dest_doc,
                destinatario_nome=dest_nome,
                data_emissao=data_emissao_dt,
                data_saida_entrada=data_saida_dt,
                valor_produtos=totais['valor_produtos'],
                valor_frete=totais['valor_frete'],
                valor_seguro=totais['valor_seguro'],
                valor_desconto=totais['valor_desconto'],
                valor_ii=totais['valor_ii'],
                valor_ipi=totais['valor_ipi'],
                valor_pis=totais['valor_pis'],
                valor_cofins=totais['valor_cofins'],
                valor_icms=totais['valor_icms'],
                valor_total=totais['valor_total'],
                xml_content=xml_content,
                status='importada'
            )

            if det_elements:
                for idx, det in enumerate(det_elements, start=1):
                    prod = det.find('nfe:prod', ns)
                    imposto = det.find('nfe:imposto', ns)

                    valor_pis_item = Decimal('0')
                    valor_cofins_item = Decimal('0')
                    valor_icms_item = Decimal('0')
                    valor_ipi_item = Decimal('0')
                    valor_ii_item = Decimal('0')

                    if imposto is not None:
                        pis = imposto.find('nfe:PIS', ns)
                        if pis is not None:
                            pis_aliquota = pis.find('.//nfe:vPIS', ns)
                            if pis_aliquota is not None:
                                valor_pis_item = Decimal(_nfe_elem_text(pis_aliquota, '0') or '0')
                        cofins = imposto.find('nfe:COFINS', ns)
                        if cofins is not None:
                            cofins_aliquota = cofins.find('.//nfe:vCOFINS', ns)
                            if cofins_aliquota is not None:
                                valor_cofins_item = Decimal(_nfe_elem_text(cofins_aliquota, '0') or '0')
                        icms = imposto.find('nfe:ICMS', ns)
                        if icms is not None:
                            icms_valor = icms.find('.//nfe:vICMS', ns)
                            if icms_valor is not None:
                                valor_icms_item = Decimal(_nfe_elem_text(icms_valor, '0') or '0')
                        ipi = imposto.find('nfe:IPI', ns)
                        if ipi is not None:
                            ipi_valor = ipi.find('.//nfe:vIPI', ns)
                            if ipi_valor is not None:
                                valor_ipi_item = Decimal(_nfe_elem_text(ipi_valor, '0') or '0')
                        ii = imposto.find('nfe:II', ns)
                        if ii is not None:
                            ii_valor = ii.find('.//nfe:vII', ns)
                            if ii_valor is not None:
                                valor_ii_item = Decimal(_nfe_elem_text(ii_valor, '0') or '0')

                    n_item_raw = det.get('nItem')
                    try:
                        numero_item = int(n_item_raw) if n_item_raw is not None else idx
                    except (TypeError, ValueError):
                        numero_item = idx

                    if prod is None:
                        NotaFiscalEntradaItem.objects.create(
                            nota_fiscal=nota_fiscal,
                            numero_item=numero_item,
                            codigo_produto='SEM_PROD',
                            ean='',
                            nome_produto=f'Item {numero_item} (XML sem nó prod)',
                            ncm='',
                            cest='',
                            cfop='0000',
                            unidade='UN',
                            quantidade=Decimal('1'),
                            valor_unitario=Decimal('0'),
                            valor_total=Decimal('0'),
                            valor_pis=valor_pis_item,
                            valor_cofins=valor_cofins_item,
                            valor_icms=valor_icms_item,
                            valor_ipi=valor_ipi_item,
                            valor_ii=valor_ii_item,
                        )
                        continue

                    nome_p = _prod_text(prod, 'xProd', ns, 'PRODUTO SEM DESCRIÇÃO')
                    cfop_p = _prod_text(prod, 'CFOP', ns, '0000')
                    un_p = _prod_text(prod, 'uCom', ns, 'UN')

                    NotaFiscalEntradaItem.objects.create(
                        nota_fiscal=nota_fiscal,
                        numero_item=numero_item,
                        codigo_produto=_prod_text(prod, 'cProd', ns, ''),
                        ean=_prod_text(prod, 'cEAN', ns, '') or _prod_text(prod, 'cEANTrib', ns, ''),
                        nome_produto=nome_p[:200],
                        ncm=_prod_text(prod, 'NCM', ns, ''),
                        cest=_prod_text(prod, 'CEST', ns, ''),
                        cfop=cfop_p[:5],
                        unidade=un_p[:10],
                        quantidade=Decimal(_prod_text(prod, 'qCom', ns, '0') or '0'),
                        valor_unitario=Decimal(_prod_text(prod, 'vUnCom', ns, '0') or '0'),
                        valor_total=Decimal(_prod_text(prod, 'vProd', ns, '0') or '0'),
                        valor_pis=valor_pis_item,
                        valor_cofins=valor_cofins_item,
                        valor_icms=valor_icms_item,
                        valor_ipi=valor_ipi_item,
                        valor_ii=valor_ii_item,
                    )
            else:
                inf_intermed = inf_nfe.find('nfe:infIntermed', ns)
                servico_descricao = 'SERVIÇO PRESTADO'
                if inf_intermed is not None:
                    servico_descricao = _nfe_elem_text(inf_intermed.find('nfe:xIntermed', ns), servico_descricao)

                NotaFiscalEntradaItem.objects.create(
                    nota_fiscal=nota_fiscal,
                    numero_item=1,
                    codigo_produto='SERVICO',
                    nome_produto=servico_descricao[:200],
                    cfop='0000',
                    unidade='UN',
                    quantidade=Decimal('1'),
                    valor_unitario=nota_fiscal.valor_produtos,
                    valor_total=nota_fiscal.valor_produtos,
                    valor_pis=nota_fiscal.valor_pis,
                    valor_cofins=nota_fiscal.valor_cofins,
                    valor_icms=nota_fiscal.valor_icms,
                    valor_ipi=nota_fiscal.valor_ipi,
                    valor_ii=nota_fiscal.valor_ii,
                )

        return nota_fiscal

    except Exception as e:
        print(f"Erro ao processar XML: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

def _xml_tag_local(tag):
    if not tag:
        return ''
    return tag.split('}', 1)[-1]


def _nfse_first_direct_child_by_local(parent, local_name):
    """Primeiro filho direto cujo nome local coincide (ignora namespace XML)."""
    if parent is None:
        return None
    ln = local_name.lower()
    for c in parent:
        if _xml_tag_local(c.tag).lower() == ln:
            return c
    return None


def _nfse_first_by_local(parent, local_name):
    """Primeiro descendente (profundidade documento) com nome local."""
    if parent is None:
        return None
    ln = local_name.lower()
    for el in parent.iter():
        if _xml_tag_local(el.tag).lower() == ln:
            return el
    return None


def _nfse_abrasf_root_find_all_nfse(root):
    """
    Todas as tags Nfse (ABRASF com ou sem xmlns).
    findall('.//Nfse') falha quando o arquivo usa namespace padrão.
    """
    out = []
    for el in root.iter():
        if _xml_tag_local(el.tag).lower() == 'nfse':
            out.append(el)
    return out


def _nfse_abrasf_buscar_inf_nfse(nfse_el):
    """InfNfse com ou sem namespace; variações de capitalização."""
    for nome in ('InfNfse', 'InfNFSe', 'infNFSe'):
        n = nfse_el.find(nome)
        if n is not None:
            return n
    for child in nfse_el:
        if _xml_tag_local(child.tag).lower() == 'infnfse':
            return child
    for el in nfse_el.iter():
        if el is not nfse_el and _xml_tag_local(el.tag).lower() == 'infnfse':
            return el
    return None


def _nfse_abrasf_buscar_servico(inf_nfse):
    """
    Layout simples: InfNfse/Servico.
    ABRASF 2.x com DPS: DeclaracaoPrestacaoServico/InfDeclaracaoPrestacaoServico/Servico
    """
    s = inf_nfse.find('Servico')
    if s is not None:
        return s
    paths = (
        'DeclaracaoPrestacaoServico/InfDeclaracaoPrestacaoServico/Servico',
        'DeclaracaoPrestacaoServico/DeclaracaoPrestacaoServico/Servico',
    )
    for p in paths:
        s = inf_nfse.find(p)
        if s is not None:
            return s
    for el in inf_nfse.iter():
        if _xml_tag_local(el.tag).lower() == 'servico':
            return el
    return None


def _nfse_abrasf_extrair_prestador_cnpj(inf_nfse, prestador_servico):
    """IdentificacaoPrestador/Cnpj ou Prestador/CpfCnpj/Cnpj (DPS / 2.04). Sem namespace."""
    if prestador_servico is not None:
        idp = prestador_servico.find('IdentificacaoPrestador')
        if idp is None:
            idp = _nfse_first_direct_child_by_local(prestador_servico, 'IdentificacaoPrestador')
        if idp is not None:
            for tag in ('Cnpj', 'CPF', 'Cpf'):
                n = idp.find(tag)
                if n is None:
                    n = _nfse_first_direct_child_by_local(idp, tag)
                if n is not None and (n.text or '').strip():
                    return limpar_cnpj(n.text.strip())
        n = prestador_servico.find('IdentificacaoPrestador/Cnpj')
        if n is None and idp is not None:
            n = _nfse_first_direct_child_by_local(idp, 'Cnpj')
        if n is not None and (n.text or '').strip():
            return limpar_cnpj(n.text.strip())

    inf_decl = _nfse_first_by_local(inf_nfse, 'InfDeclaracaoPrestacaoServico')
    if inf_decl is not None:
        prest = _nfse_first_direct_child_by_local(inf_decl, 'Prestador')
        if prest is not None:
            cpf_blk = _nfse_first_direct_child_by_local(prest, 'CpfCnpj')
            if cpf_blk is None:
                cpf_blk = _nfse_first_direct_child_by_local(prest, 'CPFCNPJ')
            if cpf_blk is not None:
                for tag in ('Cnpj', 'CPF', 'Cpf'):
                    n = _nfse_first_direct_child_by_local(cpf_blk, tag)
                    if n is not None and (n.text or '').strip():
                        return limpar_cnpj(n.text.strip())

    for path in (
        'DeclaracaoPrestacaoServico/InfDeclaracaoPrestacaoServico/Prestador/CpfCnpj/Cnpj',
        './/InfDeclaracaoPrestacaoServico/Prestador/CpfCnpj/Cnpj',
        './/Prestador/CpfCnpj/Cnpj',
    ):
        n = inf_nfse.find(path)
        if n is not None and (n.text or '').strip():
            return limpar_cnpj(n.text.strip())
    return ''


def _nfse_abrasf_decimal(el, path, default='0'):
    if el is None:
        return Decimal(default)
    n = el.find(path) if path else el
    if n is None or n.text is None or not str(n.text).strip():
        return Decimal(default)
    try:
        return Decimal(str(n.text).strip().replace(',', '.'))
    except Exception:
        return Decimal(default)


def _nfse_valores_get_decimal(valores, local_name):
    """Filho de Valores com nome local (ex.: ValorServicos), ignora namespace."""
    if valores is None:
        return Decimal('0')
    ln = local_name.lower()
    for c in valores:
        if _xml_tag_local(c.tag).lower() == ln:
            return _nfse_abrasf_decimal(c, None)
    return Decimal('0')


def _nfse_abrasf_data_emissao(inf_nfse):
    """DataEmissao texto -> datetime aware."""
    de = inf_nfse.find('DataEmissao')
    if de is None:
        de = _nfse_first_direct_child_by_local(inf_nfse, 'DataEmissao')
    if de is None or not (de.text or '').strip():
        return timezone.now()
    s = de.text.strip()
    dt = parse_datetime(s.replace(' ', 'T') if 'T' not in s and len(s) > 10 else s)
    if dt is not None:
        if timezone.is_naive(dt):
            return timezone.make_aware(dt)
        return dt
    pd = parse_date(s[:10])
    if pd is not None:
        return timezone.make_aware(datetime.combine(pd, time.min))
    return timezone.now()


def _nfse_abrasf_chave_artificial(numero_nota, serie, cnpj_prest):
    base = 'NFSE-%s-%s-%s' % (numero_nota, serie, cnpj_prest or '0')
    if len(base) <= 44:
        return base.ljust(44, '0')[:44]
    return hashlib.sha256(base.encode('utf-8')).hexdigest()[:44]


def processar_xml_nfse(xml_content, empresa_id):
    """Processa o XML da NFS-e (Nota Fiscal de Serviços) — ABRASF simples e 2.x / ListaNfse."""

    try:
        print("DEBUG: Iniciando processamento NFS-e")
        root = ET.fromstring(xml_content)
        print(f"DEBUG: Root NFS-e: {root.tag}")

        empresa = Empresa.objects.get(id=empresa_id)
        notas_processadas = []

        nfse_elements = _nfse_abrasf_root_find_all_nfse(root)
        print(f"DEBUG: Encontradas {len(nfse_elements)} NFS-e no XML")

        if not nfse_elements:
            raise ValueError('Nenhuma NFS-e encontrada no XML')

        for nfse in nfse_elements:
            print("DEBUG: Processando uma NFS-e")
            inf_nfse = _nfse_abrasf_buscar_inf_nfse(nfse)
            if inf_nfse is None:
                print("DEBUG: InfNfse não encontrado, pulando...")
                continue

            cancelamento = nfse.find('NfseCancelamento')
            if cancelamento is None:
                cancelamento = _nfse_first_direct_child_by_local(nfse, 'NfseCancelamento')
            if cancelamento is not None:
                num_el = inf_nfse.find('Numero')
                numero = num_el.text if num_el is not None and num_el.text else 'N/A'
                print(f"NFS-e {numero} foi cancelada, pulando...")
                continue

            num_el = inf_nfse.find('Numero')
            if num_el is None:
                num_el = _nfse_first_direct_child_by_local(inf_nfse, 'Numero')
            if num_el is None:
                num_el = _nfse_first_by_local(inf_nfse, 'Numero')
            if num_el is None or not (num_el.text or '').strip():
                print("DEBUG: Numero ausente, pulando...")
                continue
            numero_nota = num_el.text.strip()

            serie_el = inf_nfse.find('Serie')
            if serie_el is None:
                serie_el = _nfse_first_direct_child_by_local(inf_nfse, 'Serie')
            serie = (serie_el.text.strip() if serie_el is not None and serie_el.text else 'NFSE')

            print(f"DEBUG: NFS-e {numero_nota}, série {serie}")

            if NotaFiscalEntrada.objects.filter(
                empresa=empresa,
                numero_nota=numero_nota,
                serie=serie,
            ).exists():
                print(f"NFS-e {numero_nota} já foi importada, pulando...")
                continue

            prestador = _nfse_first_direct_child_by_local(inf_nfse, 'PrestadorServico')
            if prestador is None:
                prestador = _nfse_first_by_local(inf_nfse, 'PrestadorServico')
            prestador_cnpj = _nfse_abrasf_extrair_prestador_cnpj(inf_nfse, prestador)

            prestador_razao = ''
            if prestador is not None:
                rz = prestador.find('RazaoSocial')
                if rz is not None and rz.text:
                    prestador_razao = rz.text.strip()
            if not prestador_razao:
                prestador_razao = 'FORNECEDOR'

            prestador_fone = ''
            if prestador is not None:
                tel = prestador.find('Contato/Telefone')
                if tel is not None and tel.text:
                    prestador_fone = tel.text.strip()[:11]

            if not prestador_cnpj:
                print("DEBUG: CNPJ do prestador não encontrado, pulando...")
                continue

            print(f"DEBUG: Prestador - CNPJ: {prestador_cnpj}, Razão: {prestador_razao}")

            fornecedor = None
            fornecedor, created = Fornecedor.objects.get_or_create(
                empresa=empresa,
                cnpj=prestador_cnpj,
                defaults={
                    'razao': (prestador_razao or 'FORNECEDOR')[:50],
                    'telefone': prestador_fone or '0',
                },
            )
            if created:
                print(f"Fornecedor criado: {fornecedor.razao} - CNPJ: {fornecedor.cnpj}")

            tomador = _nfse_first_direct_child_by_local(inf_nfse, 'TomadorServico')
            if tomador is None:
                tomador = _nfse_first_by_local(inf_nfse, 'TomadorServico')
            tomador_cnpj = None
            tomador_razao = ''
            if tomador is not None:
                id_tom = tomador.find('IdentificacaoTomador')
                if id_tom is not None:
                    cpf_cnpj_element = id_tom.find('CpfCnpj')
                    if cpf_cnpj_element is None:
                        cpf_cnpj_element = tomador.find('IdentificacaoTomador/CpfCnpj')
                else:
                    cpf_cnpj_element = tomador.find('IdentificacaoTomador/CpfCnpj')
                if cpf_cnpj_element is not None:
                    cnpj_element = cpf_cnpj_element.find('Cnpj')
                    cpf_element = cpf_cnpj_element.find('Cpf')
                    if cnpj_element is not None and cnpj_element.text:
                        tomador_cnpj = limpar_cnpj(cnpj_element.text.strip())
                    elif cpf_element is not None and cpf_element.text:
                        tomador_cnpj = limpar_cnpj(cpf_element.text.strip())
                tr = tomador.find('RazaoSocial')
                if tr is not None and tr.text:
                    tomador_razao = tr.text.strip()
            print(f"DEBUG: Tomador - CNPJ: {tomador_cnpj}, Razão: {tomador_razao}")

            servico = _nfse_abrasf_buscar_servico(inf_nfse)
            if servico is None:
                print("DEBUG: Servico não encontrado, pulando...")
                continue

            valores = servico.find('Valores')
            if valores is None:
                valores = _nfse_first_direct_child_by_local(servico, 'Valores')
            if valores is None:
                print("DEBUG: Valores (serviço) não encontrado, pulando...")
                continue

            v_serv = _nfse_valores_get_decimal(valores, 'ValorServicos')
            v_liq = _nfse_valores_get_decimal(valores, 'ValorLiquidoNfse')
            if v_liq == 0:
                vn = inf_nfse.find('ValoresNfse')
                if vn is None:
                    vn = _nfse_first_direct_child_by_local(inf_nfse, 'ValoresNfse')
                if vn is not None:
                    v_liq = _nfse_valores_get_decimal(vn, 'ValorLiquidoNfse')
            if v_liq == 0:
                v_liq = v_serv

            v_pis = _nfse_valores_get_decimal(valores, 'ValorPis')
            v_cofins = _nfse_valores_get_decimal(valores, 'ValorCofins')
            v_iss = _nfse_valores_get_decimal(valores, 'ValorIss')
            if v_iss == 0:
                v_iss = _nfse_valores_get_decimal(valores, 'ValorISS')
            desconto = Decimal('0')
            for child in valores:
                loc = _xml_tag_local(child.tag)
                if 'Desconto' in loc and 'Incond' in loc:
                    desconto = _nfse_abrasf_decimal(child, None)
                    break

            discriminacao_el = servico.find('Discriminacao')
            if discriminacao_el is None:
                discriminacao_el = _nfse_first_direct_child_by_local(servico, 'Discriminacao')
            discriminacao = (
                discriminacao_el.text.strip()
                if discriminacao_el is not None and discriminacao_el.text
                else 'SERVIÇO PRESTADO'
            )

            data_emissao_dt = _nfse_abrasf_data_emissao(inf_nfse)
            chave = _nfse_abrasf_chave_artificial(numero_nota, serie, prestador_cnpj)

            print("DEBUG: Criando nota fiscal NFS-e")
            with transaction.atomic():
                nota_fiscal = NotaFiscalEntrada.objects.create(
                    empresa=empresa,
                    tipo_nota='tomador',
                    chave_acesso=chave,
                    numero_nota=numero_nota,
                    serie=serie,
                    modelo='NFS',
                    fornecedor_cnpj=prestador_cnpj,
                    fornecedor_nome=(prestador_razao or 'FORNECEDOR')[:200],
                    fornecedor=fornecedor,
                    destinatario_cnpj=tomador_cnpj or '',
                    destinatario_nome=(tomador_razao or '')[:200],
                    data_emissao=data_emissao_dt,
                    valor_produtos=v_serv,
                    valor_frete=Decimal('0'),
                    valor_seguro=Decimal('0'),
                    valor_desconto=desconto,
                    valor_ii=Decimal('0'),
                    valor_ipi=Decimal('0'),
                    valor_pis=v_pis,
                    valor_cofins=v_cofins,
                    valor_icms=v_iss,
                    valor_total=v_liq,
                    xml_content=xml_content,
                    status='importada',
                )

                NotaFiscalEntradaItem.objects.create(
                    nota_fiscal=nota_fiscal,
                    numero_item=1,
                    codigo_produto='SERVICO',
                    nome_produto=discriminacao[:200],
                    cfop='0000',
                    unidade='UN',
                    quantidade=Decimal('1'),
                    valor_unitario=v_serv,
                    valor_total=v_serv,
                    valor_pis=v_pis,
                    valor_cofins=v_cofins,
                    valor_icms=v_iss,
                    valor_ipi=Decimal('0'),
                    valor_ii=Decimal('0'),
                )

            print(f"DEBUG: Nota fiscal criada com ID {nota_fiscal.id}")
            notas_processadas.append(nota_fiscal)

        print(f"DEBUG: Total de notas processadas: {len(notas_processadas)}")
        if not notas_processadas and nfse_elements:
            raise ValueError(
                'Nenhuma NFS-e foi importada (todas foram ignoradas). '
                'Verifique CNPJ do prestador, duplicidade de número/série ou XML com layout não reconhecido.'
            )
        return notas_processadas[0] if notas_processadas else None

    except ValueError:
        raise
    except Exception as e:
        print(f"Erro ao processar XML NFS-e: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

@login_required
def listar_notas_fiscais(request):
    """Lista todas as notas fiscais de entrada"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('dashboard:relatorio_mensal')

    notas = NotaFiscalEntrada.objects.filter(empresa_id=empresa_id).order_by('-data_emissao')

    # Filtros
    tipo_nota = request.GET.get('tipo_nota', '')
    status = request.GET.get('status', '')
    fornecedor = request.GET.get('fornecedor', '')
    data_inicio = request.GET.get('data_inicio', '')
    data_fim = request.GET.get('data_fim', '')

    if tipo_nota:
        notas = notas.filter(tipo_nota=tipo_nota)

    if status:
        notas = notas.filter(status=status)

    if fornecedor:
        notas = notas.filter(fornecedor_nome__icontains=fornecedor)

    if data_inicio:
        notas = notas.filter(data_emissao__date__gte=data_inicio)

    if data_fim:
        notas = notas.filter(data_emissao__date__lte=data_fim)

    # Verificar contas a pagar para cada nota
    from contasapagar.models import ContasaPagar
    notas_com_contas = []
    for nota in notas:
        # Verificar se existe conta a pagar com o mesmo número de documento
        tem_conta_pagar = ContasaPagar.objects.filter(
            numdoc=nota.numero_nota,
            fornecedor=nota.fornecedor
        ).exists()
        nota.tem_conta_pagar = tem_conta_pagar
        notas_com_contas.append(nota)

    context = {
        'notas': notas_com_contas,
        'filtros': {
            'tipo_nota': tipo_nota,
            'status': status,
            'fornecedor': fornecedor,
            'data_inicio': data_inicio,
            'data_fim': data_fim,
        }
    }

    return render(request, 'notafiscalentrada/listar.html', context)


def _resolver_fornecedor_cadastro_da_nota(nota, empresa_id):
    """
    Retorna o registro Fornecedor vinculado à nota (FK) ou localizado por CNPJ/CPF
    na empresa, pois algumas importações só preenchem fornecedor_cnpj sem FK.
    """
    if nota.fornecedor_id:
        return nota.fornecedor
    doc = limpar_cnpj(nota.fornecedor_cnpj or "")
    if not doc:
        return None
    for f in Fornecedor.objects.filter(empresa_id=empresa_id):
        if limpar_cnpj(f.cnpj) == doc:
            return f
    return None


def _fornecedor_ainda_referenciado_em_notas_entrada(fornecedor, empresa_id):
    """Outras notas (FK ou só texto de CNPJ) ainda usam este fornecedor."""
    if NotaFiscalEntrada.objects.filter(
        empresa_id=empresa_id, fornecedor=fornecedor
    ).exists():
        return True
    doc = limpar_cnpj(fornecedor.cnpj or "")
    if not doc:
        return False
    qs = NotaFiscalEntrada.objects.filter(
        empresa_id=empresa_id, fornecedor__isnull=True
    ).only("fornecedor_cnpj")
    for n in qs.iterator():
        if limpar_cnpj(n.fornecedor_cnpj or "") == doc:
            return True
    return False


def _excluir_fornecedor_se_orfao(fornecedor, empresa_id):
    """
    Remove o cadastro do fornecedor se não restar nenhum vínculo
    (outras notas de entrada, contas a pagar ou regras de conciliação).
    Retorna True se o fornecedor foi excluído.
    """
    if fornecedor is None:
        return False
    if fornecedor.empresa_id and int(fornecedor.empresa_id) != int(empresa_id):
        return False
    if _fornecedor_ainda_referenciado_em_notas_entrada(fornecedor, empresa_id):
        return False
    if ContasaPagar.objects.filter(fornecedor=fornecedor).exists():
        return False
    if RegraConciliacao.objects.filter(fornecedor=fornecedor).exists():
        return False
    fornecedor.delete()
    return True


@login_required
@require_POST
def excluir_nota_fiscal(request, pk):
    """Exclui nota de entrada (tomador ou comércio) se não houver conta a pagar vinculada."""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('dashboard:relatorio_mensal')

    nota = get_object_or_404(NotaFiscalEntrada, pk=pk, empresa_id=empresa_id)
    numero = nota.numero_nota

    tem_conta_pagar = ContasaPagar.objects.filter(
        numdoc=nota.numero_nota,
        fornecedor=nota.fornecedor,
    ).exists()
    if tem_conta_pagar:
        messages.error(
            request,
            'Não é possível excluir esta nota: já existe conta a pagar vinculada.',
        )
        return redirect('notafiscalentrada:listar')

    fornecedor_alvo = _resolver_fornecedor_cadastro_da_nota(nota, empresa_id)
    with transaction.atomic():
        nota.delete()
        fornecedor_removido = _excluir_fornecedor_se_orfao(fornecedor_alvo, empresa_id)

    msg = 'Nota fiscal %s excluída com sucesso.' % numero
    if fornecedor_removido:
        msg += (
            ' O cadastro do fornecedor foi removido por não haver outros vínculos.'
        )
    messages.success(request, msg)
    return redirect('notafiscalentrada:listar')


@login_required
def detalhes_modal(request, tipo, id):
    """
    View para fornecer dados ao modal de detalhes
    """
    print(f"DEBUG: detalhes_modal chamada com tipo={tipo}, id={id}")
    empresa_id = request.session.get('empresa_id')
    print(f"DEBUG: empresa_id={empresa_id}")
    if not empresa_id:
        print("DEBUG: Empresa não selecionada")
        return JsonResponse({'error': 'Empresa não selecionada'}, status=400)

    try:
        # Buscar o objeto baseado no tipo
        if tipo == 'nota_fiscal':
            print(f"DEBUG: Buscando nota fiscal com id={id}, empresa_id={empresa_id}")
            obj = NotaFiscalEntrada.objects.get(id=id, empresa_id=empresa_id)
            nota_fiscal = obj
            print(f"DEBUG: Nota fiscal encontrada: {nota_fiscal.numero_nota}")
        else:
            print(f"DEBUG: Tipo inválido: {tipo}")
            return JsonResponse({'error': 'Tipo inválido'}, status=400)

        # Buscar itens da nota
        print(f"DEBUG: Buscando itens da nota fiscal")
        itens = nota_fiscal.itens.all().order_by('numero_item')
        print(f"DEBUG: Encontrados {itens.count()} itens")

        # Construir HTML do modal
        print(f"DEBUG: Construindo HTML do modal")
        html = f"""
        <div class="row">
            <div class="col-md-6">
                <h5>Nota Fiscal</h5>
                <p><strong>Chave de Acesso:</strong> {nota_fiscal.chave_acesso}</p>
                <p><strong>Número:</strong> {nota_fiscal.numero_nota}</p>
                <p><strong>Série:</strong> {nota_fiscal.serie}</p>
                <p><strong>Modelo:</strong> {nota_fiscal.modelo}</p>
                <p><strong>Tipo:</strong> {nota_fiscal.get_tipo_nota_display()}</p>
                <p><strong>Status:</strong> {nota_fiscal.get_status_display()}</p>
            </div>
            <div class="col-md-6">
                <h5>Fornecedor</h5>
                <p><strong>Nome:</strong> {nota_fiscal.fornecedor_nome}</p>
                <p><strong>CNPJ:</strong> {nota_fiscal.fornecedor_cnpj}</p>
                <h5 class="mt-3">Destinatário</h5>
                <p><strong>Nome:</strong> {nota_fiscal.destinatario_nome}</p>
                <p><strong>CNPJ:</strong> {nota_fiscal.destinatario_cnpj}</p>
            </div>
        </div>
        <div class="row mt-3">
            <div class="col-md-6">
                <h5>Datas</h5>
                <p><strong>Emissão:</strong> {nota_fiscal.data_emissao.strftime('%d/%m/%Y %H:%M') if nota_fiscal.data_emissao else 'N/A'}</p>
                <p><strong>Saída/Entrada:</strong> {nota_fiscal.data_saida_entrada.strftime('%d/%m/%Y %H:%M') if nota_fiscal.data_saida_entrada else 'N/A'}</p>
            </div>
            <div class="col-md-6">
                <h5>Valores</h5>
                <p><strong>Produtos:</strong> R$ {nota_fiscal.valor_produtos:.2f}</p>
                <p><strong>Frete:</strong> R$ {nota_fiscal.valor_frete:.2f}</p>
                <p><strong>Seguro:</strong> R$ {nota_fiscal.valor_seguro:.2f}</p>
                <p><strong>Desconto:</strong> R$ {nota_fiscal.valor_desconto:.2f}</p>
                <p><strong>Total Impostos:</strong> R$ {nota_fiscal.get_valor_impostos():.2f}</p>
                <p><strong>Total NF:</strong> R$ {nota_fiscal.valor_total:.2f}</p>
            </div>
        </div>
        <div class="row mt-3">
            <div class="col-md-12">
                <h5>Itens da Nota Fiscal</h5>
                <div class="table-responsive">
                    <table class="table table-sm table-striped">
                        <thead>
                            <tr>
                                <th>Item</th>
                                <th>Produto</th>
                                <th>CFOP</th>
                                <th>Qtde</th>
                                <th>Valor Unit.</th>
                                <th>Valor Total</th>
                            </tr>
                        </thead>
                        <tbody>
        """

        for item in itens[:10]:  # Limitar a 10 itens para não sobrecarregar o modal
            html += f"""
                            <tr>
                                <td>{item.numero_item}</td>
                                <td>{item.nome_produto[:50]}...</td>
                                <td>{item.cfop}</td>
                                <td>{item.quantidade} {item.unidade}</td>
                                <td>R$ {item.valor_unitario:.2f}</td>
                                <td>R$ {item.valor_total:.2f}</td>
                            </tr>
            """

        html += """
                        </tbody>
                    </table>
                </div>
        """

        if itens.count() > 10:
            html += f"<p class='text-muted'>... e mais {itens.count() - 10} itens</p>"

        html += """
            </div>
        </div>
        """
        print(f"DEBUG: HTML construído com sucesso, tamanho: {len(html)} caracteres")

        return JsonResponse({'html': html})

    except Exception as e:
        print(f"DEBUG: Erro na view detalhes_modal: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': f'Erro interno: {str(e)}'}, status=500)

@login_required
def buscar_categorias(request):
    """Busca categorias para autocomplete"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return JsonResponse({'error': 'Empresa não encontrada na sessão.'}, status=400)

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        return JsonResponse({'error': 'Empresa não encontrada.'}, status=404)

    termo = request.GET.get('q', '').strip()
    if len(termo) < 4:
        return JsonResponse({'categorias': []})

    # Buscar categorias que contenham o termo no nome ou classificação
    # Excluir categorias do tipo 'R' (Receita) conforme solicitado
    categorias = Categoria.objects.filter(
        empresa=empresa
    ).exclude(tipo='R').filter(
        Q(nome__icontains=termo) | Q(classificacao__icontains=termo)
    ).order_by('tipo', 'nome')[:20]  # Limitar a 20 resultados

    # Preparar dados para resposta
    categorias_data = []
    for categoria in categorias:
        tipo_display = {
            'R': 'Receita',
            'D': 'Despesa',
            'I': 'Investimento',
            'L': 'Distribuição de Lucro'
        }.get(categoria.tipo, categoria.tipo)

        categorias_data.append({
            'id': categoria.id,
            'nome': categoria.nome,
            'classificacao': categoria.classificacao,
            'nome_completo': f"{categoria.classificacao} {categoria.nome}",
            'tipo': categoria.tipo,
            'tipo_display': tipo_display,
            'grupo': categoria.grupo
        })

    return JsonResponse({'categorias': categorias_data})

@login_required
def buscar_formas_pagamento(request):
    """Busca formas de pagamento para autocomplete"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        return JsonResponse({'error': 'Empresa não encontrada na sessão.'}, status=400)

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        return JsonResponse({'error': 'Empresa não encontrada.'}, status=404)

    termo = request.GET.get('q', '').strip()
    if len(termo) < 2:
        return JsonResponse({'formas_pagamento': []})

    # Buscar formas de pagamento que contenham o termo na descrição (gerais ou da empresa)
    formas_pagamento = Cobranca.objects.filter(
        descricao__icontains=termo
    ).order_by('descricao')[:20]  # Limitar a 20 resultados

    # Preparar dados para resposta
    formas_data = []
    for forma in formas_pagamento:
        tipo_display = 'À Vista' if forma.formapgto == '0' else 'À Prazo'

        formas_data.append({
            'id': forma.id,
            'descricao': forma.descricao,
            'tipo': forma.formapgto,
            'tipo_display': tipo_display,
            'qtparcelas': '1',
            'intervaloparcelas': getattr(forma, 'intervaloparcelas', 0)
        })

    return JsonResponse({'formas_pagamento': formas_data})

@login_required
def editar_nota_fiscal(request, pk):
    """Edita uma nota fiscal de entrada"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('notafiscalentrada:listar')

    nota = get_object_or_404(NotaFiscalEntrada, pk=pk, empresa_id=empresa_id)

    if request.method == 'POST':
        try:
            # Atualizar campos editáveis
            categoria_id = request.POST.get('categoria')
            forma_pagamento_id = request.POST.get('forma_pagamento')
            regra_rateio_id = request.POST.get('regra_rateio')
            observacao = request.POST.get('observacao')

            if categoria_id:
                from categoria.models import Categoria
                try:
                    categoria = Categoria.objects.get(id=categoria_id, empresa_id=empresa_id)
                    nota.categoria = categoria
                except Categoria.DoesNotExist:
                    pass

            if forma_pagamento_id:
                try:
                    forma_pagamento = Cobranca.objects.get(id=forma_pagamento_id)
                    nota.forma_pagamento = forma_pagamento
                except Cobranca.DoesNotExist:
                    pass

            if regra_rateio_id:
                from regrarateio.models import RegraRateio
                regra_rateio = RegraRateio.objects.filter(
                    pk=regra_rateio_id, empresa_id=nota.empresa_id
                ).first()
                if regra_rateio:
                    nota.regra_rateio = regra_rateio

            nota.observacoes = observacao
            nota.save()

            messages.success(request, 'Nota fiscal atualizada com sucesso!')
            return redirect('notafiscalentrada:listar')

        except Exception as e:
            messages.error(request, f'Erro ao atualizar nota fiscal: {str(e)}')
            return redirect('notafiscalentrada:editar', pk=pk)

    # Dados para o template
    from categoria.models import Categoria
    from regrarateio.models import RegraRateio
    categorias = Categoria.objects.filter(empresa_id=empresa_id)
    formas_pagamento = Cobranca.objects.all()
    regras_rateio = RegraRateio.objects.filter(empresa_id=empresa_id).order_by('nomedaregra')

    context = {
        'nota': nota,
        'categorias': categorias,
        'formas_pagamento': formas_pagamento,
        'regras_rateio': regras_rateio,
    }

    return render(request, 'notafiscalentrada/editar.html', context)

@login_required
def aplicar_categoria(request):
    """Aplica categoria a múltiplas notas fiscais selecionadas"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('notafiscalentrada:listar')

    if request.method != 'POST':
        return redirect('notafiscalentrada:listar')

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa não encontrada.')
        return redirect('notafiscalentrada:listar')

    # Obter dados do formulário
    notas_ids = request.POST.getlist('notas_ids')
    categoria_id = request.POST.get('categoria_id')

    if not notas_ids:
        messages.error(request, 'Nenhuma nota fiscal selecionada.')
        return redirect('notafiscalentrada:listar')

    if not categoria_id:
        messages.error(request, 'Categoria não selecionada.')
        return redirect('notafiscalentrada:listar')

    try:
        # Buscar categoria
        categoria = Categoria.objects.get(id=categoria_id, empresa_id=empresa_id)
    except Categoria.DoesNotExist:
        messages.error(request, 'Categoria não encontrada ou não pertence à empresa.')
        return redirect('notafiscalentrada:listar')

    # Buscar notas selecionadas
    notas = NotaFiscalEntrada.objects.filter(id__in=notas_ids, empresa=empresa)

    aplicadas = 0

    for nota in notas:
        try:
            # Aplicar categoria à nota
            nota.categoria = categoria
            nota.save()
            aplicadas += 1

        except Exception as e:
            print(f"Erro ao aplicar categoria à nota {nota.id}: {str(e)}")
            continue

    if aplicadas > 0:
        messages.success(request, f'Categoria "{categoria.nome}" aplicada a {aplicadas} nota(s) fiscal(is) com sucesso.')
    else:
        messages.warning(request, 'Nenhuma nota foi atualizada.')

    return redirect('notafiscalentrada:listar')

@login_required
def aplicar_forma_pagamento(request):
    """Aplica forma de pagamento a múltiplas notas fiscais selecionadas"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('notafiscalentrada:listar')

    if request.method != 'POST':
        return redirect('notafiscalentrada:listar')

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa não encontrada.')
        return redirect('notafiscalentrada:listar')

    # Obter dados do formulário
    notas_ids = request.POST.getlist('notas_ids_forma_pgto')
    forma_pagamento_id = request.POST.get('forma_pagamento_id')

    if not notas_ids:
        messages.error(request, 'Nenhuma nota fiscal selecionada.')
        return redirect('notafiscalentrada:listar')

    if not forma_pagamento_id:
        messages.error(request, 'Forma de pagamento não selecionada.')
        return redirect('notafiscalentrada:listar')

    try:
        forma_pagamento = Cobranca.objects.get(id=forma_pagamento_id)
    except Cobranca.DoesNotExist:
        messages.error(request, 'Forma de pagamento não encontrada ou não pertence à empresa.')
        return redirect('notafiscalentrada:listar')

    # Buscar notas selecionadas
    notas = NotaFiscalEntrada.objects.filter(id__in=notas_ids, empresa=empresa)

    aplicadas = 0

    for nota in notas:
        try:
            # Aplicar forma de pagamento à nota fiscal
            nota.forma_pagamento = forma_pagamento
            nota.save()  # O método save() criará/atualizará contas a pagar automaticamente se necessário
            aplicadas += 1

        except Exception as e:
            print(f"Erro ao aplicar forma de pagamento à nota {nota.id}: {str(e)}")
            continue

    if aplicadas > 0:
        messages.success(request, f'Forma de pagamento "{forma_pagamento.descricao}" aplicada a {aplicadas} nota(s) fiscal(is) com sucesso.')
    else:
        messages.warning(request, 'Nenhuma nota foi atualizada.')

    return redirect('notafiscalentrada:listar')

@login_required
def gerar_contas_a_pagar(request):
    """Gera contas a pagar a partir de múltiplas notas fiscais selecionadas"""
    empresa_id = request.session.get('empresa_id')
    if not empresa_id:
        messages.error(request, 'Empresa não encontrada na sessão.')
        return redirect('notafiscalentrada:listar')

    if request.method != 'POST':
        return redirect('notafiscalentrada:listar')

    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        messages.error(request, 'Empresa não encontrada.')
        return redirect('notafiscalentrada:listar')

    # Obter dados do formulário
    notas_ids = request.POST.getlist('notas')

    if not notas_ids:
        messages.error(request, 'Nenhuma nota fiscal selecionada.')
        return redirect('notafiscalentrada:listar')

    # Filtrar apenas notas que não possuem conta a pagar
    notas_filtradas = []
    for nota_id in notas_ids:
        try:
            nota = NotaFiscalEntrada.objects.get(id=nota_id, empresa=empresa)
            if not ContasaPagar.objects.filter(
                numdoc=nota.numero_nota,
                fornecedor=nota.fornecedor
            ).exists():
                notas_filtradas.append(nota_id)
        except NotaFiscalEntrada.DoesNotExist:
            continue

    if not notas_filtradas:
        messages.warning(request, 'Todas as notas selecionadas já possuem contas a pagar.')
        return redirect('notafiscalentrada:listar')

    notas_ids = notas_filtradas

    # Buscar notas selecionadas
    notas = NotaFiscalEntrada.objects.filter(id__in=notas_ids, empresa=empresa)

    contas_criadas = 0
    erros = []

    for nota in notas:
        try:
            # Verificar se já existe conta a pagar para esta nota
            if ContasaPagar.objects.filter(
                numdoc=nota.numero_nota,
                fornecedor=nota.fornecedor
            ).exists():
                erros.append(f'Nota {nota.numero_nota} já possui conta a pagar')
                continue

            # Buscar dados necessários
            categoria = nota.categoria
            forma_pagamento = nota.forma_pagamento

            if not categoria:
                erros.append(f'Nota {nota.numero_nota} não possui categoria definida')
                continue

            if not forma_pagamento:
                erros.append(f'Nota {nota.numero_nota} não possui forma de pagamento definida')
                continue

            # Buscar cobrança padrão
            cobranca = Cobranca.objects.first()
            if not cobranca:
                cobranca = Cobranca.objects.create(descricao='COBRANCA_PADRAO', tpag='00')

            # Buscar conta bancária padrão da empresa
            conta_banco = ContaBancaria.objects.filter(empresa=empresa, status='A').first()

            # Calcular data de vencimento (30 dias após emissão)
            data_vencimento = nota.data_emissao.date() + timedelta(days=30) if nota.data_emissao else None

            # Criar conta a pagar
            ContasaPagar.objects.create(
                empresa=empresa,
                fornecedor=nota.fornecedor,
                descricao=f'NF {nota.numero_nota} - {nota.fornecedor_nome}',
                numdoc=nota.numero_nota,
                valorDoc=nota.valor_total,
                categoria=categoria,
                cobranca=forma_pagamento or cobranca,
                conta_banco=conta_banco,
                parcela='1',
                dtEmissao=nota.data_emissao.date() if nota.data_emissao else None,
                dtvenc=data_vencimento,
                status='pendente',
                obs=f'Gerado automaticamente da NF-e {nota.numero_nota}'
            )

            contas_criadas += 1

        except Exception as e:
            erros.append(f'Erro ao criar conta para nota {nota.numero_nota}: {str(e)}')
            continue

    if contas_criadas > 0:
        messages.success(request, f'{contas_criadas} conta(s) a pagar criada(s) com sucesso!')

    if erros:
        for erro in erros:
            messages.warning(request, erro)

    return redirect('notafiscalentrada:listar')
