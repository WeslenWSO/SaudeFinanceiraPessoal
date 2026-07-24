from django import forms
from django.core.exceptions import ValidationError
from .models import NotaFiscalServico
from socio.models import Socio
from cobranca.models import Cobranca
from regraImposto.models import RegraImposto
import xml.etree.ElementTree as ET
import re
from decimal import Decimal
from django.forms import formset_factory

class PortalNacionalNfseForm(forms.Form):
    """
    Consulta NFSe na SEFIN nacional com mTLS (PFX): GET /dps/{id42} — uma nota por envio.
    O período informado só filtra **depois** do download (não lista notas por data na SEFIN).
    """

    data_periodo_inicio = forms.DateField(
        label="Período — data inicial (opcional)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text=(
            "Não busca notas por intervalo na API. Após baixar o XML desta DPS, a importação só prossegue "
            "se a data de emissão/competência do XML estiver entre esta data e a final."
        ),
    )
    data_periodo_fim = forms.DateField(
        label="Período — data final (opcional)",
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        help_text="Deixe as duas datas em branco para não filtrar por período após o download.",
    )
    serie_dps = forms.CharField(
        label="Série da DPS (opcional)",
        max_length=8,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: 70000 — veja no DANFSE / XML (infDPS)"}),
        help_text=(
            "Deve ser a **série da DPS** do documento (DANFSE ou XML), não a série “genérica” da NFS-e. "
            "Se vazio, usa “Série DPS padrão” na empresa e, se vazio, **80000** — muitos emitentes usam outra (ex. **70000**); "
            "valor errado gera E2404 na SEFIN."
        ),
    )
    numero_dps = forms.CharField(
        label="Número da DPS (opcional)",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: 101 — número da DPS, não o nº da NFS-e"}),
        help_text=(
            "É o **número da DPS** (infDPS), não o “Número da NFS-e” impresso se forem diferentes. "
            "Se vazio, usa “Próximo número da DPS” no cadastro (ou 1). Número errado → E2404 mesmo com a nota existindo para outro par série/nº."
        ),
    )
    numero_dps_ate = forms.CharField(
        label="Até número da DPS (opcional)",
        max_length=20,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Ex.: 120 — mesma série, vários números"}),
        help_text=(
            "Se preenchido, baixa **todas** as DPS da **mesma série** entre o número acima (ou o próximo do cadastro) "
            "e este valor, inclusive. Máximo 100 números por envio. Deixe em branco para consultar só uma DPS."
        ),
    )
    importar_canceladas = forms.BooleanField(
        label="Nota cancelada (importar com valores zerados)",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, empresa=None, **kwargs):
        self.empresa = empresa
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        di = cleaned.get("data_periodo_inicio")
        df = cleaned.get("data_periodo_fim")
        if (di and not df) or (df and not di):
            raise ValidationError("Informe data inicial e final do período, ou deixe as duas em branco.")
        if di and df and di > df:
            raise ValidationError("A data inicial do período não pode ser maior que a final.")
        if not self.empresa:
            raise ValidationError("Selecione uma empresa na sessão.")

        ibge = re.sub(r"\D", "", (getattr(self.empresa, "nfse_nacional_codigo_ibge_municipio", None) or "").strip())
        if len(ibge) != 7:
            raise ValidationError(
                "Cadastre o código IBGE do município (7 dígitos) na empresa em edição — "
                "ele não é informado nesta tela."
            )
        serie_in = re.sub(r"\D", "", (cleaned.get("serie_dps") or "").strip())
        num_in = re.sub(r"\D", "", (cleaned.get("numero_dps") or "").strip())
        if not serie_in:
            serie_in = re.sub(
                r"\D", "", (getattr(self.empresa, "nfse_nacional_dps_serie_padrao", None) or "").strip()
            )
        if not serie_in:
            ult = (
                NotaFiscalServico.objects.filter(empresa=self.empresa)
                .order_by("-data_emissao", "-pk")
                .only("serie")
                .first()
            )
            if ult and (ult.serie or "").strip():
                serie_in = re.sub(r"\D", "", (ult.serie or "").strip())
        if not serie_in:
            serie_in = "80000"
        serie = serie_in.zfill(5)[-5:]
        sequencia_auto = False
        if not num_in:
            prox = getattr(self.empresa, "nfse_nacional_dps_proximo_numero", None)
            if prox is not None and int(prox) > 0:
                num_in = str(int(prox))
            else:
                num_in = "1"
            sequencia_auto = True
        num = num_in.zfill(15)[-15:]
        cleaned["_sequencia_numero_automatico"] = sequencia_auto
        cleaned["_numero_dps_informado_pelo_usuario"] = bool((cleaned.get("numero_dps") or "").strip())
        ate_raw = re.sub(r"\D", "", (cleaned.get("numero_dps_ate") or "").strip())
        if ate_raw:
            n_start = int(num)
            n_end = int(ate_raw)
            if n_start > n_end:
                raise ValidationError("O número inicial da DPS não pode ser maior que o «até número».")
            max_lote = 100
            if n_end - n_start + 1 > max_lote:
                raise ValidationError(f"Intervalo máximo de {max_lote} números de DPS por envio.")
            cleaned["_dps_numero_range"] = (n_start, n_end)
        else:
            cleaned["_dps_numero_range"] = None
        if not (self.empresa.cnpj or "").strip():
            raise ValidationError("Empresa da sessão sem CNPJ/CPF cadastrado; necessário para montar o identificador DPS.")
        doc = re.sub(r"\D", "", (self.empresa.cnpj or "").strip())
        if len(doc) == 14:
            # Id do infDPS / GET SEFIN: 8º dígito = tpInscrFed — 1=CPF, 2=CNPJ (padrão nacional / RFB).
            tipo_inc = "2"
            insc = doc
        elif len(doc) == 11:
            tipo_inc = "1"
            insc = doc.zfill(14)[-14:]
        else:
            raise ValidationError(
                "No cadastro da empresa, informe CNPJ com 14 dígitos ou CPF com 11 dígitos (somente números) para montar a DPS."
            )
        cleaned["_tipo_inscricao_dps"] = tipo_inc
        cleaned["_ibge_dps"] = ibge
        cleaned["_serie_dps"] = serie
        cleaned["_numero_dps"] = num
        cleaned["_inscricao_dps"] = insc
        return cleaned


