from django import forms

from .models import CartaoCredito


class CartaoCreditoForm(forms.ModelForm):
    class Meta:
        model = CartaoCredito
        fields = [
            'descricao', 'banco', 'bandeira', 'final_cartao', 'limite',
            'dia_fechamento_fatura', 'dia_vencimento_fatura', 'ativo',
        ]
        widgets = {
            'descricao': forms.TextInput(attrs={'class': 'form-control'}),
            'banco': forms.Select(attrs={'class': 'form-select'}),
            'bandeira': forms.Select(attrs={'class': 'form-select'}),
            'final_cartao': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '8',
                'inputmode': 'numeric',
                'placeholder': 'Ex.: 1234',
            }),
            'limite': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': 'Ex.: 34000',
            }),
            'dia_fechamento_fatura': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31}),
            'dia_vencimento_fatura': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31}),
            'ativo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'descricao': 'Descrição',
            'final_cartao': 'Final do cartão',
            'dia_fechamento_fatura': 'Data do fechamento da fatura',
            'dia_vencimento_fatura': 'Data do vencimento da fatura',
        }
        help_texts = {
            'final_cartao': 'Últimos dígitos do cartão (até 8 caracteres).',
            'limite': 'Limite total de crédito. Use ponto para centavos (ex.: 34000 ou 34000.00).',
            'dia_fechamento_fatura': 'Informe o dia do mês (1 a 31). Ex.: fechamento no dia 20.',
            'dia_vencimento_fatura': 'Informe o dia do mês (1 a 31). Ex.: vencimento no dia 3.',
        }

    def clean_final_cartao(self):
        valor = (self.cleaned_data.get('final_cartao') or '').strip()
        if valor and not valor.isdigit():
            raise forms.ValidationError('Informe apenas números no final do cartão.')
        return valor

    def clean_limite(self):
        limite = self.cleaned_data.get('limite')
        if limite is not None and limite < 0:
            raise forms.ValidationError('O limite não pode ser negativo.')
        return limite


class ImportarFaturaCartaoForm(forms.Form):
    BANCO_CHOICES = [
        ('', 'Detectar automaticamente'),
        ('SICREDI', 'Sicredi'),
        ('SICOOB', 'Sicoob'),
    ]

    cartao = forms.ModelChoiceField(
        label='Cartão cadastrado',
        queryset=CartaoCredito.objects.none(),
        required=False,
        empty_label='— Não vincular —',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    banco = forms.ChoiceField(
        label='Banco emissor',
        choices=BANCO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    arquivo = forms.FileField(
        label='Arquivo PDF da fatura',
        help_text='Fatura Sicredi ou Sicoob em formato PDF',
        widget=forms.ClearableFileInput(attrs={'accept': '.pdf,application/pdf', 'class': 'form-control'}),
    )

    def __init__(self, *args, empresa=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa is not None:
            self.fields['cartao'].queryset = CartaoCredito.objects.filter(
                empresa=empresa, ativo=True,
            ).order_by('descricao')

    def clean_arquivo(self):
        arquivo = self.cleaned_data['arquivo']
        nome = (arquivo.name or '').lower()
        if not nome.endswith('.pdf'):
            raise forms.ValidationError('Selecione um arquivo PDF.')
        if arquivo.size > 15 * 1024 * 1024:
            raise forms.ValidationError('Arquivo muito grande (máximo 15 MB).')
        return arquivo