from django import forms
from .models import Convenio, ServicosMedicos, TabelaPreco, Cabecalho

class ConvenioForm(forms.ModelForm):
    class Meta:
        model = Convenio
        fields = ['empresa', 'nome', 'dia_fechamento', 'dia_abertura', 'observacao']
        widgets = {
            'dia_fechamento': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31}),
            'dia_abertura': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 31}),
            'observacao': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empresa'].disabled = True
        self.fields['dia_fechamento'].label = 'Dia para fechamento'
        self.fields['dia_abertura'].label = 'Dia para abertura'
        self.fields['observacao'].label = 'Observação (particularidades do convênio)'

class ServicosMedicosForm(forms.ModelForm):
    class Meta:
        model = ServicosMedicos
        fields = ['codigo', 'servicos', 'porte_anestesico']

class TabelaPrecoForm(forms.ModelForm):
    class Meta:
        model = TabelaPreco
        fields = ['empresa', 'convenio', 'cabecalho', 'codigo_servico', 'preco_apartamento', 'preco_enfermaria']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['empresa'].disabled = True
        self.fields['preco_apartamento'].label = 'Preço sem Contraste'
        self.fields['preco_enfermaria'].label = 'Preço com Contraste'
        if self.instance and self.instance.empresa_id:
            self.fields['cabecalho'].queryset = Cabecalho.objects.filter(empresa_id=self.instance.empresa_id)
        elif self.initial.get('empresa'):
            self.fields['cabecalho'].queryset = Cabecalho.objects.filter(empresa_id=self.initial['empresa'])
        else:
            self.fields['cabecalho'].queryset = Cabecalho.objects.none()