class AdnNfseSyncForm(forms.Form):
    data_periodo_inicio = forms.DateField(
        label="Período inicial",
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    data_periodo_fim = forms.DateField(
        label="Período final",
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    max_documentos = forms.IntegerField(
        label="Máximo de documentos por sincronização",
        required=False,
        min_value=1,
        max_value=1000,
        initial=200,
        widget=forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "1000"}),
        help_text="Limite para evitar processamento muito grande em uma única execução.",
    )
    consultar_ultimo_nsu_primeiro = forms.BooleanField(
        label="Consultar último NSU no ADN antes de sincronizar",
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text=(
            "Chama GET /contribuintes/DFe/0 e usa MaiorNSU/UltimoNSU da resposta. "
            "Para CNPJ envia cnpjConsulta; para CPF (contribuinte PF) a consulta é só com o certificado. "
            "Use com cuidado ao alinhar o cursor ao valor remoto."
        ),
    )
    def clean(self):
        cleaned = super().clean()
        di = cleaned.get("data_periodo_inicio")
        df = cleaned.get("data_periodo_fim")
        if di and df and di > df:
            raise ValidationError("A data inicial não pode ser maior que a data final.")
        if cleaned.get("max_documentos") in (None, ""):
            cleaned["max_documentos"] = 200
        return cleaned


class PortalExtensaoNfseForm(forms.Form):
    """
    Período alinhado ao filtro da lista de NFSe: usado na página Portal (extensão), Selenium e importação da pasta.
    """

    data_inicio = forms.DateField(
        label="Data inicial",
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    data_fim = forms.DateField(
        label="Data final",
        required=True,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )

    def clean(self):
        cleaned = super().clean()
        di = cleaned.get("data_inicio")
        df = cleaned.get("data_fim")
        if di and df and di > df:
            raise ValidationError("A data inicial não pode ser maior que a data final.")
        if di and df:
            from notasfiscais.nfse_xml_copia import validar_periodo_um_mes_portal_nacional

            try:
                validar_periodo_um_mes_portal_nacional(di, df)
            except ValueError as e:
                raise ValidationError(str(e)) from e
        return cleaned


class XMLUploadForm(forms.Form):
    xml_file = forms.FileField(
        label='Arquivo XML',
        help_text='Selecione um arquivo XML de NFSe válido',
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xml',
            'id': 'xmlFile'
        })
    )
    importar_canceladas = forms.BooleanField(
        label='Estes XMLs são de notas canceladas (importar com valores zerados)',
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'importarCanceladas'})
    )
    
    def clean_xml_file(self):
        xml_file = self.cleaned_data.get('xml_file')
        
        if not xml_file:
            raise ValidationError('Este campo é obrigatório.')
        
        # Validações básicas
        if not xml_file.name.endswith('.xml'):
            raise ValidationError('O arquivo deve ser um XML válido.')
        
        if xml_file.size > 5 * 1024 * 1024:  # 5MB
            raise ValidationError('O arquivo é muito grande. Tamanho máximo: 5MB.')
        
        # Validação básica de XML (sem parse completo para evitar problemas)
        try:
            # Apenas verifica se o arquivo pode ser lido
            xml_file.read(1024)  # Lê apenas os primeiros 1KB
            xml_file.seek(0)  # Volta ao início do arquivo
        except Exception as e:
            raise ValidationError(f'Erro ao ler arquivo: {str(e)}')
        
        return xml_file

