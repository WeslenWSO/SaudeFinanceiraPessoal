from django import forms
from .models import RegraImposto

class RegraImpostoForm(forms.ModelForm):
    class Meta:
        model = RegraImposto
        fields = ['DescricaoRegraImposto', 'aliquota_pis', 'aliquota_cofins', 'aliquota_csll', 'aliquota_irpj', 'aliquota_iss_apuracao', 'percentual_calculo', 'ha_retencao']