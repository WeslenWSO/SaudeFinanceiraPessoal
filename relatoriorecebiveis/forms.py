from django import forms
from .models import RelatorioRecebiveisMaquinaCartao

class RelatorioRecebiveisForm(forms.ModelForm):
    class Meta:
        model = RelatorioRecebiveisMaquinaCartao
        fields = [
            'empresa', 'data_pagamento', 'forma_pagamento', 'bandeira',
            'valor_bruto', 'taxa_maquinha', 'valor_liquido', 'maquinha',
            'numero_autorizacao', 'data_venda', 'nsu_doc', 'parcelas',
            'total_parcelas', 'parcela_texto', 'conciliado', 'identificacao_extrato',
            'nota_fiscal', 'conta_a_receber', 'razao'
        ]
        widgets = {
            'data_pagamento': forms.DateInput(attrs={'type': 'date'}),
            'data_venda': forms.DateInput(attrs={'type': 'date'}),
            'valor_bruto': forms.NumberInput(attrs={'step': '0.01'}),
            'taxa_maquinha': forms.NumberInput(attrs={'step': '0.01'}),
            'valor_liquido': forms.NumberInput(attrs={'step': '0.01'}),
            'conciliado': forms.CheckboxInput(),
            'maquinha': forms.Select(attrs={'class': 'form-control'}),
        }

class InfinitePayPDFImportForm(forms.Form):
    pdf_file = forms.FileField(
        label='Selecione o PDF (Conta Web — relatório de recebimentos Infinite Pay)',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,application/pdf'}),
        required=True,
    )
    extrair_com_gemini = forms.BooleanField(
        label='Extrair com Google Gemini (IA)',
        required=False,
        initial=False,
        help_text=(
            'Usa o modelo Gemini para ler o PDF (melhor em tabelas complexas, logos e texto). '
            'Requer GEMINI_API_KEY em settings. Se falhar ou vier vazio, o sistema tenta a extração local.'
        ),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )


class CSVImportForm(forms.Form):
    csv_file = forms.FileField(
        label='Selecione o arquivo CSV',
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': '.csv'}),
        required=True
    )
    maquinha = forms.ChoiceField(
        label='Modelo da Máquina de Cartão',
        choices=RelatorioRecebiveisMaquinaCartao.MAQUINHA_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'}),
        required=True,
        help_text='Selecione o modelo da máquina de cartão que gerou o arquivo CSV'
    )


class CieloXLSXImportForm(forms.Form):
    xlsx_file = forms.FileField(
        label='Selecione o arquivo Excel (.xlsx) da Cielo',
        widget=forms.FileInput(
            attrs={
                'class': 'form-control',
                'accept': '.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            }
        ),
        required=True,
        help_text=(
            'Exporte o relatório detalhado de recebíveis no portal Cielo '
            '(Recebíveis → detalhe) em formato Excel (.xlsx).'
        ),
    )