class NFSeForm(forms.ModelForm):
    class Meta:
        model = NotaFiscalServico
        fields = [
            'numero_nota', 'serie', 'data_emissao', 'cnpj_cpf', 'cliente',
            'socio', 'valor_bruto','aliquota' ,'valor_liquido', 'discriminacao', 'forma_pagamento','nsu',
            'observacoes', 'segmento', 'base_servico'
        ]
        widgets = {
            'numero_nota': forms.TextInput(attrs={'class': 'form-control'}),
            'serie': forms.TextInput(attrs={'class': 'form-control'}),
            'data_emissao': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'cnpj_cpf': forms.TextInput(attrs={'class': 'form-control'}),
            'cliente': forms.TextInput(attrs={'class': 'form-control'}),
            'socio': forms.Select(attrs={'class': 'form-select'}),
            'valor_bruto': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'aliquota': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'valor_liquido': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'discriminacao': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'observacoes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'segmento': forms.TextInput(attrs={'class': 'form-control'}),
            'forma_pagamento': forms.Select(attrs={'class': 'form-select'}),
            'nsu': forms.TextInput(attrs={'class': 'form-control'}),
            'base_servico': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        empresa_id = kwargs.pop('empresa_id', None)
        super().__init__(*args, **kwargs)
        
        if empresa_id:
            # Filtra formas de pagamento pela empresa
            self.fields['forma_pagamento'].queryset = Cobranca.objects.all()
            self.fields['socio'].queryset = Socio.objects.filter(empresa_id=empresa_id)
        # Configurar queryset para sócios
        #self.fields['socio'].queryset = Socio.objects.all()
    
    def clean(self):
        cleaned_data = super().clean()
        valor_bruto = cleaned_data.get('valor_bruto')
        valor_liquido = cleaned_data.get('valor_liquido')
        
        if valor_bruto and valor_liquido and valor_bruto < valor_liquido:
            raise ValidationError('O valor bruto não pode ser menor que o valor líquido.')

        return cleaned_data


class NFSeSegmentForm(forms.Form):
    numero_segmentos = forms.IntegerField(
        min_value=2,
        max_value=10,
        initial=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'id': 'numero_segmentos'
        }),
        label='Número de Segmentos'
    )

    def __init__(self, *args, **kwargs):
        numero_segmentos = kwargs.pop('numero_segmentos', 2)
        empresa_id = kwargs.pop('empresa_id', None)
        super().__init__(*args, **kwargs)

        # Ensure numero_segmentos field has the correct value
        if 'numero_segmentos' in self.data:
            numero_segmentos = int(self.data.get('numero_segmentos', 2))
            self.fields['numero_segmentos'].initial = numero_segmentos

        # Create dynamic fields for each segment
        for i in range(1, numero_segmentos + 1):
            self.fields[f'valor_bruto_{i}'] = forms.DecimalField(
                max_digits=10,
                decimal_places=2,
                min_value=0.01,
                widget=forms.NumberInput(attrs={
                    'class': 'form-control valor-segmento',
                    'step': '0.01',
                    'id': f'valor_bruto_{i}'
                }),
                label=f'Valor Bruto Segmento {i}'
            )

            self.fields[f'forma_pagamento_{i}'] = forms.ModelChoiceField(
                queryset=Cobranca.objects.all(),
                empty_label='Selecione...',
                widget=forms.Select(attrs={
                    'class': 'form-select',
                    'id': f'forma_pagamento_{i}'
                }),
                label=f'Forma de Pagamento Segmento {i}'
            )

            self.fields[f'socio_{i}'] = forms.ModelChoiceField(
                queryset=Socio.objects.filter(empresa_id=empresa_id) if empresa_id else Socio.objects.none(),
                empty_label='Selecione...',
                widget=forms.Select(attrs={
                    'class': 'form-select',
                    'id': f'socio_{i}'
                }),
                label=f'Sócio Segmento {i}'
            )


            self.fields[f'codigo_regra_imposto_{i}'] = forms.ModelChoiceField(
                queryset=RegraImposto.objects.all().order_by('DescricaoRegraImposto'),
                empty_label='Selecione...',
                widget=forms.Select(attrs={
                    'class': 'form-select',
                    'id': f'codigo_regra_imposto_{i}'
                }),
                label=f'Código da Regra do Imposto Segmento {i}',
                required=False
            )

            self.fields[f'segmento_{i}'] = forms.CharField(
                max_length=100,
                widget=forms.TextInput(attrs={
                    'class': 'form-control',
                    'id': f'segmento_{i}',
                    'placeholder': 'Nome do segmento'
                }),
                label=f'Segmento {i}',
                required=False
            )

            self.fields[f'base_servico_{i}'] = forms.ChoiceField(
                choices=[('NORMAL', 'Normal'), ('DEMAIS', 'Demais')],
                widget=forms.Select(attrs={
                    'class': 'form-select',
                    'id': f'base_servico_{i}'
                }),
                label=f'Tipo de Base Segmento {i}',
                required=False
            )

