from django import forms

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
    class Meta:
        model = ServicoContaAzul
        fields = (
            'natureza_operacao',
            'codigo_nbs',
            'indicador_operacao',
            'c_class_trib',
        )
        widgets = {
            'natureza_operacao': forms.TextInput(attrs={'class': 'form-control'}),
            'codigo_nbs': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1.2301.22.00'}),
            'indicador_operacao': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '030101'}),
            'c_class_trib': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '000001'}),
        }
        help_texts = {
            'c_class_trib': (
                'Código de Classificação Tributária. O Conta Azul calcula IBS/CBS automaticamente a partir deste código.'
            ),
            'codigo_nbs': 'Nomenclatura Brasileira de Serviços (cNBS).',
            'indicador_operacao': 'Código indicador de operação (INDop).',
        }
