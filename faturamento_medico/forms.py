from django import forms
from django.utils import timezone
from .models import FaturamentoMedico, DocumentoAnexado, ItemServico, ServicoDisponivel
from servicos_medicos.models import TabelaPreco, Convenio
from empresa.models import Empresa


class FaturamentoMedicoForm(forms.ModelForm):
    """Formulário para Faturamento Médico"""

    # Campo temporário para upload de documento para extração de dados
    documento_upload = forms.FileField(
        required=False,
        label='Documento para Extração (Imagem/PDF)',
        help_text='Selecione uma imagem ou PDF para extrair dados automaticamente usando IA',
        widget=forms.ClearableFileInput(attrs={
            'accept': '.pdf,.jpg,.jpeg,.png,.gif,.bmp,.tiff'
        })
    )

    # Campo para arquivo para processamento com Gemini
    documentos_gemini = forms.FileField(
        required=False,
        label='Documento para Gemini',
        help_text='Selecione um arquivo (PDF, imagens) para processamento com Gemini',
        widget=forms.FileInput(attrs={
            'accept': '.pdf,.jpg,.jpeg,.png,.gif,.bmp,.tiff,.doc,.docx'
        })
    )

    class Meta:
        model = FaturamentoMedico
        fields = [
            'lote', 'guia', 'carteirinha', 'nome', 'nome_associado',
            'data_autorizacao', 'data', 'total',
            'local', 'medico', 'medico_solicitante', 'anestesista', 'tecnico',
            'checkin_por', 'agendado_por',
            'convenio', 'receber_por', 'apartamento_enfermaria', 'urgencia',
            'prioridade', 'horario_inicio', 'horario_fim',
            'cpf', 'status_agendamento', 'motivo_cancelamento',
            'tag', 'indicacao_clinica', 'descricao', 'observacao',
            'guia_lancada', 'numero_guia_lancada', 'nota_fiscal',
            'codigo_relatorio', 'agendado_via', 'codigo_fechamento',
        ]
        widgets = {
            'lote': forms.TextInput(attrs={'class': 'form-control'}),
            'guia': forms.TextInput(attrs={'class': 'form-control'}),
            'carteirinha': forms.TextInput(attrs={'class': 'form-control'}),
            'nome': forms.TextInput(attrs={'class': 'form-control'}),
            'nome_associado': forms.TextInput(attrs={'class': 'form-control'}),
            'data_autorizacao': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'data': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'total': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'readonly': True,
            }),
            'local': forms.TextInput(attrs={'class': 'form-control'}),
            'medico': forms.TextInput(attrs={'class': 'form-control'}),
            'medico_solicitante': forms.TextInput(attrs={'class': 'form-control'}),
            'anestesista': forms.TextInput(attrs={'class': 'form-control'}),
            'tecnico': forms.TextInput(attrs={'class': 'form-control'}),
            'checkin_por': forms.TextInput(attrs={'class': 'form-control'}),
            'agendado_por': forms.TextInput(attrs={'class': 'form-control'}),
            'convenio': forms.TextInput(attrs={'class': 'form-control'}),
            'receber_por': forms.TextInput(attrs={'class': 'form-control'}),
            'apartamento_enfermaria': forms.Select(attrs={'class': 'form-select'}),
            'urgencia': forms.Select(attrs={'class': 'form-select'}),
            'prioridade': forms.TextInput(attrs={'class': 'form-control'}),
            'horario_inicio': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '21:00'}),
            'horario_fim': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '21:30'}),
            'cpf': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '000.000.000-00'}),
            'status_agendamento': forms.TextInput(attrs={'class': 'form-control'}),
            'motivo_cancelamento': forms.TextInput(attrs={'class': 'form-control'}),
            'tag': forms.TextInput(attrs={'class': 'form-control'}),
            'indicacao_clinica': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'descricao': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
            'observacao': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'guia_lancada': forms.NumberInput(attrs={'min': '0', 'class': 'form-control'}),
            'numero_guia_lancada': forms.TextInput(attrs={'class': 'form-control'}),
            'nota_fiscal': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo_relatorio': forms.TextInput(attrs={'class': 'form-control'}),
            'agendado_via': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo_fechamento': forms.TextInput(attrs={'readonly': True, 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        empresa_id = kwargs.pop('empresa_id', None)
        super().__init__(*args, **kwargs)
        # Define valores padrão apenas para criação
        if not self.instance:
            # Para novo, usa data atual
            self.initial['data_autorizacao'] = timezone.now().date()
            self.initial['data'] = timezone.now().date()
        else:
            # Para edição, define initial com os valores da instância formatados
            if self.instance.data_autorizacao:
                self.initial['data_autorizacao'] = self.instance.data_autorizacao.strftime('%Y-%m-%d')
            if self.instance.data:
                self.initial['data'] = self.instance.data.strftime('%Y-%m-%d')

        # Configurar campo convenio como ModelChoiceField filtrado por empresa
        if empresa_id:
            try:
                empresa = Empresa.objects.get(id=empresa_id)
                convenios = Convenio.objects.filter(empresa=empresa)
                self.fields['convenio'] = forms.ModelChoiceField(
                    queryset=convenios,
                    required=False,
                    label='Convênio',
                    empty_label='Selecione um convênio',
                    widget=forms.Select(attrs={'class': 'form-select'})
                )
                # Definir valor inicial se for edição
                if self.instance and self.instance.pk and self.instance.convenio:
                    try:
                        convenio_obj = Convenio.objects.get(nome=self.instance.convenio, empresa=empresa)
                        self.initial['convenio'] = convenio_obj
                    except Convenio.DoesNotExist:
                        pass
            except Empresa.DoesNotExist:
                # Fallback para choices hardcoded se empresa não existir
                self.fields['convenio'] = forms.ChoiceField(
                    choices=[
                        ('', 'Selecione um convênio'),
                        ('CBSAUDE', 'CBSAUDE'),
                        ('PM', 'PM'),
                        ('UNIMED', 'UNIMED'),
                        ('BRADESCO', 'BRADESCO'),
                        ('GEAP', 'GEAP'),
                        ('SAUDE CAIXA', 'SAUDE CAIXA'),
                        ('POSTAL SAUDE', 'POSTAL SAUDE'),
                        ('FUSEX', 'FUSEX'),
                        ('LIFE EMPRESARIAL', 'LIFE EMPRESARIAL'),
                        ('CASSI', 'CASSI'),
                        ('GCARD', 'GCARD'),
                        ('PERSONAL NET', 'PERSONAL NET'),
                    ],
                    required=False,
                    label='Convênio',
                    widget=forms.Select(attrs={'class': 'form-select'})
                )
        else:
            # Fallback para choices hardcoded se não houver empresa_id
            self.fields['convenio'] = forms.ChoiceField(
                choices=[
                    ('', 'Selecione um convênio'),
                    ('CBSAUDE', 'CBSAUDE'),
                    ('PM', 'PM'),
                    ('UNIMED', 'UNIMED'),
                    ('BRADESCO', 'BRADESCO'),
                    ('GEAP', 'GEAP'),
                    ('SAUDE CAIXA', 'SAUDE CAIXA'),
                    ('POSTAL SAUDE', 'POSTAL SAUDE'),
                    ('FUSEX', 'FUSEX'),
                    ('LIFE EMPRESARIAL', 'LIFE EMPRESARIAL'),
                    ('CASSI', 'CASSI'),
                    ('GCARD', 'GCARD'),
                    ('PERSONAL NET', 'PERSONAL NET'),
                ],
                required=False,
                label='Convênio',
                widget=forms.Select(attrs={'class': 'form-select'})
            )

        for name, field in self.fields.items():
            if name == 'documento_upload':
                field.widget.attrs.setdefault('class', 'form-control')
                continue
            css = field.widget.attrs.get('class', '')
            if 'form-control' not in css and 'form-select' not in css and 'form-check' not in css:
                field.widget.attrs['class'] = f'{css} form-control'.strip()

    def save(self, commit=True):
        instance = super().save(commit=False)
        # Se convenio for um objeto Convenio, converter para string
        if isinstance(self.cleaned_data.get('convenio'), Convenio):
            instance.convenio = self.cleaned_data['convenio'].nome
        if commit:
            instance.save()
        return instance


