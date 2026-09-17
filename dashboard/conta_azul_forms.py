from django import forms

from dashboard.conta_azul.catalogos_fiscais import naturezas_operacao
from dashboard.models import ContaAzulConfig, ServicoContaAzul


class ContaAzulConfigForm(forms.ModelForm):
    client_secret = forms.CharField(
        label='Client Secret',
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text='Deixe em branco para manter o secret já gravado.',
    )

    class Meta:
        model = ContaAzulConfig
        fields = (
            'ativo',
            'ambiente',
            'client_id',
            'redirect_uri',
        )
        widgets = {
            'client_id': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'redirect_uri': forms.TextInput(attrs={'class': 'form-control'}),
            'ambiente': forms.Select(attrs={'class': 'form-select'}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.instance.redirect_uri or '').strip():
            self.fields['redirect_uri'].initial = self.instance.redirect_uri_efetiva()

    def save(self, commit=True):
        obj = super().save(commit=False)
        secret = self.cleaned_data.get('client_secret') or ''
        if secret.strip():
            from dashboard.conta_azul.config import gravar_client_secret
            gravar_client_secret(obj, secret)
        if commit:
            obj.save()
        return obj


class ServicoContaAzulFiscalForm(forms.ModelForm):
    natureza_operacao = forms.ChoiceField(
        label='Natureza de operação',
        required=False,
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'}),
    )

    class Meta:
        model = ServicoContaAzul
        fields = (
            'natureza_operacao',
            'codigo_servico_municipal',
            'codigo_nbs',
            'indicador_operacao',
            'c_class_trib',
        )
        widgets = {
            'codigo_servico_municipal': forms.TextInput(
                attrs={
                    'class': 'form-control js-catalogo-fiscal',
                    'data-catalogo': 'servico_municipal',
                    'placeholder': '040205',
                    'autocomplete': 'off',
                }
            ),
            'codigo_nbs': forms.TextInput(
                attrs={
                    'class': 'form-control js-catalogo-fiscal',
                    'data-catalogo': 'nbs',
                    'placeholder': '1.2301.22.00',
                    'autocomplete': 'off',
                }
            ),
            'indicador_operacao': forms.TextInput(
                attrs={
                    'class': 'form-control js-catalogo-fiscal',
                    'data-catalogo': 'indicador',
                    'placeholder': '030101',
                    'autocomplete': 'off',
                }
            ),
            'c_class_trib': forms.TextInput(
                attrs={
                    'class': 'form-control js-catalogo-fiscal',
                    'data-catalogo': 'cclasstrib',
                    'placeholder': '000001',
                    'autocomplete': 'off',
                }
            ),
        }
        help_texts = {
            'codigo_servico_municipal': 'Código de serviço municipal (LC 116 / prefeitura).',
            'c_class_trib': (
                'Código de Classificação Tributária. O Conta Azul calcula IBS/CBS automaticamente.'
            ),
            'codigo_nbs': 'Nomenclatura Brasileira de Serviços (cNBS).',
            'indicador_operacao': 'Código indicador de operação (INDop).',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        opcoes = [('', '— Selecione —')]
        valor_atual = (self.instance.natureza_operacao or '').strip()
        for item in naturezas_operacao():
            label = item.get('label') or item.get('descricao') or ''
            if label:
                opcoes.append((label, label))
        if valor_atual and valor_atual not in dict(opcoes):
            opcoes.insert(1, (valor_atual, valor_atual))
        self.fields['natureza_operacao'].choices = opcoes