class NFSeRecebimentoForm(forms.ModelForm):
    data_recebimento = forms.DateField(
        widget=forms.DateInput(
            format='%Y-%m-%d',
            attrs={'type': 'date', 'class': 'form-control'}
        ),
        input_formats=['%Y-%m-%d', '%d/%m/%Y'],
        label='Data do Recebimento'
    )

    class Meta:
        model = NotaFiscalServico
        fields = [
             'status_conciliacao'
        ]
        widgets = {
            
            'status_conciliacao': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        

    def clean(self):
        cleaned_data = super().clean()
        valor_recebido = cleaned_data.get('valor_recebido')
        valor_liquido = self.instance.valor_liquido if self.instance else None

        if valor_recebido and valor_liquido and valor_recebido > valor_liquido:
            raise ValidationError('O valor recebido não pode ser maior que o valor líquido da NFSe.')

        return cleaned_data

class NFSeUpdateForm(forms.ModelForm):
    data_emissao = forms.DateField(
        widget=forms.DateInput(
            format='%Y-%m-%d',  # formato para renderizar preenchido no input type=date
            attrs={'type': 'date', 'class': 'form-control'}
        ),
        input_formats=['%Y-%m-%d', '%d/%m/%Y']  # aceita ISO e BR na submissão
        )
    class Meta:
        model = NotaFiscalServico
        fields = [
            'numero_nota', 'serie', 'data_emissao', 'cnpj_cpf', 'cliente',
            'socio', 'valor_bruto','aliquota', 'valor_liquido', 'discriminacao', 'forma_pagamento','nsu',
            'observacoes', 'segmento', 'status_conciliacao', 'base_servico', 'codigo_da_regra_do_imposto'
        ]
        widgets = {
            'numero_nota': forms.TextInput(attrs={'class': 'form-control'}),
            'serie': forms.TextInput(attrs={'class': 'form-control'}),
            
            'cnpj_cpf': forms.TextInput(attrs={'class': 'form-control'}),
            'cliente': forms.TextInput(attrs={'class': 'form-control'}),
            'socio': forms.Select(attrs={'class': 'form-select'}),
            'valor_bruto': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'aliquota': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'valor_liquido': forms.NumberInput(attrs={'step': '0.01', 'min': '0', 'class': 'form-control'}),
            'discriminacao': forms.Textarea(attrs={'rows': 4, 'class': 'form-control'}),
            'observacoes': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'segmento': forms.TextInput(attrs={'class': 'form-control'}),
            'forma_pagamento': forms.Select(attrs={'class': 'form-select'}),
            'nsu': forms.TextInput(attrs={'class': 'form-control'}),
            'status_conciliacao': forms.Select(attrs={'class': 'form-select'}),
            'base_servico': forms.Select(attrs={'class': 'form-select'}),
            'codigo_da_regra_do_imposto': forms.Select(attrs={'class': 'form-select'}),
        }
        
    
    def __init__(self, *args, **kwargs):
        empresa_id = kwargs.pop('empresa_id', None)
        super().__init__(*args, **kwargs)

        if empresa_id:
            self.fields['forma_pagamento'].queryset = Cobranca.objects.all()
            self.fields['socio'].queryset = Socio.objects.filter(empresa_id=empresa_id)        # Configurar queryset para sócios
        #self.fields['socio'].queryset = Socio.objects.all()

        # Configurar queryset para regras de imposto (apenas da empresa)
        from regraImposto.models import RegraImposto
        self.fields['codigo_da_regra_do_imposto'].queryset = RegraImposto.objects.all().order_by('DescricaoRegraImposto')

        if self.instance and self.instance.pk and self.instance.data_emissao:
            self.initial['data_emissao'] = self.instance.data_emissao.strftime('%Y-%m-%d')
    
    def clean(self):
        cleaned_data = super().clean()
        valor_bruto = cleaned_data.get('valor_bruto')
        valor_liquido = cleaned_data.get('valor_liquido')
        
        if valor_bruto and valor_liquido and valor_bruto < valor_liquido:
            raise ValidationError('O valor bruto não pode ser menor que o valor líquido.')
        
        return cleaned_data