class DocumentoAnexadoForm(forms.ModelForm):
    """Formulário para upload de documentos anexados"""

    class Meta:
        model = DocumentoAnexado
        fields = ['arquivo', 'nome', 'descricao']
        widgets = {
            'arquivo': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': '.pdf,.doc,.docx,.xls,.xlsx,.jpg,.jpeg,.png,.gif'
            }),
            'nome': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome descritivo do documento'
            }),
            'descricao': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Descrição opcional do documento'
            }),
        }


class DocumentoAnexadoFormSet(forms.BaseModelFormSet):
    """FormSet para múltiplos documentos anexados"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self:
            form.empty_permitted = True


class ItemServicoForm(forms.ModelForm):
    """Formulário para item de serviço"""

    cabecalho = forms.ChoiceField(
        choices=[],
        required=True,
        label='Selecionar Cabeçalho',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'cabecalho_select'}),
        help_text='Selecione um cabeçalho para adicionar os serviços'
    )
    preco_apartamento = forms.DecimalField(
        required=False,
        label='Preço Apartamento',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': True, 'step': '0.01'}),
        help_text='Preço para apartamento'
    )
    preco_enfermaria = forms.DecimalField(
        required=False,
        label='Preço Enfermaria',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'readonly': True, 'step': '0.01'}),
        help_text='Preço para enfermaria'
    )


    class Meta:
        model = ItemServico
        fields = ['codigo_servico', 'servico', 'porte', 'modalidade', 'com_contraste', 'qt', 'valor', 'percentual']
        widgets = {
            'codigo_servico': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Código do serviço'
            }),
            'servico': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Descrição do serviço'
            }),
            'porte': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Porte'
            }),
            'modalidade': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'MR, CT, US...'
            }),
            'com_contraste': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'qt': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'value': '1'
            }),
            'valor': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'percentual': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '1',
                'value': '1.00',
                'placeholder': '1.00'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.faturamento = kwargs.pop('faturamento', None)
        super().__init__(*args, **kwargs)
        # Campo total é calculado automaticamente
        if 'total' in self.fields:
            self.fields['total'].widget = forms.HiddenInput()

        # Para edição, cabecalho não é obrigatório
        if self.instance and self.instance.pk:
            self.fields['cabecalho'].required = False

        # Inicializar choices vazios
        self.fields['cabecalho'].choices = [('', 'Selecione um cabeçalho...')]
        # Adicionar atributo list aos campos
        self.fields['codigo_servico'].widget.attrs.update({'list': 'servicos-list'})
        self.fields['servico'].widget.attrs.update({'list': 'servicos-descricao-list'})

        # Filtrar cabeçalhos pelo convênio do faturamento
        if self.faturamento:
            convenio_nome = self.faturamento.convenio
            if convenio_nome:
                try:
                    from servicos_medicos.models import Convenio, Cabecalho
                    convenio = Convenio.objects.get(nome=convenio_nome, empresa=self.faturamento.empresa)
                    cabecalhos = Cabecalho.objects.filter(
                        empresa=self.faturamento.empresa,
                        convenio=convenio
                    )
                    # Criar choices para cabeçalhos
                    cabecalho_choices = [('', 'Selecione um cabeçalho...')]
                    for cabecalho in cabecalhos:
                        cabecalho_choices.append((cabecalho.id, cabecalho.nome_tabela))
                    self.fields['cabecalho'].choices = cabecalho_choices
                except Convenio.DoesNotExist:
                    pass


class ItemServicoFormSet(forms.BaseModelFormSet):
    """FormSet para múltiplos itens de serviço"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self:
            form.empty_permitted = True

    def save(self, commit=True):
        """Salva os itens e atualiza o total do faturamento"""
        instances = super().save(commit=False)
        for instance in instances:
            if commit:
                instance.save()
        return instances


class ServicoDisponivelForm(forms.ModelForm):
    """Formulário para serviços disponíveis"""

    class Meta:
        model = ServicoDisponivel
        fields = ['codigo', 'descricao', 'porte', 'valor_base', 'categoria', 'subcategoria', 'ativo']
        widgets = {
            'codigo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Código único do serviço'
            }),
            'descricao': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Descrição completa do serviço'
            }),
            'porte': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Porte anestésico'
            }),
            'valor_base': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '0.00'
            }),
            'categoria': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Categoria do serviço'
            }),
            'subcategoria': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Subcategoria do serviço'
            }),
            'ativo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }